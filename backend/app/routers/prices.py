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
    db: Session = Depends(get_db)
):
    """Get the most recent prices for all stations"""
    # Subquery to get the latest timestamp for each station
    subquery = db.query(
        FuelPrice.station_id,
        func.max(FuelPrice.timestamp).label('max_timestamp')
    ).group_by(FuelPrice.station_id).subquery()
    
    # Join to get the full price records
    query = db.query(FuelPrice, Station).join(
        subquery,
        and_(
            FuelPrice.station_id == subquery.c.station_id,
            FuelPrice.timestamp == subquery.c.max_timestamp
        )
    ).join(Station, FuelPrice.station_id == Station.id)
    
    results = query.limit(limit).all()
    
    response = []
    for price, station in results:
        response.append(CurrentPriceResponse(
            station_id=station.id,
            station_name=station.name,
            brand=station.brand,
            city=station.city,
            e5=price.e5,
            e10=price.e10,
            diesel=price.diesel,
            timestamp=price.timestamp
        ))
    
    return response


@router.get("/lowest", response_model=List[LowestPriceResponse])
def get_lowest_prices(
    fuel_type: str = Query("diesel", regex="^(e5|e10|diesel)$"),
    limit: int = Query(10, ge=1, le=50),
    hours: int = Query(24, ge=1, le=168),  # Last N hours
    db: Session = Depends(get_db)
):
    """Get the lowest fuel prices in the specified timeframe"""
    since = datetime.utcnow() - timedelta(hours=hours)
    
    # Get the fuel type column
    fuel_column = getattr(FuelPrice, fuel_type)
    
    # Query for lowest prices
    query = db.query(
        FuelPrice.station_id,
        Station.name,
        Station.city,
        func.min(fuel_column).label('min_price'),
        func.max(FuelPrice.timestamp).label('latest_timestamp')
    ).join(Station, FuelPrice.station_id == Station.id).filter(
        FuelPrice.timestamp >= since,
        fuel_column.isnot(None)
    ).group_by(
        FuelPrice.station_id,
        Station.name,
        Station.city
    ).order_by(
        func.min(fuel_column)
    ).limit(limit)
    
    results = query.all()
    
    response = []
    for station_id, name, city, min_price, timestamp in results:
        response.append(LowestPriceResponse(
            fuel_type=fuel_type,
            price=min_price,
            station_id=station_id,
            station_name=name,
            city=city,
            timestamp=timestamp
        ))
    
    return response


@router.get("/station/{station_id}/history", response_model=List[PriceResponse])
def get_station_price_history(
    station_id: str,
    hours: int = Query(24, ge=1, le=720),  # Up to 30 days
    db: Session = Depends(get_db)
):
    """Get price history for a specific station"""
    since = datetime.utcnow() - timedelta(hours=hours)
    
    prices = db.query(FuelPrice).filter(
        FuelPrice.station_id == station_id,
        FuelPrice.timestamp >= since
    ).order_by(FuelPrice.timestamp.desc()).all()
    
    if not prices:
        raise HTTPException(status_code=404, detail="No price data found for this station")
    
    return prices


@router.get("/station/{station_id}/stats", response_model=List[PriceStatsResponse])
def get_station_stats(
    station_id: str,
    hours: int = Query(168, ge=1, le=720),  # Default 7 days
    db: Session = Depends(get_db)
):
    """Get price statistics for a station"""
    since = datetime.utcnow() - timedelta(hours=hours)
    
    stats = []
    
    for fuel_type in ['e5', 'e10', 'diesel']:
        fuel_column = getattr(FuelPrice, fuel_type)
        
        result = db.query(
            func.min(fuel_column).label('min_price'),
            func.max(fuel_column).label('max_price'),
            func.avg(fuel_column).label('avg_price')
        ).filter(
            FuelPrice.station_id == station_id,
            FuelPrice.timestamp >= since,
            fuel_column.isnot(None)
        ).first()
        
        if result and result.min_price is not None:
            # Get current price
            current = db.query(fuel_column).filter(
                FuelPrice.station_id == station_id
            ).order_by(FuelPrice.timestamp.desc()).first()
            
            stats.append(PriceStatsResponse(
                fuel_type=fuel_type,
                min_price=float(result.min_price),
                max_price=float(result.max_price),
                avg_price=float(result.avg_price),
                current_price=float(current[0]) if current and current[0] else None
            ))
    
    return stats


@router.get("/history/all")
def get_all_prices_history(
    fuel_type: str = Query("diesel", regex="^(e5|e10|diesel)$"),
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db)
):
    """Get average price history across all stations for graphing"""
    since = datetime.utcnow() - timedelta(hours=hours)
    fuel_column = getattr(FuelPrice, fuel_type)
    
    # Group by hourly intervals
    results = db.query(
        func.date_trunc('hour', FuelPrice.timestamp).label('hour'),
        func.avg(fuel_column).label('avg_price'),
        func.min(fuel_column).label('min_price'),
        func.max(fuel_column).label('max_price'),
        func.count(FuelPrice.id).label('sample_count')
    ).filter(
        FuelPrice.timestamp >= since,
        fuel_column.isnot(None)
    ).group_by('hour').order_by('hour').all()
    
    return [
        {
            "timestamp": r.hour,
            "avg_price": float(r.avg_price) if r.avg_price else None,
            "min_price": float(r.min_price) if r.min_price else None,
            "max_price": float(r.max_price) if r.max_price else None,
            "sample_count": r.sample_count
        }
        for r in results
    ]
