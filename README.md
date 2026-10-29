# HydCast 🌊

Application web de visualisation et prévision hydrologique : cartographie des cours d'eau et de leur bassin versant, et, au clic, l'historique (15 jours) et la prévision (7 jours) de pluie et de débit.

**Bassin pilote :** la Seine en amont de Paris.

## Architecture

```
Frontend (Leaflet + Chart.js)          Backend (FastAPI)
┌──────────────────────────┐   HTTP   ┌────────────────────────────────┐
│ Carte : bassin, tronçons,│ ───────► │ /api/watersheds  /api/rivers    │
│ stations hydrométriques  │          │ /api/stations                  │
│ Graphiques pluie/débit   │          │ /api/hydro/{station}            │
└──────────────────────────┘          │   ├─ Pluie/ETP : Open-Meteo     │
                                      │   ├─ Débit observé : Hub'Eau    │
                                      │   └─ Prévision débit : GR4J     │
                                      └──────────────┬─────────────────┘
                                                    PostGIS (bassins, tronçons — à venir)
```

### Sources de données


| Donnée                       | Source                                                                       | Coût              |
| ---------------------------- | ---------------------------------------------------------------------------- | ----------------- |
| Pluie observée + prévue, ETP | [Open-Meteo](https://open-meteo.com)                                         | gratuit, sans clé |
| Débit observé (temps réel)   | [Hub'Eau — Hydrométrie v2](https://hubeau.eaufrance.fr/page/api/hydrometrie) | gratuit, sans clé |
| Prévision de débit           | Modèle **GR4J** (Perrin et al., 2003) implémenté dans `backend/gr4j.py`      | —                 |


> ⚠️ Le GR4J est ici utilisé avec des paramètres par défaut + un recalage simple sur  
> les 15 derniers jours de débit observé : la prévision est **indicative** et ne doit  
> pas être utilisée pour la gestion de crise (se référer à [Vigicrues](https://www.vigicrues.gouv.fr)).

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


| Endpoint                        | Description                                                                                     |
| ------------------------------- | ----------------------------------------------------------------------------------------------- |
| `GET /api/watersheds`           | Bassins versants (GeoJSON)                                                                      |
| `GET /api/rivers`               | Tronçons de cours d'eau (GeoJSON), propriété `station_exutoire`                                 |
| `GET /api/stations`             | Stations hydrométriques (GeoJSON)                                                               |
| `GET /api/hydro/{station_code}` | Pluie (15 j obs + 7 j prév), débit observé (Hub'Eau, moyenne journalière) et débit prévu (GR4J) |


## Utilisation

1. La carte affiche le bassin versant (polygone bleu), les tronçons (Seine, Marne, Yonne, Aube) et les stations (points rouges).
2. Cliquez sur un tronçon ou une station : le panneau latéral affiche la pluie (barres) et le débit (courbes) sur les 15 derniers jours, puis la prévision à 7 jours (pluie Open-Meteo ; débit GR4J recalé, en pointillés orange).

## Feuille de route

- [ ] Charger bassins et tronçons depuis PostGIS (géométries officielles SANDRE/BDCARTHAGE) au lieu des données pilotes en dur
- [ ] Calage automatique du GR4J par station (optimisation des X1–X4 sur l'historique Hub'Eau)
- [ ] Étendue nationale + tributaires (Marne, Yonne, Aube…)
- [ ] Prévision d'ensemble (météo ensembliste Open-Meteo / ECMWF) avec bande d'incertitude
- [ ] Seuils de vigilance Vigicrues sur les graphiques

## Limites actuelles
Limites actuelles (assumées pour le pilote) : surfaces de bassin indicatives à affiner, GR4J non calé (prévision indicative, signalé dans l'UI), géométries simplifiées. Prochaines étapes logiques : calage automatique par station sur l'historique Hub'Eau, puis bascule des couches vers PostGIS. Dites-moi si vous voulez que je vous prépare aussi le Dockerfile du backend ou le script de calage.

## Licence

GPL-3.0