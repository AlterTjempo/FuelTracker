from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from slowapi import Limiter
from slowapi.util import get_remote_address

from database import get_db
from models import FuelPrice, Station

router = APIRouter()

# Rate limiter instance (shared with main app via state, but we need a
# reference here to use the @limiter.limit decorator on routes).
limiter = Limiter(key_func=get_remote_address)

# Whitelist mapping for fuel type → ORM column.
# Prevents SQL injection and unsafe getattr on arbitrary attributes.
FUEL_COLUMNS = {
    "e5": FuelPrice.e5,
    "e10": FuelPrice.e10,
    "diesel": FuelPrice.diesel,
}


def _get_fuel_column(fuel_type: str):
    """Return the validated ORM column for the given fuel type."""
    col = FUEL_COLUMNS.get(fuel_type)
    if col is None:
        raise HTTPException(status_code=400, detail="Invalid fuel type")
    return col


class PriceResponse(BaseModel):
    id: str
    station_id: str
    timestamp: datetime
    e5: Optional[float]
    e10: Optional[float]
    diesel: Optional[float]

    class Config:
        from_attributes = True


class CurrentPriceResponse(BaseModel):
    station_id: str
    station_name: str
    brand: Optional[str]
    city: Optional[str]
    is_open: bool
    e5: Optional[float]
    e10: Optional[float]
    diesel: Optional[float]
    timestamp: datetime


class LowestPriceResponse(BaseModel):
    fuel_type: str
    price: float
    station_id: str
    station_name: str
    city: Optional[str]
    is_open: bool
    timestamp: datetime


class PriceStatsResponse(BaseModel):
    fuel_type: str
    min_price: float
    max_price: float
    avg_price: float
    current_price: Optional[float]


@router.get("/current", response_model=List[CurrentPriceResponse])
def get_current_prices(
    fuel_type: Optional[str] = Query(None, pattern="^(e5|e10|diesel)$"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Get the most recent prices for all stations"""
    # Subquery to get the latest timestamp for each station
    subquery = (
        db.query(
            FuelPrice.station_id, func.max(FuelPrice.timestamp).label("max_timestamp")
        )
        .group_by(FuelPrice.station_id)
        .subquery()
    )

    # Join to get the full price records
    query = (
        db.query(FuelPrice, Station)
        .join(
            subquery,
            and_(
                FuelPrice.station_id == subquery.c.station_id,
                FuelPrice.timestamp == subquery.c.max_timestamp,
            ),
        )
        .join(Station, FuelPrice.station_id == Station.id)
    )

    results = query.limit(limit).all()

    response = []
    for price, station in results:
        response.append(
            CurrentPriceResponse(
                station_id=station.id,
                station_name=station.name,
                brand=station.brand,
                city=station.city,
                is_open=station.is_open,
                e5=price.e5,
                e10=price.e10,
                diesel=price.diesel,
                timestamp=price.timestamp,
            )
        )

    return response


@router.get("/current-lowest", response_model=List[LowestPriceResponse])
def get_current_lowest_prices(
    fuel_type: str = Query("diesel", pattern="^(e5|e10|diesel)$"),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Get the current lowest fuel prices (from the latest data available for each station)"""
    fuel_column = _get_fuel_column(fuel_type)

    # Subquery to get the latest timestamp for each station
    subquery = (
        db.query(
            FuelPrice.station_id, func.max(FuelPrice.timestamp).label("max_timestamp")
        )
        .group_by(FuelPrice.station_id)
        .subquery()
    )

    # Query for current lowest prices
    query = (
        db.query(
            FuelPrice.station_id,
            Station.name,
            Station.city,
            Station.is_open,
            fuel_column.label("current_price"),
            FuelPrice.timestamp,
        )
        .join(
            subquery,
            and_(
                FuelPrice.station_id == subquery.c.station_id,
                FuelPrice.timestamp == subquery.c.max_timestamp,
            ),
        )
        .join(Station, FuelPrice.station_id == Station.id)
        .filter(fuel_column.isnot(None))
        .order_by(fuel_column)
        .limit(limit)
    )

    results = query.all()

    response = []
    for station_id, name, city, is_open, current_price, timestamp in results:
        response.append(
            LowestPriceResponse(
                fuel_type=fuel_type,
                price=current_price,
                station_id=station_id,
                station_name=name,
                city=city,
                is_open=is_open,
                timestamp=timestamp,
            )
        )

    return response


@router.get("/lowest", response_model=List[LowestPriceResponse])
def get_lowest_prices(
    fuel_type: str = Query("diesel", pattern="^(e5|e10|diesel)$"),
    limit: int = Query(10, ge=1, le=50),
    hours: int = Query(24, ge=1, le=1000000),
    db: Session = Depends(get_db),
):
    """Get the lowest fuel prices in the specified timeframe"""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    fuel_column = _get_fuel_column(fuel_type)

    # Query for lowest prices
    query = (
        db.query(
            FuelPrice.station_id,
            Station.name,
            Station.city,
            Station.is_open,
            func.min(fuel_column).label("min_price"),
            func.max(FuelPrice.timestamp).label("latest_timestamp"),
        )
        .join(Station, FuelPrice.station_id == Station.id)
        .filter(FuelPrice.timestamp >= since, fuel_column.isnot(None))
        .group_by(FuelPrice.station_id, Station.name, Station.city, Station.is_open)
        .order_by(func.min(fuel_column))
        .limit(limit)
    )

    results = query.all()

    response = []
    for station_id, name, city, is_open, min_price, timestamp in results:
        response.append(
            LowestPriceResponse(
                fuel_type=fuel_type,
                price=min_price,
                station_id=station_id,
                station_name=name,
                city=city,
                is_open=is_open,
                timestamp=timestamp,
            )
        )

    return response


@router.get("/station/{station_id}/history", response_model=List[PriceResponse])
def get_station_price_history(
    station_id: str,
    hours: int = Query(24, ge=1, le=720),  # Up to 30 days
    db: Session = Depends(get_db),
):
    """Get price history for a specific station"""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    prices = (
        db.query(FuelPrice)
        .filter(FuelPrice.station_id == station_id, FuelPrice.timestamp >= since)
        .order_by(FuelPrice.timestamp.desc())
        .all()
    )

    if not prices:
        raise HTTPException(
            status_code=404, detail="No price data found for this station"
        )

    return prices


@router.get("/station/{station_id}/stats", response_model=List[PriceStatsResponse])
def get_station_stats(
    station_id: str,
    hours: int = Query(168, ge=1, le=720),  # Default 7 days
    db: Session = Depends(get_db),
):
    """Get price statistics for a station"""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    stats = []

    for fuel_type in ["e5", "e10", "diesel"]:
        fuel_column = _get_fuel_column(fuel_type)

        result = (
            db.query(
                func.min(fuel_column).label("min_price"),
                func.max(fuel_column).label("max_price"),
                func.avg(fuel_column).label("avg_price"),
            )
            .filter(
                FuelPrice.station_id == station_id,
                FuelPrice.timestamp >= since,
                fuel_column.isnot(None),
            )
            .first()
        )

        if result and result.min_price is not None:
            # Get current price
            current = (
                db.query(fuel_column)
                .filter(FuelPrice.station_id == station_id)
                .order_by(FuelPrice.timestamp.desc())
                .first()
            )

            stats.append(
                PriceStatsResponse(
                    fuel_type=fuel_type,
                    min_price=float(result.min_price),
                    max_price=float(result.max_price),
                    avg_price=float(result.avg_price),
                    current_price=float(current[0]) if current and current[0] else None,
                )
            )

    return stats


@router.get("/history/all")
@limiter.limit("60/minute")
def get_all_prices_history(
    request: Request,
    fuel_type: str = Query("diesel", pattern="^(e5|e10|diesel)$"),
    hours: int = Query(24, ge=1, le=1000000),
    db: Session = Depends(get_db),
):
    """Get average price history across all stations for graphing"""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    fuel_column = _get_fuel_column(fuel_type)

    # Group by hourly intervals
    results = (
        db.query(
            func.date_trunc("hour", FuelPrice.timestamp).label("hour"),
            func.avg(fuel_column).label("avg_price"),
            func.min(fuel_column).label("min_price"),
            func.max(fuel_column).label("max_price"),
            func.count(FuelPrice.id).label("sample_count"),
        )
        .filter(FuelPrice.timestamp >= since, fuel_column.isnot(None))
        .group_by("hour")
        .order_by("hour")
        .all()
    )

    return [
        {
            "timestamp": r.hour,
            "avg_price": float(r.avg_price) if r.avg_price else None,
            "min_price": float(r.min_price) if r.min_price else None,
            "max_price": float(r.max_price) if r.max_price else None,
            "sample_count": r.sample_count,
        }
        for r in results
    ]


@router.get("/analytics/time-patterns")
@limiter.limit("30/minute")
def get_time_patterns(
    request: Request,
    fuel_type: str = Query("e5", pattern="^(e5|e10|diesel)$"),
    hours: int = Query(168, ge=24, le=1000000),
    db: Session = Depends(get_db),
):
    """Get cheapest day and time patterns"""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    fuel_column = _get_fuel_column(fuel_type)

    # Check if we have enough data (at least 7 unique days for day patterns)
    unique_days = (
        db.query(func.count(func.distinct(func.date(FuelPrice.timestamp))))
        .filter(FuelPrice.timestamp >= since, fuel_column.isnot(None))
        .scalar()
        or 0
    )

    # For day-of-week patterns, need at least 7 days of data
    if unique_days < 7:
        return {
            "insufficient_data": True,
            "days_collected": unique_days,
            "days_needed": 7,
            "cheapest_day": None,
            "cheapest_hour": None,
            "by_day": [],
            "by_hour": [],
        }

    # Cheapest by day of week (0=Monday, 6=Sunday)
    day_results = (
        db.query(
            func.extract("dow", FuelPrice.timestamp).label("day_of_week"),
            func.avg(fuel_column).label("avg_price"),
        )
        .filter(FuelPrice.timestamp >= since, fuel_column.isnot(None))
        .group_by("day_of_week")
        .order_by("avg_price")
        .all()
    )

    # Cheapest by hour of day
    hour_results = (
        db.query(
            func.extract("hour", FuelPrice.timestamp).label("hour_of_day"),
            func.avg(fuel_column).label("avg_price"),
        )
        .filter(FuelPrice.timestamp >= since, fuel_column.isnot(None))
        .group_by("hour_of_day")
        .order_by("avg_price")
        .all()
    )

    days = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    return {
        "insufficient_data": False,
        "days_collected": unique_days,
        "cheapest_day": {
            "day": days[int(day_results[0].day_of_week)] if day_results else None,
            "avg_price": float(day_results[0].avg_price) if day_results else None,
        },
        "cheapest_hour": {
            "hour": int(hour_results[0].hour_of_day) if hour_results else None,
            "avg_price": float(hour_results[0].avg_price) if hour_results else None,
        },
        "by_day": [
            {"day": days[int(r.day_of_week)], "avg_price": float(r.avg_price)}
            for r in day_results
        ],
        "by_hour": [
            {"hour": int(r.hour_of_day), "avg_price": float(r.avg_price)}
            for r in hour_results
        ],
    }


@router.get("/analytics/go-now")
@limiter.limit("30/minute")
def get_go_now_indicator(
    request: Request,
    fuel_type: str = Query("e5", pattern="^(e5|e10|diesel)$"),
    db: Session = Depends(get_db),
):
    """Smart refuel indicator using same-hour-of-day percentile + trend.

    Two signals combined:
    1. Same-hour percentile: compare the current price against the SAME
       hour of day (±1h) over the past 7 days. This means a 7am price is
       only ranked against other ~7am prices, not cheap evening prices.
    2. Trend: linear regression over the last 3 hours of hourly minimums
       to detect whether prices are currently falling or rising.

    Matrix:
      cheap + falling  => excellent - Great price, still dropping
      cheap + rising   => good      - Good price, grab it before it rises
      mid   + falling  => neutral   - OK price, might improve
      mid   + rising   => wait      - Average but getting worse
      expensive + fall => wait      - Wait, price is coming down
      expensive + rise => avoid     - Expensive and climbing
    """
    fuel_column = _get_fuel_column(fuel_type)
    now = datetime.now(timezone.utc)

    # --- Current best price (lowest among all stations, last hour) ---
    one_hour_ago = now - timedelta(hours=1)
    current_min = (
        db.query(func.min(fuel_column))
        .filter(FuelPrice.timestamp >= one_hour_ago, fuel_column.isnot(None))
        .scalar()
    )

    insufficient = {
        "current_price": None,
        "percentile": None,
        "trend": None,
        "trend_direction": None,
        "week_low": None,
        "week_high": None,
        "week_median": None,
        "recommendation": "insufficient_data",
    }

    if current_min is None:
        return insufficient

    current_price = float(current_min)
    current_hour = now.hour

    # --- Same-hour-of-day percentile (±1 hour window, past 7 days) ---
    # Compare current price only against historical prices from the same
    # time-of-day window, so morning prices compete with mornings only.
    seven_days_ago = now - timedelta(days=7)
    hour_low = (current_hour - 1) % 24
    hour_high = (current_hour + 1) % 24

    # Build hour filter using ORM (safe — no raw SQL interpolation)
    hour_expr = func.extract("hour", FuelPrice.timestamp)
    if hour_low < hour_high:
        hour_condition = and_(hour_expr >= hour_low, hour_expr <= hour_high)
    else:
        # Wraps around midnight, e.g. 23, 0, 1
        hour_condition = (hour_expr >= hour_low) | (hour_expr <= hour_high)

    # Same-hour ORM query
    hour_bucket = func.date_trunc("hour", FuelPrice.timestamp).label("hour_bucket")
    same_hour_rows = (
        db.query(
            hour_bucket,
            func.min(fuel_column).label("min_price"),
        )
        .filter(
            FuelPrice.timestamp >= seven_days_ago,
            fuel_column.isnot(None),
            hour_condition,
        )
        .group_by(hour_bucket)
        .order_by(func.min(fuel_column))
        .all()
    )

    rows = same_hour_rows
    if len(rows) < 6:
        # Need at least 6 same-hour data points (~2 days worth)
        # Fall back to all-hours percentile
        fallback_rows = (
            db.query(
                hour_bucket,
                func.min(fuel_column).label("min_price"),
            )
            .filter(
                FuelPrice.timestamp >= seven_days_ago,
                fuel_column.isnot(None),
            )
            .group_by(hour_bucket)
            .order_by(func.min(fuel_column))
            .all()
        )
        rows = fallback_rows

        if len(rows) < 12:
            insufficient["current_price"] = round(current_price, 3)
            return insufficient

    prices = [float(r.min_price) for r in rows]
    total = len(prices)

    below_or_equal = sum(1 for p in prices if p <= current_price)
    percentile = round((below_or_equal / total) * 100, 1)

    week_low = min(prices)
    week_high = max(prices)
    sorted_prices = sorted(prices)
    mid = total // 2
    week_median = (
        sorted_prices[mid]
        if total % 2 == 1
        else (sorted_prices[mid - 1] + sorted_prices[mid]) / 2
    )

    # --- Trend: linear regression over last 3 hours ---
    # Get hourly min prices for the last 3 hours to compute slope.
    three_hours_ago = now - timedelta(hours=3)
    trend_bucket = func.date_trunc("hour", FuelPrice.timestamp).label("hour_bucket")
    trend_rows = (
        db.query(
            trend_bucket,
            func.min(fuel_column).label("min_price"),
        )
        .filter(
            FuelPrice.timestamp >= three_hours_ago,
            fuel_column.isnot(None),
        )
        .group_by(trend_bucket)
        .order_by(trend_bucket)
        .all()
    )

    # Calculate trend using simple linear regression (cents per hour)
    trend_cents_per_hour = 0.0
    trend_direction = "stable"
    if len(trend_rows) >= 2:
        n = len(trend_rows)
        # x = 0, 1, 2, ... (hour index), y = price
        trend_prices = [float(r.min_price) for r in trend_rows]
        x_mean = (n - 1) / 2.0
        y_mean = sum(trend_prices) / n

        numerator = sum((i - x_mean) * (p - y_mean) for i, p in enumerate(trend_prices))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator > 0:
            slope = numerator / denominator  # euros per hour
            trend_cents_per_hour = round(slope * 100, 2)  # convert to cents

            # Threshold: ±0.1 cent/hour to avoid noise
            if trend_cents_per_hour < -0.1:
                trend_direction = "falling"
            elif trend_cents_per_hour > 0.1:
                trend_direction = "rising"
            else:
                trend_direction = "stable"

    # --- Combined recommendation ---
    # Percentile buckets: cheap (<35), mid (35-65), expensive (>65)
    # Trend: falling, stable, rising
    if percentile <= 35:
        # Cheap
        if trend_direction == "falling":
            recommendation = "excellent"  # Great price, still dropping
        elif trend_direction == "stable":
            recommendation = "good"  # Good price, stable
        else:
            recommendation = "good"  # Good price, grab it before it rises
    elif percentile <= 65:
        # Mid-range
        if trend_direction == "falling":
            recommendation = "neutral"  # OK price, might improve
        elif trend_direction == "stable":
            recommendation = "neutral"  # Average price
        else:
            recommendation = "wait"  # Average but getting worse
    else:
        # Expensive
        if trend_direction == "falling":
            recommendation = "wait"  # Wait, price is coming down
        elif trend_direction == "stable":
            recommendation = "wait"  # Expensive, wait for drop
        else:
            recommendation = "avoid"  # Expensive and climbing

    return {
        "current_price": round(current_price, 3),
        "percentile": percentile,
        "trend": trend_cents_per_hour,
        "trend_direction": trend_direction,
        "week_low": round(week_low, 3),
        "week_high": round(week_high, 3),
        "week_median": round(week_median, 3),
        "recommendation": recommendation,
    }


@router.get("/analytics/top-stations")
@limiter.limit("30/minute")
def get_top_stations(
    request: Request,
    fuel_type: str = Query("e5", pattern="^(e5|e10|diesel)$"),
    hours: int = Query(168, ge=24, le=1000000),
    limit: int = Query(3, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """Get top stations by average price and consistency"""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    # Volatility is always measured over a fixed 30-day window so that the
    # stability label is a station characteristic, not an artefact of the
    # currently selected time range.
    volatility_since = datetime.now(timezone.utc) - timedelta(days=30)
    fuel_column = _get_fuel_column(fuel_type)

    # Get station statistics (ranking window = user-selected hours)
    station_stats = (
        db.query(
            FuelPrice.station_id,
            Station.name,
            Station.brand,
            Station.city,
            func.avg(fuel_column).label("avg_price"),
            func.min(fuel_column).label("min_price"),
            func.max(fuel_column).label("max_price"),
            func.count(FuelPrice.id).label("data_points"),
        )
        .join(Station, FuelPrice.station_id == Station.id)
        .filter(FuelPrice.timestamp >= since, fuel_column.isnot(None))
        .group_by(FuelPrice.station_id, Station.name, Station.brand, Station.city)
        .order_by(func.avg(fuel_column))
        .limit(limit)
        .all()
    )

    # Volatility subquery over fixed 30-day window
    volatility_rows = (
        db.query(
            FuelPrice.station_id,
            func.stddev(fuel_column).label("volatility"),
        )
        .filter(FuelPrice.timestamp >= volatility_since, fuel_column.isnot(None))
        .group_by(FuelPrice.station_id)
        .all()
    )
    volatility_map = {row.station_id: row.volatility for row in volatility_rows}

    # Calculate cheapest counts - simplified approach
    # Get total number of hourly samples
    total_samples = (
        db.query(
            func.count(func.distinct(func.date_trunc("hour", FuelPrice.timestamp)))
        )
        .filter(FuelPrice.timestamp >= since, fuel_column.isnot(None))
        .scalar()
        or 1
    )

    # For each station, approximate how often it was cheapest
    # by comparing its minimum price to overall minimum
    cheapest_counts = {}
    overall_min = (
        db.query(func.min(fuel_column))
        .filter(FuelPrice.timestamp >= since, fuel_column.isnot(None))
        .scalar()
        or 0
    )

    for stat in station_stats:
        # Simple heuristic: if station's min price is close to overall min,
        # it was likely cheapest more often
        if overall_min > 0:
            price_diff = abs(stat.min_price - overall_min)
            # Stations within 1 cent of absolute min are considered frequently cheapest
            if price_diff < 0.01:
                cheapest_counts[stat.station_id] = int(
                    total_samples * 0.3
                )  # Rough estimate
            elif price_diff < 0.02:
                cheapest_counts[stat.station_id] = int(total_samples * 0.15)
            else:
                cheapest_counts[stat.station_id] = 0
        else:
            cheapest_counts[stat.station_id] = 0

    results = []
    for stat in station_stats:
        cheapest_count = cheapest_counts.get(stat.station_id, 0)
        cheapest_percentage = (
            (cheapest_count / total_samples) * 100 if total_samples > 0 else 0
        )

        volatility = volatility_map.get(stat.station_id) or 0
        results.append(
            {
                "station_id": stat.station_id,
                "name": stat.name,
                "brand": stat.brand,
                "city": stat.city,
                "avg_price": round(float(stat.avg_price), 3),
                "min_price": round(float(stat.min_price), 3),
                "max_price": round(float(stat.max_price), 3),
                "volatility": round(float(volatility), 4),
                "cheapest_percentage": round(cheapest_percentage, 1),
                "data_points": stat.data_points,
            }
        )

    return results


@router.get("/analytics/heatmap")
@limiter.limit("30/minute")
def get_price_heatmap(
    request: Request,
    fuel_type: str = Query("e5", pattern="^(e5|e10|diesel)$"),
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Return average price grouped by day-of-week (0=Mon … 6=Sun) and hour-of-day (0-23).

    The result is a flat list of {day_of_week, hour_of_day, avg_price} objects
    covering only cells that have data.  Missing cells should be treated as null
    by the frontend.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    fuel_column = _get_fuel_column(fuel_type)

    # PostgreSQL: EXTRACT(DOW …) returns 0=Sunday … 6=Saturday.
    # We remap to 0=Monday … 6=Sunday in Python.
    rows = (
        db.query(
            func.extract("dow", FuelPrice.timestamp).label("dow_pg"),
            func.extract("hour", FuelPrice.timestamp).label("hour_of_day"),
            func.avg(fuel_column).label("avg_price"),
        )
        .filter(FuelPrice.timestamp >= since, fuel_column.isnot(None))
        .group_by("dow_pg", "hour_of_day")
        .order_by("dow_pg", "hour_of_day")
        .all()
    )

    # Remap PostgreSQL DOW (0=Sun) → ISO (0=Mon)
    result = []
    for row in rows:
        pg_dow = int(row.dow_pg)  # 0=Sun, 1=Mon, …, 6=Sat
        iso_dow = (pg_dow + 6) % 7  # 0=Mon, …, 6=Sun
        result.append(
            {
                "day_of_week": iso_dow,
                "hour_of_day": int(row.hour_of_day),
                "avg_price": round(float(row.avg_price), 3),
            }
        )

    return result


@router.get("/analytics/lowest-ever")
@limiter.limit("30/minute")
def get_lowest_price_ever(
    request: Request,
    fuel_type: str = Query("e5", pattern="^(e5|e10|diesel)$"),
    db: Session = Depends(get_db),
):
    """Get the lowest price ever recorded with station and timestamp"""
    fuel_column = _get_fuel_column(fuel_type)

    # Find the record with the absolute minimum price
    result = (
        db.query(FuelPrice, Station)
        .join(Station, FuelPrice.station_id == Station.id)
        .filter(fuel_column.isnot(None))
        .order_by(fuel_column.asc())
        .first()
    )

    if not result:
        return {
            "price": None,
            "timestamp": None,
            "station_id": None,
            "station_name": None,
            "city": None,
        }

    price_record, station = result
    # fuel_type is already validated by _get_fuel_column above; use a dict
    # lookup on the known columns to avoid getattr on arbitrary attributes.
    price_map = {
        "e5": price_record.e5,
        "e10": price_record.e10,
        "diesel": price_record.diesel,
    }
    price_value = price_map.get(fuel_type)
    if price_value is None:
        raise HTTPException(status_code=404, detail="No price data found")

    return {
        "price": round(float(price_value), 3),
        "timestamp": price_record.timestamp,
        "station_id": station.id,
        "station_name": station.name,
        "brand": station.brand,
        "city": station.city,
    }
