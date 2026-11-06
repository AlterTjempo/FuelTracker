"""Dutch average pump prices from CBS (Statistics Netherlands) open data.

Table 80416ENG "Pump prices motor fuels; per type, per day": official weighted
daily averages (incl. VAT and excise) for Euro95, diesel and LPG, published
weekly. No API key required. Euro95 is the Dutch equivalent of E10 (E5 is not
published separately), so Euro95 is used as the reference for both E5 and E10.
"""

from datetime import date, datetime, timedelta

import httpx

from database import SessionLocal
from models import NlFuelPrice

CBS_URL = "https://opendata.cbs.nl/ODataApi/odata/80416ENG/TypedDataSet"
HEADERS = {"User-Agent": "FuelTracker/1.0 (hobby project)"}


def _parse_day(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


class NlCollector:
    """Fetches and stores the Dutch average pump prices."""

    async def fetch_and_store(self, days: int = 45) -> None:
        try:
            async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
                # The CBS ODataApi supports neither $orderby nor $skip/$top paging
                # but does honour a $filter on the period (YYYYMMDD) text.
                since = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
                params = {
                    "$filter": f"Periods ge '{since}'",
                    "$select": "Periods,Euro95_1,Diesel_2",
                    "$format": "json",
                }
                response = await client.get(CBS_URL, params=params)
                response.raise_for_status()
                rows = response.json().get("value", [])
        except httpx.HTTPStatusError as exc:
            print(
                f"[NlCollector] CBS HTTP error {exc.response.status_code}; will retry"
            )
            return
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            print(f"[NlCollector] CBS network error ({type(exc).__name__}); will retry")
            return
        except ValueError:
            print("[NlCollector] CBS returned invalid JSON; will retry")
            return

        parsed = {}
        for row in rows:
            day = _parse_day(row.get("Periods"))
            if day is None:
                continue
            e95, diesel = row.get("Euro95_1"), row.get("Diesel_2")
            if isinstance(e95, (int, float)) or isinstance(diesel, (int, float)):
                parsed[day] = (
                    e95 if isinstance(e95, (int, float)) else None,
                    diesel if isinstance(diesel, (int, float)) else None,
                )
        if not parsed:
            print("[NlCollector] No usable rows in CBS response")
            return

        db = SessionLocal()
        try:
            existing = {
                r.day: r
                for r in db.query(NlFuelPrice)
                .filter(NlFuelPrice.day.in_(list(parsed)))
                .all()
            }
            added = 0
            for day, (e95, diesel) in parsed.items():
                row = existing.get(day)
                if row is None:
                    db.add(NlFuelPrice(day=day, euro95=e95, diesel=diesel))
                    added += 1
                elif (row.euro95, row.diesel) != (e95, diesel):
                    row.euro95, row.diesel = e95, diesel  # CBS figures can be revised
            db.commit()
            print(f"[NlCollector] Stored {added} new day(s); latest {max(parsed)}")
        except Exception as exc:
            print(f"[NlCollector] DB error: {type(exc).__name__}")
            db.rollback()
        finally:
            db.close()
