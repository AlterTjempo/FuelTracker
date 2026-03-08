"""
Fetches Brent crude oil spot price and converts it to EUR.

Data sources (no API key required):
  - Yahoo Finance public REST API  →  BZ=F (Brent crude futures, $/barrel)
  - open.er-api.com free tier      →  live USD→EUR exchange rate

1 barrel = 159 liters (metric standard)
"""

import httpx
from datetime import datetime, timezone

from database import SessionLocal
from models import OilPrice

BRENT_URL = "https://query2.finance.yahoo.com/v8/finance/chart/BZ%3DF"
EUR_USD_URL = "https://open.er-api.com/v6/latest/USD"
LITERS_PER_BARREL = 159


class OilCollector:
    """Fetches and persists Brent crude oil prices."""

    async def _fetch_brent_usd(self) -> float | None:
        headers = {"User-Agent": "FuelTracker/1.0 (compatible)"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(BRENT_URL, headers=headers)
                response.raise_for_status()
                data = response.json()
                meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
                price = meta.get("regularMarketPrice")
                return float(price) if price is not None else None
            except Exception as exc:
                print(f"[OilCollector] Error fetching Brent price: {exc}")
                return None

    async def _fetch_eur_rate(self) -> float | None:
        """Return EUR per 1 USD."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(EUR_USD_URL)
                response.raise_for_status()
                data = response.json()
                return data.get("rates", {}).get("EUR")
            except Exception as exc:
                print(f"[OilCollector] Error fetching EUR/USD rate: {exc}")
                return None

    async def fetch_and_store(self) -> None:
        price_usd = await self._fetch_brent_usd()
        if price_usd is None:
            print("[OilCollector] Skipping – Brent price unavailable.")
            return

        eur_rate = await self._fetch_eur_rate()
        if eur_rate is None:
            print("[OilCollector] Skipping – EUR/USD rate unavailable.")
            return

        price_eur_per_barrel = price_usd * eur_rate
        price_eur_per_liter = price_eur_per_barrel / LITERS_PER_BARREL

        db = SessionLocal()
        try:
            record = OilPrice(
                timestamp=datetime.now(timezone.utc),
                price_usd_per_barrel=round(price_usd, 4),
                price_eur_per_barrel=round(price_eur_per_barrel, 4),
                price_eur_per_liter=round(price_eur_per_liter, 6),
            )
            db.add(record)
            db.commit()
            print(
                f"[OilCollector] Stored: "
                f"${price_usd:.2f}/bbl  "
                f"€{price_eur_per_barrel:.2f}/bbl  "
                f"€{price_eur_per_liter:.4f}/L"
            )
        except Exception as exc:
            print(f"[OilCollector] DB error: {exc}")
            db.rollback()
        finally:
            db.close()
