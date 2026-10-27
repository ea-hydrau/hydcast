from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI(title="HydCast API")

# Autoriser le frontend à communiquer avec l'API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exemple fictif d'un bassin versant (polygone) autour de la Seine à Paris
DEMO_WATERSHED = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "id": "bassin_seine_paris",
                "nom": "Bassin de la Seine (Paris)",
                "surface_km2": 1200
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [2.2, 48.8],
                    [2.5, 48.8],
                    [2.5, 49.0],
                    [2.2, 49.0],
                    [2.2, 48.8]
                ]]
            }
        }
    ]
}

@app.get("/")
def read_root():
    return {"message": "API HydCast opérationnelle"}

@app.get("/api/watersheds")
def get_watersheds():
    """Retourne la couche vectorielle des bassins versants (GeoJSON)."""
    return DEMO_WATERSHED

@app.get("/api/weather/rain")
async def get_rain_data(lat: float, lon: float):
    """
    Récupère la pluie passée (15 jours) et à venir (7 jours)
    via l'API Open-Meteo pour un point (lat, lon).
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "precipitation",
        "past_days": 15,
        "forecast_days": 7,
        "timezone": "auto"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Erreur lors de la récupération des données météo")
        return response.json()
