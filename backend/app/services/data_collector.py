import httpx
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models import Station, FuelPrice


class DataCollector:
    """Collects fuel price data from Tankerkonig API"""

    def __init__(self):
        self.api_key = settings.TANKERKONIG_API_KEY
        self.base_url = settings.TANKERKONIG_BASE_URL

    async def fetch_stations_list(
        self, lat: float, lng: float, rad: float, fuel_type: str = "all"
    ) -> Optional[Dict[str, Any]]:
        """Fetch list of stations from Tankerkonig API"""
        url = f"{self.base_url}/list.php"
        params = {
            "lat": lat,
            "lng": lng,
            "rad": rad,
            "type": fuel_type,
            "apikey": self.api_key,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                print(f"Requesting URL: {url} with params: {params}")
                response = await client.get(url, params=params)
                print(f"Response status: {response.status_code}")
                response.raise_for_status()
                data = response.json()
                print(
                    f"Response data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}"
                )

                if data.get("ok"):
                    return data
                else:
                    print(f"API Error: {data.get('message', 'Unknown error')}")
                    return None

            except Exception as e:
                print(f"Error fetching stations: {type(e).__name__}: {str(e)}")
                import traceback

                traceback.print_exc()
                return None

    async def fetch_prices_for_stations(
        self, station_ids: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Fetch current prices for specific stations"""
        if not station_ids:
            return None

        url = f"{self.base_url}/prices.php"

        # Tankerkonig API accepts max 10 stations per request
        chunks = [station_ids[i : i + 10] for i in range(0, len(station_ids), 10)]
        all_prices = {}

        async with httpx.AsyncClient(timeout=30.0) as client:
            for chunk in chunks:
                params = {"ids": ",".join(chunk), "apikey": self.api_key}

                try:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()

                    if data.get("ok"):
                        all_prices.update(data.get("prices", {}))
                    else:
                        print(f"API Error: {data.get('message', 'Unknown error')}")

                except Exception as e:
                    print(f"Error fetching prices: {e}")
                    continue

        return {"ok": True, "prices": all_prices} if all_prices else None

    def save_stations(self, stations_data: List[Dict], db: Session):
        """Save or update stations in database"""
        for station_data in stations_data:
            station_id = station_data.get("id")

            # Check if station exists
            existing_station = (
                db.query(Station).filter(Station.id == station_id).first()
            )

            if existing_station:
                # Update existing station
                existing_station.name = station_data.get("name", existing_station.name)
                existing_station.brand = station_data.get(
                    "brand", existing_station.brand
                )
                existing_station.is_open = station_data.get(
                    "isOpen", existing_station.is_open
                )
                existing_station.last_updated = datetime.utcnow()
            else:
                # Create new station
                new_station = Station(
                    id=station_id,
                    name=station_data.get("name", "Unknown"),
                    brand=station_data.get("brand", ""),
                    street=station_data.get("street", ""),
                    house_number=station_data.get("houseNumber", ""),
                    post_code=station_data.get("postCode", ""),
                    city=station_data.get("place", ""),
                    latitude=station_data.get("lat"),
                    longitude=station_data.get("lng"),
                    is_open=station_data.get("isOpen", True),
                )
                db.add(new_station)

        db.commit()

    def save_prices(self, prices_data: Dict[str, Dict], db: Session):
        """Save fuel prices to database"""
        timestamp = datetime.utcnow()

        for station_id, price_info in prices_data.items():
            # Only save if station exists and has price data
            if price_info.get("status") != "open":
                continue

            # Convert false values (unavailable fuel types) to None
            e5 = price_info.get("e5")
            e10 = price_info.get("e10")
            diesel = price_info.get("diesel")

            e5 = e5 if e5 is not False else None
            e10 = e10 if e10 is not False else None
            diesel = diesel if diesel is not False else None

            new_price = FuelPrice(
                id=str(uuid.uuid4()),
                station_id=station_id,
                timestamp=timestamp,
                e5=e5,
                e10=e10,
                diesel=diesel,
            )
            db.add(new_price)

        db.commit()

    async def fetch_and_store_prices(self):
        """Main function to fetch and store fuel prices"""
        print(f"[{datetime.utcnow()}] Starting data collection...")
        print(
            f"Config - API Key: {'***' + self.api_key[-4:] if self.api_key else 'MISSING'}"
        )
        print(
            f"Config - Lat: {settings.LATITUDE}, Lng: {settings.LONGITUDE}, Range: {settings.RANGE}"
        )

        db = SessionLocal()
        try:
            # Fetch stations in the configured area
            stations_response = await self.fetch_stations_list(
                lat=settings.LATITUDE, lng=settings.LONGITUDE, rad=settings.RANGE
            )

            if not stations_response:
                print("Failed to fetch stations")
                return

            stations = stations_response.get("stations", [])
            print(f"Found {len(stations)} stations")

            if not stations:
                return

            # Save/update stations
            self.save_stations(stations, db)

            # Get station IDs
            station_ids = [s["id"] for s in stations]

            # Fetch current prices
            prices_response = await self.fetch_prices_for_stations(station_ids)

            if prices_response and prices_response.get("prices"):
                prices = prices_response["prices"]
                print(f"Fetched prices for {len(prices)} stations")

                # Save prices
                self.save_prices(prices, db)
                print("Prices saved successfully")
            else:
                print("No prices fetched")

        except Exception as e:
            print(f"Error in data collection: {e}")
            db.rollback()
        finally:
            db.close()
