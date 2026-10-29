version: '3.8'

services:
  db:
    image: postgis/postgis:15-3.3
    container_name: hydcast_db
    environment:
      POSTGRES_USER: hydcast
      POSTGRES_PASSWORD: hydcast_password
      POSTGRES_DB: hydcast_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  api:
    build: ./backend
    container_name: hydcast_api
    command: uvicorn main:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
    environment:
      - HUBEAU_BASE_URL=https://hubeau.eaufrance.fr/api/v2/hydrometrie
      - OPEN_METEO_URL=https://api.open-meteo.com/v1/forecast
    depends_on:
      - db
    # Le frontend est servi statiquement (frontend/index.html) :
    #   python -m http.server 3000 --directory frontend
    # puis ouvrir http://localhost:3000?api=http://localhost:8000

volumes:
  postgres_data: