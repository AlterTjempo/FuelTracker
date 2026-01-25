# FuelTracker

A fuel price tracking and analysis platform using the Tankerkonig API.

## Features

- 📊 Real-time fuel price tracking
- 📈 Historical price graphs and trends (24h, 3d, 7d, 1m, All time)
- 🏆 Lowest price finder with Google Maps routing
- 🗺️ Interactive station map with color-coded prices
- 🔍 Station comparison
- ⏰ Automatic data collection every hour
- 💾 Persistent historical data (never deleted)

## Setup

### Prerequisites

- Docker and Docker Compose
- Tankerkonig API key (get it from https://creativecommons.tankerkoenig.de/)

### Configuration

1. Copy the example config and add your API key:
   ```bash
   # Edit config.env and add your API key
   TANKERKONIG_API_KEY=your_api_key_here
   ```

2. Optional: Configure your location in `config.env`:
   ```env
   LATITUDE=52.52        # Your latitude
   LONGITUDE=13.405      # Your longitude
   RANGE=25              # Search radius in km
   ```

### Running

```bash
# Start all services
docker-compose up --build

# The API will be available at:
# http://localhost:8000
# API docs at: http://localhost:8000/docs
```

## API Endpoints

### Stations

- `GET /api/stations/` - List all stations
- `GET /api/stations/{station_id}` - Get station details

### Prices

- `GET /api/prices/current` - Current prices for all stations
- `GET /api/prices/lowest?fuel_type=diesel&hours=24` - Lowest prices
- `GET /api/prices/station/{station_id}/history?hours=24` - Price history for a station
- `GET /api/prices/station/{station_id}/stats` - Price statistics
- `GET /api/prices/history/all?fuel_type=diesel&hours=24` - Average prices for graphing

## Data Collection

The backend automatically collects data every hour from the Tankerkonig API.
All data is stored permanently in PostgreSQL with complete history for long-term analysis and graphing.
**No data is ever deleted** - you'll have a complete historical record of all price changes.

## Database Connection (DBeaver)

To connect to the PostgreSQL database using DBeaver:

1. **Open DBeaver** and create a new database connection (Database → New Database Connection)
2. **Select PostgreSQL** from the database list
3. **Enter connection details:**
   - **Host:** `localhost`
   - **Port:** `5432`
   - **Database:** `fuelprices`
   - **Username:** `fuel`
   - **Password:** `fuel`
4. **Test Connection** and click **Finish**

### Database Schema

**Tables:**
- `stations` - Gas station information (id, name, brand, location, etc.)
- `fuel_prices` - Historical price records (timestamp, station_id, e5, e10, diesel)

**Example Queries:**
```sql
-- View all stations
SELECT * FROM stations;

-- Get latest prices
SELECT s.name, s.city, fp.e5, fp.e10, fp.diesel, fp.timestamp
FROM fuel_prices fp
JOIN stations s ON fp.station_id = s.id
ORDER BY fp.timestamp DESC
LIMIT 20;

-- Find cheapest diesel prices
SELECT s.name, s.city, MIN(fp.diesel) as min_price
FROM fuel_prices fp
JOIN stations s ON fp.station_id = s.id
WHERE fp.diesel IS NOT NULL
GROUP BY s.name, s.city
ORDER BY min_price ASC
LIMIT 10;
```

## Tech Stack

- **Backend**: FastAPI (Python)
- **Database**: PostgreSQL
- **Scheduler**: APScheduler
- **Frontend**: Svelte (to be implemented)

## Next Steps

1. ✅ Data collection setup (DONE)
2. 🔲 Frontend development (Svelte)
3. 🔲 Advanced analytics and graphs
4. 🔲 ML-based price predictions
5. 🔲 Optimal refueling time recommendations
