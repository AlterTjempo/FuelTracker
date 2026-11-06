"""Collects refined-product, Brent (USD) and EUR/USD prices from Yahoo Finance.

Hourly: the latest price per series with a real timestamp.
Backfill: once per start-up, missing daily closes of the last two years (stored
at noon UTC of the exchange's trading date) so that features can be validated
on more than a few weeks. Real observations only; nothing is interpolated.
"""

from datetime import datetime, timedelta, timezone

import httpx

import analytics_config as cfg
from database import SessionLocal
from models import MarketPrice

URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "FuelTracker/1.0 (compatible)"}


async def _fetch(client: httpx.AsyncClient, symbol: str, **params):
    try:
        r = await client.get(URL.format(symbol=symbol), params=params, headers=HEADERS)
        r.raise_for_status()
        result = r.json().get("chart", {}).get("result")
        return result[0] if result else None
    except httpx.HTTPStatusError as exc:
        print(f"[MarketCollector] {symbol}: HTTP {exc.response.status_code}")
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        print(f"[MarketCollector] {symbol}: network error ({type(exc).__name__})")
    except (ValueError, KeyError, IndexError):
        print(f"[MarketCollector] {symbol}: unexpected response")
    return None


class MarketCollector:
    async def fetch_and_store(self) -> None:
        """Latest price of every series (called hourly)."""
        now = datetime.now(timezone.utc)
        new_rows = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for series, symbol in cfg.MARKET_SERIES.items():
                res = await _fetch(client, symbol, range="1d", interval="1d")
                price = (res or {}).get("meta", {}).get("regularMarketPrice")
                if price is not None:
                    new_rows.append(
                        MarketPrice(
                            timestamp=now,
                            series=series,
                            source=f"yahoo:{symbol}",
                            value=float(price),
                        )
                    )
        self._save(new_rows)

    async def backfill(self) -> None:
        """Missing daily closes for the last `MARKET_BACKFILL_RANGE`."""
        rows = []
        async with httpx.AsyncClient(timeout=60.0) as client:
            for series, symbol in cfg.MARKET_SERIES.items():
                res = await _fetch(
                    client, symbol, range=cfg.MARKET_BACKFILL_RANGE, interval="1d"
                )
                if not res:
                    continue
                offset = res.get("meta", {}).get("gmtoffset", 0) or 0
                closes = (res.get("indicators", {}).get("quote") or [{}])[0].get(
                    "close"
                ) or []
                for ts, close in zip(res.get("timestamp") or [], closes):
                    if close is None:
                        continue
                    day = datetime.fromtimestamp(ts + offset, tz=timezone.utc).date()
                    stamp = datetime(
                        day.year, day.month, day.day, 12, tzinfo=timezone.utc
                    )
                    rows.append(
                        MarketPrice(
                            timestamp=stamp,
                            series=series,
                            source=f"yahoo:{symbol}:daily",
                            value=float(close),
                        )
                    )
        self._save(rows)

    @staticmethod
    def _save(rows) -> None:
        if not rows:
            return
        db = SessionLocal()
        try:
            existing = {
                (s, t)
                for s, t in db.query(MarketPrice.series, MarketPrice.timestamp).filter(
                    MarketPrice.timestamp
                    >= min(r.timestamp for r in rows) - timedelta(seconds=1)
                )
            }
            unique = {
                (r.series, r.timestamp): r for r in rows
            }  # last bar of a day wins
            fresh = [r for k, r in unique.items() if k not in existing]
            db.add_all(fresh)
            db.commit()
            print(f"[MarketCollector] Stored {len(fresh)} new row(s)")
        except Exception as exc:
            print(f"[MarketCollector] DB error: {type(exc).__name__}")
            db.rollback()
        finally:
            db.close()
