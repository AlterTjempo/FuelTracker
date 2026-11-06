from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, literal_column
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import analytics_config as cfg
from cache import ttl_cached
from limiter import limiter
from services import go_now, literboard
from services.stats_utils import haversine_km

from database import get_db
from models import FuelPrice, Station

router = APIRouter()

# Time-of-day / day-of-week statistics are evaluated in German local time.
LOCAL_TZ_NAME = "Europe/Berlin"
LOCAL_TZ = ZoneInfo(LOCAL_TZ_NAME)
# Max age of a station's latest price for it to count as a "current" price.
CURRENT_PRICE_MAX_AGE = timedelta(minutes=30)


def _local_ts():
    """FuelPrice.timestamp converted to Europe/Berlin wall-clock time."""
    return func.timezone(LOCAL_TZ_NAME, FuelPrice.timestamp)


# Whitelist mapping for fuel type → ORM column.
# Prevents SQL injection and unsafe getattr on arbitrary attributes.
FUEL_COLUMNS = {
    "e5": FuelPrice.e5,
    "e10": FuelPrice.e10,
    "diesel": FuelPrice.diesel,
}


def _stability_label(ratio):
    """Label a station's daily price swing relative to the market median."""
    if ratio is None:
        return None
    if ratio <= 0.75:
        return "very_stable"
    if ratio <= 0.92:
        return "stable"
    if ratio <= 1.08:
        return "typical"
    if ratio <= 1.25:
        return "volatile"
    return "very_volatile"


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
@limiter.limit("120/minute")
@ttl_cached(120)
def get_all_prices_history(
    request: Request,
    fuel_type: str = Query("diesel", pattern="^(e5|e10|diesel)$"),
    hours: int = Query(24, ge=1, le=1000000),
    start: Optional[datetime] = Query(
        None, description="Window start (overrides `hours`)"
    ),
    end: Optional[datetime] = Query(None, description="Window end (default: now)"),
    bucket_minutes: int = Query(60, description="Bucket size: 15, 30 or 60 minutes"),
    db: Session = Depends(get_db),
):
    """Average price history across all stations for graphing.

    Default is hourly buckets over the last `hours`. For zooming, pass
    `start`/`end` and a finer `bucket_minutes` (15 = the collection interval,
    i.e. the individual observations). Fine buckets are limited to 14 days.
    """
    if bucket_minutes not in (15, 30, 60):
        raise HTTPException(
            status_code=400, detail="bucket_minutes must be 15, 30 or 60"
        )
    fuel_column = _get_fuel_column(fuel_type)

    now = datetime.now(timezone.utc)
    if start is not None:
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        since = start
        until = end if end is not None else now
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        if until <= since:
            raise HTTPException(status_code=400, detail="end must be after start")
        if bucket_minutes < 60 and (until - since) > timedelta(days=14):
            raise HTTPException(
                status_code=400, detail="Fine-grained buckets are limited to 14 days"
            )
    else:
        since = now - timedelta(hours=hours)
        until = None

    bucket = func.date_bin(
        literal_column(f"interval '{int(bucket_minutes)} minutes'"),
        FuelPrice.timestamp,
        literal_column("TIMESTAMPTZ '2000-01-03 00:00:00+00'"),
    )

    filters = [FuelPrice.timestamp >= since, fuel_column.isnot(None)]
    if until is not None:
        filters.append(FuelPrice.timestamp <= until)

    results = (
        db.query(
            bucket.label("hour"),
            func.avg(fuel_column).label("avg_price"),
            func.min(fuel_column).label("min_price"),
            func.max(fuel_column).label("max_price"),
            func.count(FuelPrice.id).label("sample_count"),
        )
        .filter(*filters)
        .group_by(bucket)
        .order_by(bucket)
        .all()
    )

    return [
        {
            "timestamp": r.hour,
            "avg_price": float(r.avg_price) if r.avg_price is not None else None,
            "min_price": float(r.min_price) if r.min_price is not None else None,
            "max_price": float(r.max_price) if r.max_price is not None else None,
            "sample_count": r.sample_count,
        }
        for r in results
    ]


@router.get("/analytics/time-patterns")
@limiter.limit("30/minute")
@ttl_cached(300)
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
        db.query(func.count(func.distinct(func.date(_local_ts()))))
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
            func.extract("isodow", _local_ts()).label("day_of_week"),
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
            func.extract("hour", _local_ts()).label("hour_of_day"),
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
            "day": days[int(day_results[0].day_of_week) - 1] if day_results else None,
            "avg_price": float(day_results[0].avg_price) if day_results else None,
        },
        "cheapest_hour": {
            "hour": int(hour_results[0].hour_of_day) if hour_results else None,
            "avg_price": float(hour_results[0].avg_price) if hour_results else None,
        },
        "by_day": [
            {"day": days[int(r.day_of_week) - 1], "avg_price": float(r.avg_price)}
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
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    max_distance_km: Optional[float] = Query(
        None, gt=0, le=cfg.GO_NOW_MAX_DISTANCE_KM_LIMIT
    ),
    station_id: Optional[str] = Query(None, max_length=64),
    db: Session = Depends(get_db),
):
    """Refuel-now indicator: same-hour percentile + trend (see docs/prediction-models.md).

    Optional filters restrict which stations count: either a single
    `station_id`, or all stations within `max_distance_km` of (`lat`, `lon`).
    Without filters every tracked station counts (the default).
    The decision logic lives in services/go_now.py and is backtested by
    services/go_now_backtest.py.
    """
    fuel_column = _get_fuel_column(fuel_type)
    now = datetime.now(timezone.utc)

    # --- which stations count? ---
    allowed_ids = None
    applied = {"type": "all"}
    if station_id:
        station = db.query(Station).filter(Station.id == station_id).first()
        if station is None:
            raise HTTPException(status_code=404, detail="Station not found")
        allowed_ids = [station.id]
        applied = {
            "type": "station",
            "station_id": station.id,
            "station_name": station.name,
        }
    elif lat is not None or lon is not None or max_distance_km is not None:
        if lat is None or lon is None or max_distance_km is None:
            raise HTTPException(
                status_code=400,
                detail="lat, lon and max_distance_km must be given together",
            )
        allowed_ids = [
            sid
            for sid, slat, slon in db.query(
                Station.id, Station.latitude, Station.longitude
            )
            if haversine_km(lat, lon, slat, slon) <= max_distance_km
        ]
        applied = {
            "type": "radius",
            "max_distance_km": max_distance_km,
            "stations_in_range": len(allowed_ids),
        }

    insufficient = {
        "current_price": None,
        "percentile": None,
        "trend": None,
        "trend_direction": None,
        "week_low": None,
        "week_high": None,
        "week_median": None,
        "recommendation": "insufficient_data",
        "station_id": None,
        "station_name": None,
        "price_timestamp": None,
        "filter": applied,
    }
    if allowed_ids is not None and not allowed_ids:
        return insufficient

    def restrict(query):
        return (
            query
            if allowed_ids is None
            else query.filter(FuelPrice.station_id.in_(allowed_ids))
        )

    # --- current best price: each station's latest row, fresh and open ---
    fresh_since = now - timedelta(minutes=cfg.GO_NOW_FRESH_MINUTES)
    latest_ts = (
        restrict(
            db.query(
                FuelPrice.station_id.label("station_id"),
                func.max(FuelPrice.timestamp).label("max_ts"),
            )
        )
        .group_by(FuelPrice.station_id)
        .subquery()
    )
    best = (
        db.query(fuel_column, Station.id, Station.name, FuelPrice.timestamp)
        .join(
            latest_ts,
            and_(
                FuelPrice.station_id == latest_ts.c.station_id,
                FuelPrice.timestamp == latest_ts.c.max_ts,
            ),
        )
        .join(Station, Station.id == FuelPrice.station_id)
        .filter(
            FuelPrice.timestamp >= fresh_since,
            Station.is_open.is_(True),
            fuel_column.isnot(None),
        )
        .order_by(fuel_column.asc())
        .first()
    )
    if best is None:
        return insufficient
    current_price = float(best[0])

    # --- hourly lows over the shape window (covers the 7-day percentile window too) ---
    hour_bucket = func.date_trunc("hour", FuelPrice.timestamp)
    rows = (
        restrict(db.query(hour_bucket, func.min(fuel_column)))
        .filter(
            FuelPrice.timestamp >= now - timedelta(days=cfg.GO_NOW_SHAPE_DAYS + 1),
            fuel_column.isnot(None),
        )
        .group_by(hour_bucket)
        .all()
    )
    lows = {k: float(v) for k, v in rows}

    decision = go_now.decide(lows, now, current_price)
    if decision is None:
        insufficient["current_price"] = round(current_price, 3)
        return insufficient

    return {
        "current_price": round(current_price, 3),
        "percentile": decision.percentile,
        "trend": (
            round(decision.slope_c_per_h, 2)
            if decision.slope_c_per_h is not None
            else 0.0
        ),
        "trend_direction": decision.trend_direction,
        "week_low": round(decision.week_low, 3),
        "week_high": round(decision.week_high, 3),
        "week_median": round(decision.week_median, 3),
        "recommendation": decision.recommendation,
        "station_id": best[1],
        "station_name": best[2],
        "price_timestamp": best[3],
        "hours_to_jump": (
            round(decision.hours_to_jump, 1)
            if decision.hours_to_jump is not None
            else None
        ),
        "filter": applied,
    }


@router.get("/analytics/top-stations")
@limiter.limit("30/minute")
@ttl_cached(900)  # prices change every 15 minutes; this is the heaviest aggregate
def get_top_stations(
    request: Request,
    fuel_type: str = Query("e5", pattern="^(e5|e10|diesel)$"),
    hours: int = Query(168, ge=24, le=1000000),
    limit: int = Query(3, ge=1, le=10),
    opening_hours_weighted: bool = Query(
        False,
        description="Relate 'cheapest X% of the time' to the hours the station had data (was open)",
    ),
    db: Session = Depends(get_db),
):
    """Top stations by average price, with the data volume behind every figure.

    Stations with too little data in the window are returned unranked at the
    end (`ranked: false`, `enough_data: false`) instead of being ranked next to
    well-covered stations. See docs/prediction-models.md.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    # Stability uses a fixed window (analytics_config.LITERBOARD_STABILITY_DAYS) so that the
    # label is a station characteristic, not an artefact of the selected time range.
    stability_since = now - timedelta(days=cfg.LITERBOARD_STABILITY_DAYS)
    fuel_column = _get_fuel_column(fuel_type)
    local_day = func.date(_local_ts())

    # Ranking window statistics for every station (all stations: eligibility needs the full picture)
    hour_bucket = func.date_trunc("hour", FuelPrice.timestamp).label("hour_bucket")
    # One aggregation over the window, reused for hours-with-data, the cheapest share and the
    # number of hours in the window (previously three separate scans of the whole table).
    per_station_hour = (
        db.query(
            hour_bucket,
            FuelPrice.station_id.label("station_id"),
            func.min(fuel_column).label("min_price"),
        )
        .filter(FuelPrice.timestamp >= since, fuel_column.isnot(None))
        .group_by(hour_bucket, FuelPrice.station_id)
        .cte("per_station_hour")
    )
    ranked_cte = db.query(
        per_station_hour.c.station_id,
        func.rank()
        .over(
            partition_by=per_station_hour.c.hour_bucket,
            order_by=per_station_hour.c.min_price,
        )
        .label("rnk"),
        func.dense_rank()
        .over(order_by=per_station_hour.c.hour_bucket)
        .label("hour_no"),
    ).cte("ranked")
    coverage_rows = (
        db.query(
            ranked_cte.c.station_id,
            func.count().label("hours"),
            func.count().filter(ranked_cte.c.rnk == 1).label("cheapest"),
            func.max(ranked_cte.c.hour_no).label("window_hours"),
        )
        .group_by(ranked_cte.c.station_id)
        .all()
    )
    hours_by_station = {r.station_id: r.hours for r in coverage_rows}
    cheapest_counts = {r.station_id: r.cheapest for r in coverage_rows}
    total_hours = max((r.window_hours for r in coverage_rows), default=0)
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
            func.count(func.distinct(local_day)).label("days_with_data"),
        )
        .join(Station, FuelPrice.station_id == Station.id)
        .filter(FuelPrice.timestamp >= since, fuel_column.isnot(None))
        .group_by(FuelPrice.station_id, Station.name, Station.brand, Station.city)
        .all()
    )

    # Stability = how big a station's typical daily price swing is compared with
    # the other stations (see docs). Rows exist only while a station is open, so
    # a day's range is always measured over its open hours.
    daily = (
        db.query(
            FuelPrice.station_id.label("station_id"),
            (func.max(fuel_column) - func.min(fuel_column)).label("rng"),
            func.count(FuelPrice.id).label("n"),
        )
        .filter(FuelPrice.timestamp >= stability_since, fuel_column.isnot(None))
        .group_by(FuelPrice.station_id, local_day)
        .subquery()
    )
    swing_rows = (
        db.query(
            daily.c.station_id,
            func.avg(daily.c.rng).label("swing"),
            func.count().label("days"),
        )
        .filter(daily.c.n >= cfg.LITERBOARD_MIN_ROWS_PER_DAY)
        .group_by(daily.c.station_id)
        .all()
    )
    swing_map = {
        r.station_id: (float(r.swing), r.days)
        for r in swing_rows
        if r.days >= cfg.LITERBOARD_MIN_STABILITY_DAYS
    }
    swing_values = sorted(v[0] for v in swing_map.values())
    market_swing = swing_values[len(swing_values) // 2] if swing_values else None

    rows = []
    for stat in station_stats:
        swing_info = swing_map.get(stat.station_id)
        swing = swing_info[0] if swing_info else None
        ratio = swing / market_swing if swing is not None and market_swing else None
        station_hours = hours_by_station.get(stat.station_id, 0)
        rows.append(
            {
                "station_id": stat.station_id,
                "name": stat.name,
                "brand": stat.brand,
                "city": stat.city,
                "avg_price": round(float(stat.avg_price), 3),
                "min_price": round(float(stat.min_price), 3),
                "max_price": round(float(stat.max_price), 3),
                "daily_swing_cents": (
                    round(swing * 100, 1) if swing is not None else None
                ),
                "swing_vs_market": round(ratio, 2) if ratio is not None else None,
                "stability": _stability_label(ratio),
                "stability_days": swing_info[1] if swing_info else 0,
                "stability_window_days": cfg.LITERBOARD_STABILITY_DAYS,
                "cheapest_percentage": literboard.cheapest_percentage(
                    cheapest_counts.get(stat.station_id, 0),
                    total_hours,
                    station_hours,
                    opening_hours_weighted,
                ),
                "data_points": stat.data_points,
                "hours_with_data": station_hours,
                "days_with_data": stat.days_with_data,
                "window_hours": total_hours,
                "opening_hours_weighted": opening_hours_weighted,
            }
        )

    ranked, unranked = literboard.split_by_coverage(rows)
    ranked.sort(key=lambda r: r["avg_price"])
    unranked.sort(key=lambda r: r["avg_price"])
    for i, r in enumerate(ranked[:limit], start=1):
        r["ranked"], r["enough_data"], r["rank"] = True, True, i
    out = ranked[:limit]
    for r in unranked[: cfg.LITERBOARD_MAX_UNRANKED]:
        r["ranked"], r["enough_data"], r["rank"] = False, False, None
        out.append(r)
    return out


@router.get("/analytics/heatmap")
@limiter.limit("30/minute")
@ttl_cached(300)
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
            func.extract("dow", _local_ts()).label("dow_pg"),
            func.extract("hour", _local_ts()).label("hour_of_day"),
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
@ttl_cached(300)
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
