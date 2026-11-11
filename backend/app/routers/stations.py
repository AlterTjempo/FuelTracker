from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone

from database import get_db
from models import Station, FuelPrice

router = APIRouter()


class StationResponse(BaseModel):
    id: str
    name: str
    brand: Optional[str]
    street: Optional[str]
    house_number: Optional[str]
    post_code: Optional[str]
    city: Optional[str]
    latitude: float
    longitude: float
    is_open: bool
    first_seen: datetime
    last_updated: datetime

    class Config:
        from_attributes = True


def _sanitize_like(value: str) -> str:
    """Escape special characters for LIKE/ILIKE patterns to prevent wildcard injection."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/", response_model=List[StationResponse])
def get_stations(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    brand: Optional[str] = Query(None, max_length=100),
    city: Optional[str] = Query(None, max_length=100),
    db: Session = Depends(get_db),
):
    """Get list of all stations with optional filtering"""
    query = db.query(Station)

    if brand:
        query = query.filter(
            Station.brand.ilike(f"%{_sanitize_like(brand)}%", escape="\\")
        )
    if city:
        query = query.filter(
            Station.city.ilike(f"%{_sanitize_like(city)}%", escape="\\")
        )

    stations = query.offset(offset).limit(limit).all()
    return stations


@router.get("/{station_id}", response_model=StationResponse)
def get_station(station_id: str, db: Session = Depends(get_db)):
    """Get details of a specific station"""
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    return station


class StationDetailResponse(BaseModel):
    id: str
    name: str
    brand: Optional[str]
    street: Optional[str]
    house_number: Optional[str]
    post_code: Optional[str]
    city: Optional[str]
    latitude: float
    longitude: float
    is_open: bool
    first_seen: datetime
    last_updated: datetime
    current_e5: Optional[float]
    current_e10: Optional[float]
    current_diesel: Optional[float]
    avg_e5: Optional[float]
    avg_e10: Optional[float]
    avg_diesel: Optional[float]
    min_e5: Optional[float]
    min_e10: Optional[float]
    min_diesel: Optional[float]
    max_e5: Optional[float]
    max_e10: Optional[float]
    max_diesel: Optional[float]
    price_count: int

    class Config:
        from_attributes = True


@router.get("/{station_id}/detail", response_model=StationDetailResponse)
def get_station_detail(
    station_id: str,
    hours: int = Query(168, ge=1, le=1000000),
    db: Session = Depends(get_db),
):
    """Get detailed station info with average prices over a time period"""
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")

    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Get price statistics
    stats = (
        db.query(
            func.avg(FuelPrice.e5).label("avg_e5"),
            func.avg(FuelPrice.e10).label("avg_e10"),
            func.avg(FuelPrice.diesel).label("avg_diesel"),
            func.min(FuelPrice.e5).label("min_e5"),
            func.min(FuelPrice.e10).label("min_e10"),
            func.min(FuelPrice.diesel).label("min_diesel"),
            func.max(FuelPrice.e5).label("max_e5"),
            func.max(FuelPrice.e10).label("max_e10"),
            func.max(FuelPrice.diesel).label("max_diesel"),
            func.count(FuelPrice.id).label("price_count"),
        )
        .filter(FuelPrice.station_id == station_id, FuelPrice.timestamp >= since)
        .first()
    )

    # Get latest price
    latest = (
        db.query(FuelPrice)
        .filter(FuelPrice.station_id == station_id)
        .order_by(FuelPrice.timestamp.desc())
        .first()
    )

    return StationDetailResponse(
        id=station.id,
        name=station.name,
        brand=station.brand,
        street=station.street,
        house_number=station.house_number,
        post_code=station.post_code,
        city=station.city,
        latitude=station.latitude,
        longitude=station.longitude,
        is_open=station.is_open,
        first_seen=station.first_seen,
        last_updated=station.last_updated,
        current_e5=latest.e5 if latest else None,
        current_e10=latest.e10 if latest else None,
        current_diesel=latest.diesel if latest else None,
        avg_e5=round(stats.avg_e5, 3) if stats.avg_e5 is not None else None,
        avg_e10=round(stats.avg_e10, 3) if stats.avg_e10 is not None else None,
        avg_diesel=round(stats.avg_diesel, 3) if stats.avg_diesel is not None else None,
        min_e5=stats.min_e5,
        min_e10=stats.min_e10,
        min_diesel=stats.min_diesel,
        max_e5=stats.max_e5,
        max_e10=stats.max_e10,
        max_diesel=stats.max_diesel,
        price_count=stats.price_count or 0,
    )
