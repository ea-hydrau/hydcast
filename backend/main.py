"""API HydCast — FastAPI.

Données :
  - Pluie / ETP (passées 15 j + prévues 7 j) : Open-Meteo (gratuit, sans clé)
  - Pluie prévue en ensemble (51 membres ECMWF) : Open-Meteo Ensemble API
  - Débits observés (temps réel) : Hub'Eau / API Hydrométrie v2
  - Prévision de débit : modèle conceptuel GR4J forcé par chaque membre de
    l'ensemble météo -> percentiles q10/q25/q50/q75/q90
"""

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import geopandas as gpd
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from shapely.geometry import mapping

try:
    from .gr4j import GR4J, run_series      # uvicorn backend.main:app
except ImportError:
    from gr4j import GR4J, run_series       # uvicorn main:app (depuis backend/)

app = FastAPI(title="HydCast API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HUBEAU = "https://hubeau.eaufrance.fr/api/v2/hydrometrie"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ENSEMBLE = "https://ensemble-api.open-meteo.com/v1/ensemble"

PAST_DAYS = 15        # historique affiché (jours)
FORECAST_DAYS = 7     # prévision (jours)
WARMUP_DAYS = 60     # montée en régime du GR4J (jours)
ENSEMBLE_MODEL = "ecmwf_seamless"   # 51 membres

# ------------------------------------------------------------------
# Couches SIG du bassin du Doux
# ------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent / "data"
WATERSHED_FILE = DATA_DIR / "ssbv_doux_wgs84.gpkg"
STATIONS_FILE = DATA_DIR / "StationHydro_FXX_Doux.gpkg"

# Surfaces drainées aux stations, fournies par l'utilisateur (km²).
STATION_AREAS_KM2 = {
    "V371402001": 253,
    "V372401001": 372,
    "V374401001": 671,
}


def load_watersheds():
    layer = gpd.read_file(WATERSHED_FILE)
    if layer.crs is None:
        raise ValueError(f"Le système de coordonnées manque dans {WATERSHED_FILE}")

    areas_km2 = (
        layer.to_crs("EPSG:2154").geometry.area / 1_000_000
    ).round(2)
    layer = layer.to_crs("EPSG:4326")
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "id": row["CD_SSBV"],
                    "nom": row["LIB_SSBV"],
                    "surface_km2": float(area_km2),
                },
                "geometry": mapping(row.geometry),
            }
            for (_, row), area_km2 in zip(layer.iterrows(), areas_km2)
        ],
    }


def load_stations():
    layer = gpd.read_file(STATIONS_FILE)
    if layer.crs is None:
        raise ValueError(f"Le système de coordonnées manque dans {STATIONS_FILE}")
    layer = layer.to_crs("EPSG:4326")

    basins = gpd.read_file(WATERSHED_FILE)
    if basins.crs is None:
        raise ValueError(f"Le système de coordonnées manque dans {WATERSHED_FILE}")
    basins = basins.to_crs("EPSG:4326")

    stations = []
    for _, row in layer.iterrows():
        code = str(row["CdStationHydro"])
        point = row.geometry
        if point.geom_type != "Point":
            raise ValueError(f"La géométrie de la station {code} n'est pas un point")
        basin_ids = [
            str(basin["CD_SSBV"])
            for _, basin in basins.iterrows()
            if basin.geometry.covers(point)
        ]
        stations.append({
            "code": code,
            "nom": row["LbStationHydro"],
            "lat": point.y,
            "lon": point.x,
            "area_km2": STATION_AREAS_KM2[code],
            "bassin_ids": basin_ids,
        })
    return stations


WATERSHEDS = load_watersheds()
STATIONS = load_stations()

# Aucun tronçon de cours d'eau n'a été fourni pour le Doux.
RIVERS = {"type": "FeatureCollection", "features": []}

STATIONS_BY_CODE = {s["code"]: s for s in STATIONS}


def stations_geojson():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {k: v for k, v in s.items() if k not in ("lat", "lon")},
                "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]}
            }
            for s in STATIONS
        ]
    }


# ------------------------------------------------------------------
# Services externes
# ------------------------------------------------------------------

async def fetch_rain_etp(lat: float, lon: float) -> dict:
    """Pluie + ETP journalières : montée en régime + 15 jours passés
    + 7 jours de prévision déterministe (Open-Meteo)."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "precipitation_sum,et0_fao_evapotranspiration",
        "past_days": WARMUP_DAYS + PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(OPEN_METEO, params=params)
        r.raise_for_status()
        return r.json()


async def fetch_rain_ensemble(lat: float, lon: float) -> Optional[dict]:
    """Pluie journalière prévue par les 51 membres ECMWF (7 jours).
    Retourne {"dates": [...], "members": [[mm/j]*7]*51} ou None si indisponible."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "precipitation_sum",
        "models": ENSEMBLE_MODEL,
        "forecast_days": FORECAST_DAYS,
        "timezone": "auto",
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.get(OPEN_METEO_ENSEMBLE, params=params)
            r.raise_for_status()
            data = r.json().get("daily", {})
    except httpx.HTTPError:
        return None

    dates = data.get("time", [])
    members = []
    for i in range(51):  # member_0 .. member_50
        key = f"precipitation_sum_member_{i}"
        if key in data and data[key]:
            series = [v if v is not None else 0.0 for v in data[key]]
            members.append(series)
    if not members:
        return None
    return {"dates": dates, "members": members}


async def fetch_observed_flow(code_station: str) -> list:
    """Débit temps réel (Q, horaire, l/s) des PAST_DAYS derniers jours,
    agrégé en moyenne journalière (m³/s)."""
    start = (datetime.now(timezone.utc) - timedelta(days=PAST_DAYS)
             ).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"{HUBEAU}/observations_tr"
    params = {
        "code_entite": code_station,
        "grandeur_hydro": "Q",
        "date_debut_obs": start,
        "size": 20000,
        "fields": "date_obs,resultat_obs",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json().get("data", [])

    daily: dict = {}
    for obs in data:
        day = obs["date_obs"][:10]
        q = obs.get("resultat_obs")
        if q is not None:                       # l/s -> m³/s
            daily.setdefault(day, []).append(q / 1000.0)
    return [{"date": d, "q_m3s": sum(v) / len(v)}
            for d, v in sorted(daily.items())]


# ------------------------------------------------------------------
# Prévision GR4J par membre d'ensemble
# ------------------------------------------------------------------

def _percentile(sorted_vals, p):
    """Percentile linéaire d'une liste triée."""
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def ensemble_flow(rain_hist, etp_hist, members_rain, etp_fcst,
                 area_km2: float, bias: float) -> list:
    """Fait tourner le GR4J sur chaque membre de l'ensemble.

    1. un modèle unique digère l'historique (montée en régime) ;
    2. son état est dupliqué vers chaque membre ;
    3. chaque membre est forcé par sa pluie prévue (ETP déterministe partagée) ;
    4. percentiles journaliers q10/q25/q50/q75/q90 sur les 51 débits.

    Retourne [{"date":…, "q10":…, "q25":…, "q50":…, "q75":…, "q90":…}, …]
    """
    model = GR4J()
    for p, e in zip(rain_hist, etp_hist):
        model.step(p, e)                        # état commun après l'historique

    sims = []
    for member in members_rain:
        m = copy.deepcopy(model)
        q = [m.step(p, e) * area_km2 / 86.4 * bias
             for p, e in zip(member, etp_fcst)]
        sims.append(q)

    out = []
    for day in range(len(etp_fcst)):
        vals = sorted(s[day] for s in sims)
        out.append({
            "q10": round(_percentile(vals, 0.10), 1),
            "q25": round(_percentile(vals, 0.25), 1),
            "q50": round(_percentile(vals, 0.50), 1),
            "q75": round(_percentile(vals, 0.75), 1),
            "q90": round(_percentile(vals, 0.90), 1),
        })
    return out


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.get("/")
def read_root():
    return {"message": "API HydCast opérationnelle", "version": "0.3.0"}


@app.get("/api/watersheds")
def get_watersheds():
    """Couche vectorielle des bassins versants (GeoJSON)."""
    return WATERSHEDS


@app.get("/api/rivers")
def get_rivers():
    """Tronçons de cours d'eau (GeoJSON)."""
    return RIVERS


@app.get("/api/stations")
def get_stations():
    """Stations hydrométriques (GeoJSON)."""
    return stations_geojson()


@app.get("/api/hydro/{station_code}")
async def get_hydro(station_code: str, past_days: Optional[int] = Query(None, ge=1, le=30)):
    """Synthèse hydro pour une station : pluie passée/prévue (déterministe +
    ensemble), débit observé (Hub'Eau) et prévision de débit GR4J avec
    intervalles de confiance issus de l'ensemble (q10–q90)."""
    station = STATIONS_BY_CODE.get(station_code)
    if not station:
        raise HTTPException(404, "Station inconnue")

    past = past_days or PAST_DAYS

    weather, obs, ens = await fetch_rain_etp(station["lat"], station["lon"]), \
        await fetch_observed_flow(station_code), \
        await fetch_rain_ensemble(station["lat"], station["lon"])

    daily = weather.get("daily", {})
    dates = daily.get("time", [])
    rain = daily.get("precipitation_sum", [])
    etp = daily.get("et0_fao_evapotranspiration", [])

    if not dates or len(rain) != len(dates) or len(etp) != len(dates):
        raise HTTPException(502, "Série météo incomplète reçue d'Open-Meteo")

    # Open-Meteo peut ne pas avoir les premiers jours demandés dans son historique.
    first_valid = next(
        (i for i, (p, e) in enumerate(zip(rain, etp))
         if p is not None and e is not None),
        None,
    )
    if first_valid is None:
        raise HTTPException(502, "Aucune donnée météo exploitable reçue d'Open-Meteo")
    dates, rain, etp = dates[first_valid:], rain[first_valid:], etp[first_valid:]
    if any(p is None or e is None for p, e in zip(rain, etp)):
        raise HTTPException(502, "Données météo manquantes dans la période exploitable")

    # La série déterministe se termine par la prévision :
    n_hist = len(dates) - FORECAST_DAYS
    if n_hist < past:
        raise HTTPException(502, "Historique météo insuffisant pour la période demandée")

    # --- Recalage simple du GR4J sur les débits observés (facteur borné) ---
    q_sim_mm, _ = run_series(rain, etp, area_km2=station["area_km2"])
    q_sim_m3s = [q * station["area_km2"] / 86.4 for q in q_sim_mm]
    obs_by_date = {o["date"]: o["q_m3s"] for o in obs}
    obs_vals = list(obs_by_date.values())
    sim_vals = [q_sim_m3s[i] for i, d in enumerate(dates[:n_hist])
                if d in obs_by_date]
    if obs_vals and sim_vals and sum(sim_vals) > 0:
        ratio = min(4.0, max(0.25, sum(obs_vals) / sum(sim_vals)))
    else:
        ratio = 1.0

    # --- Prévision déterministe (repli si l'ensemble est indisponible) ---
    flow_forecast = [
        {"date": d, "q_m3s": round(q * ratio, 1)}
        for d, q in zip(dates[n_hist:], q_sim_m3s[n_hist:])
    ]
    for i in range(1, len(flow_forecast) - 1):
        flow_forecast[i]["q_m3s"] = round(
            (flow_forecast[i - 1]["q_m3s"] + flow_forecast[i]["q_m3s"]
             + flow_forecast[i + 1]["q_m3s"]) / 3, 1)

    # --- Prévision d'ensemble (GR4J x 51 membres) ---
    flow_ensemble, rain_ensemble = None, None
    if ens and ens["dates"]:
        try:
            fcst_dates = ens["dates"][:FORECAST_DAYS]
            flow_ensemble = ensemble_flow(
                rain[:n_hist], etp[:n_hist], ens["members"],
                etp[n_hist:n_hist + FORECAST_DAYS],
                station["area_km2"], ratio)
            for f, d in zip(flow_ensemble, fcst_dates):
                f["date"] = d
            # Percentiles de pluie par jour (pour le graphe pluie)
            rain_ensemble = []
            for day in range(len(fcst_dates)):
                vals = sorted(m[day] for m in ens["members"])
                rain_ensemble.append({
                    "date": fcst_dates[day],
                    "q10": round(_percentile(vals, 0.10), 1),
                    "q50": round(_percentile(vals, 0.50), 1),
                    "q90": round(_percentile(vals, 0.90), 1),
                })
        except Exception:      # repli silencieux en déterministe
            flow_ensemble, rain_ensemble = None, None

    return {
        "station": station,
        "past_days": past,
        "forecast_days": FORECAST_DAYS,
        "dates": dates[n_hist - past:],
        "rain": {
            "observed": rain[n_hist - past:n_hist],
            "forecast": rain[n_hist:],
            "ensemble": rain_ensemble,
        },
        "flow": {
            "observed": obs,                     # Hub'Eau (moy. journalière)
            "simulated": [round(q * ratio, 1)
                           for q in q_sim_m3s[n_hist - past:n_hist]],
            "forecast": flow_forecast,           # déterministe (repli)
            "ensemble": flow_ensemble,           # q10..q90 (51 membres)
            "bias_factor": round(ratio, 3),
        },
        "disclaimer": ("Prévision de débit indicative issue d'un modèle "
                       "conceptuel (GR4J) non calé, forcée par l'ensemble "
                       "ECMWF : ne pas utiliser pour la gestion de crise. "
                       "Se référer à Vigicrues."),
    }