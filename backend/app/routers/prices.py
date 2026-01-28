from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta

from database import get_db
from models import FuelPrice, Station

router = APIRouter()


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
    fuel_type: Optional[str] = Query(None, regex="^(e5|e10|diesel)$"),
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
    fuel_type: str = Query("diesel", regex="^(e5|e10|diesel)$"),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Get the current lowest fuel prices (from the latest data available for each station)"""
    # Get the fuel type column
    fuel_column = getattr(FuelPrice, fuel_type)

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
    fuel_type: str = Query("diesel", regex="^(e5|e10|diesel)$"),
    limit: int = Query(10, ge=1, le=50),
    hours: int = Query(24, ge=1, le=168),  # Last N hours
    db: Session = Depends(get_db),
):
    """Get the lowest fuel prices in the specified timeframe"""
    since = datetime.utcnow() - timedelta(hours=hours)

    # Get the fuel type column
    fuel_column = getattr(FuelPrice, fuel_type)

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
    since = datetime.utcnow() - timedelta(hours=hours)

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
    since = datetime.utcnow() - timedelta(hours=hours)

    stats = []

    for fuel_type in ["e5", "e10", "diesel"]:
        fuel_column = getattr(FuelPrice, fuel_type)

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
def get_all_prices_history(
    fuel_type: str = Query("diesel", regex="^(e5|e10|diesel)$"),
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
):
    """Get average price history across all stations for graphing"""
    since = datetime.utcnow() - timedelta(hours=hours)
    fuel_column = getattr(FuelPrice, fuel_type)

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
def get_time_patterns(
    fuel_type: str = Query("e5", regex="^(e5|e10|diesel)$"),
    hours: int = Query(168, ge=24, le=720),  # At least 24 hours
    db: Session = Depends(get_db),
):
    """Get cheapest day and time patterns"""
    since = datetime.utcnow() - timedelta(hours=hours)
    fuel_column = getattr(FuelPrice, fuel_type)

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
def get_go_now_indicator(
    fuel_type: str = Query("e5", regex="^(e5|e10|diesel)$"),
    db: Session = Depends(get_db),
):
    """Compare current average price to 24h average"""
    fuel_column = getattr(FuelPrice, fuel_type)

    # Get current average (last hour)
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    current_avg = (
        db.query(func.avg(fuel_column))
        .filter(FuelPrice.timestamp >= one_hour_ago, fuel_column.isnot(None))
        .scalar()
    )

    # Get 24h average
    one_day_ago = datetime.utcnow() - timedelta(hours=24)
    day_avg = (
        db.query(func.avg(fuel_column))
        .filter(FuelPrice.timestamp >= one_day_ago, fuel_column.isnot(None))
        .scalar()
    )

    if not current_avg or not day_avg:
        return {
            "current_price": None,
            "avg_24h": None,
            "difference": None,
            "percentage": None,
            "recommendation": "insufficient_data",
        }

    current = float(current_avg)
    average = float(day_avg)
    diff = current - average
    percentage = (diff / average) * 100

    # Determine recommendation
    if percentage <= -3:
        recommendation = "excellent"  # More than 3% cheaper
    elif percentage <= -1:
        recommendation = "good"  # 1-3% cheaper
    elif percentage <= 1:
        recommendation = "neutral"  # Within 1%
    elif percentage <= 3:
        recommendation = "wait"  # 1-3% more expensive
    else:
        recommendation = "avoid"  # More than 3% more expensive

    return {
        "current_price": round(current, 3),
        "avg_24h": round(average, 3),
        "difference": round(diff, 3),
        "percentage": round(percentage, 2),
        "recommendation": recommendation,
    }


@router.get("/analytics/top-stations")
def get_top_stations(
    fuel_type: str = Query("e5", regex="^(e5|e10|diesel)$"),
    hours: int = Query(168, ge=24, le=720),
    limit: int = Query(3, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """Get top stations by average price and consistency"""
    since = datetime.utcnow() - timedelta(hours=hours)
    fuel_column = getattr(FuelPrice, fuel_type)

    # Get station statistics
    station_stats = (
        db.query(
            FuelPrice.station_id,
            Station.name,
            Station.brand,
            Station.city,
            func.avg(fuel_column).label("avg_price"),
            func.min(fuel_column).label("min_price"),
            func.max(fuel_column).label("max_price"),
            func.stddev(fuel_column).label("volatility"),
            func.count(FuelPrice.id).label("data_points"),
        )
        .join(Station, FuelPrice.station_id == Station.id)
        .filter(FuelPrice.timestamp >= since, fuel_column.isnot(None))
        .group_by(FuelPrice.station_id, Station.name, Station.brand, Station.city)
        .order_by(func.avg(fuel_column))
        .limit(limit)
        .all()
    )

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

        results.append(
            {
                "station_id": stat.station_id,
                "name": stat.name,
                "brand": stat.brand,
                "city": stat.city,
                "avg_price": round(float(stat.avg_price), 3),
                "min_price": round(float(stat.min_price), 3),
                "max_price": round(float(stat.max_price), 3),
                "volatility": round(float(stat.volatility or 0), 4),
                "cheapest_percentage": round(cheapest_percentage, 1),
                "data_points": stat.data_points,
            }
        )

    return results


@router.get("/analytics/lowest-ever")
def get_lowest_price_ever(
    fuel_type: str = Query("e5", regex="^(e5|e10|diesel)$"),
    db: Session = Depends(get_db),
):
    """Get the lowest price ever recorded with station and timestamp"""
    fuel_column = getattr(FuelPrice, fuel_type)

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
    price_value = getattr(price_record, fuel_type)

    return {
        "price": round(float(price_value), 3),
        "timestamp": price_record.timestamp,
        "station_id": station.id,
        "station_name": station.name,
        "brand": station.brand,
        "city": station.city,
    }
