# FuelTracker

A hobby project to track fuel prices in your area. Gets data from the Tankerkonig API and shows you where to find the cheapest gas.

## Features

- 📊 Real-time fuel price tracking
- 📈 Historical price graphs and trends (24h, 3d, 7d, 1m, all time)
- 🏆 Find the cheapest fuel with directions
- 🗺️ Interactive map showing gas stations with prices
- ⏰ Updates every 15 minutes automatically.
- 💾 Keeps all historical data for analysis

## Setup

### Prerequisites

- Docker and Docker Compose
- Tankerkonig API key (get it from https://creativecommons.tankerkoenig.de/)

### Configuration

1. Copy the example config and add your API key:
   ```bash
   cp config.env.example config.env
   # Edit config.env and add your Tankerkonig API key
   TANKERKONIG_API_KEY=your_api_key_here
   ```

2. Optional: Set your location to track nearby stations:
   ```env
   LATITUDE=52.52        # Your latitude
   LONGITUDE=13.405      # Your longitude
   RANGE=25              # Search radius in km
   ```

### Running

```bash
# Start everything with Docker
docker-compose up --build

# API will be at http://localhost:8001
# Docs at http://localhost:8001/docs
```

## API Endpoints

### Stations
- `GET /api/stations/` - List all stations
- `GET /api/stations/{station_id}` - Get details for a station

### Prices
- `GET /api/prices/current` - Current prices
- `GET /api/prices/lowest?fuel_type=diesel&hours=24` - Cheapest fuel
- `GET /api/prices/station/{station_id}/history?hours=24` - Price history
- `GET /api/prices/station/{station_id}/stats` - Price stats
- `GET /api/prices/history/all?fuel_type=diesel&hours=24` - Average prices for charts

## Data Collection

The backend fetches fresh data from Tankerkonig every 15 minutes and stores it in PostgreSQL. All historical data is kept, so you can track how prices change over time.

## Database

PostgreSQL stores the fuel prices and station data. Two main tables:
- `stations` - Gas station info (name, brand, location, etc.)
- `fuel_prices` - Price history (timestamp, station_id, e5, e10, diesel)

Example queries:
```sql
-- All stations
SELECT * FROM stations;

-- Latest prices
SELECT s.name, s.city, fp.e5, fp.e10, fp.diesel, fp.timestamp
FROM fuel_prices fp
JOIN stations s ON fp.station_id = s.id
ORDER BY fp.timestamp DESC
LIMIT 20;

-- Cheapest diesel
SELECT s.name, s.city, MIN(fp.diesel) as min_price
FROM fuel_prices fp
JOIN stations s ON fp.station_id = s.id
WHERE fp.diesel IS NOT NULL
GROUP BY s.name, s.city
ORDER BY min_price ASC
LIMIT 10;
```

## Tech Stack

- FastAPI (Python backend)
- PostgreSQL (database)
- APScheduler (15-minute data collection)
- Svelte (frontend)
- Tankerkonig API (fuel price data)

## Next Steps

- [ ] Frontend improvements
- [ ] Better graphs and analytics
- [ ] Mobile app maybe?
- [ ] Simple machine learning (because everything needs AI...)
