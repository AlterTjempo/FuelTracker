from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from models import Station


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


@router.get("/", response_model=List[StationResponse])
def get_stations(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    brand: Optional[str] = None,
    city: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get list of all stations with optional filtering"""
    query = db.query(Station)
    
    if brand:
        query = query.filter(Station.brand.ilike(f"%{brand}%"))
    if city:
        query = query.filter(Station.city.ilike(f"%{city}%"))
    
    stations = query.offset(offset).limit(limit).all()
    return stations


@router.get("/{station_id}", response_model=StationResponse)
def get_station(station_id: str, db: Session = Depends(get_db)):
    """Get details of a specific station"""
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Station not found")
    return station
