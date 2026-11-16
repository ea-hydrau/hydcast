# HydCast 🌊

Application web de visualisation et prévision hydrologique : cartographie des cours d'eau et de leur bassin versant, et, au clic, l'historique (15 jours) et la prévision (7 jours) de pluie et de débit.

**Bassin pilote :** le Doux, en Ardèche.

## Architecture

```
Frontend (Leaflet + Chart.js)          Backend (FastAPI)
┌──────────────────────────┐   HTTP   ┌────────────────────────────────┐
│ Carte : bassin, stations  │ ───────► │ /api/watersheds  /api/stations  │
│ stations hydrométriques  │          │ /api/stations                  │
│ Graphiques pluie/débit   │          │ /api/hydro/{station}            │
└──────────────────────────┘          │   ├─ Pluie/ETP : Open-Meteo     │
                                      │   ├─ Débit observé : Hub'Eau    │
                                      │   └─ Prévision débit : GR4J     │
                                      └──────────────┬─────────────────┘
                                                    GeoPackages locaux (bassin, stations)
```

### Sources de données

| Donnée | Source | Coût |
|---|---|---|
| Pluie observée + prévue, ETP | [Open-Meteo](https://open-meteo.com) | gratuit, sans clé |
| Pluie prévue en ensemble (51 membres ECMWF) | [Open-Meteo Ensemble API](https://open-meteo.com/en/docs/ensemble-api) | gratuit, sans clé |
| Débit observé (temps réel) | [Hub'Eau — Hydrométrie v2](https://hubeau.eaufrance.fr/page/api/hydrometrie) | gratuit, sans clé |
| Prévision de débit | Modèle **GR4J** (Perrin et al., 2003) implémenté dans `backend/gr4j.py` | — |

### Couches SIG

Les couches chargées par l'API sont dans `backend/data/` :

- `ssbv_doux_wgs84.gpkg` : polygone du bassin versant, en EPSG:4326 ;
- `StationHydro_FXX_Doux.gpkg` : stations hydrométriques, reprojetées en EPSG:4326 à la lecture (source EPSG:2154).

Les surfaces drainées utilisées par GR4J sont configurées par code station dans
`backend/main.py` : 253 km² (`V371402001`), 372 km² (`V372401001`) et 671 km²
(`V374401001`). Elles sont fournies par l'utilisateur et sont à vérifier avant
toute utilisation opérationnelle. Aucun tronçon du Doux n'a encore été fourni ;
la couche `/api/rivers` est donc vide.

> ⚠️ Le GR4J est ici utilisé avec des paramètres par défaut + un recalage simple sur
> les 15 derniers jours de débit observé : la prévision est **indicative** et ne doit
> pas être utilisée pour la gestion de crise (se référer à [Vigicrues](https://www.vigicrues.gouv.fr)).

## Prévision d'ensemble & intervalles de confiance

Chaque station est forcée par les **51 membres de l'ensemble ECMWF** (`ecmwf_seamless`) :

1. un modèle GR4J unique digère l'historique (montée en régime + 15 derniers jours) ;
2. son état est dupliqué vers chacun des 51 membres ;
3. chaque membre produit sa propre hydrogramme de débit sur 7 jours ;
4. percentiles journaliers **q10 / q25 / q50 / q75 / q90** → intervalles de
   confiance affichés sur les graphiques (pluie : q10–q90 ; débit : q25–q75 et
   q10–q90, médiane en pointillés orange).

Si l'API ensemble est indisponible, l'application bascule automatiquement sur la
prévision déterministe (sans bandes).

## Démarrage rapide (sans Docker)

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload          # API sur http://localhost:8000
python -m http.server 3000 --directory frontend   # Frontend sur http://localhost:3000
```

Ouvrez `http://localhost:3000` (le frontend interroge l'API sur `http://localhost:8000` ;
utilisez `http://localhost:3000/?api=<url-de-l'api>` pour changer d'API).

## Démarrage avec Docker

```bash
docker compose up --build      # API sur :8000, PostGIS sur :5432
python -m http.server 3000 --directory frontend
```

## API

| Endpoint | Description |
|---|---|
| `GET /api/watersheds` | Bassins versants (GeoJSON) |
| `GET /api/rivers` | Tronçons de cours d'eau (GeoJSON, vide tant qu'aucune couche n'est fournie) |
| `GET /api/stations` | Stations hydrométriques (GeoJSON) |
| `GET /api/hydro/{station_code}` | Pluie (15 j obs + 7 j prév, déterministe et ensemble), débit observé (Hub'Eau) et débit prévu (GR4J : déterministe + percentiles q10–q90 de l'ensemble) |

## Utilisation

1. Choisissez le bassin puis la station dans le panneau à gauche, ou cliquez sur une station de la carte.
2. Le panneau affiche un graphique combiné : précipitations sur l'axe gauche inversé, débit observé et prévu sur l'axe droit, avec intervalles d'ensemble et séparateur « Aujourd'hui ». Sa mini-carte localise le bassin et la station.

## Feuille de route

- [ ] Charger aussi les tronçons du Doux (géométrie hydrographique officielle) et migrer les couches SIG vers PostGIS
- [ ] Calage automatique du GR4J par station (optimisation des X1–X4 sur l'historique Hub'Eau)
- [ ] Étendue nationale + tributaires (Marne, Yonne, Aube…)
- [ ] Propager aussi l'incertitude de l'ETP dans l'ensemble (membres de température)
- [ ] Seuils de vigilance Vigicrues sur les graphiques

## Licence

GPL-3.0