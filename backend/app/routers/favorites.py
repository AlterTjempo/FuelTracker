from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

from database import get_db
from models import User, FavoriteStation, Station, FuelPrice
from routers.auth import require_current_user

router = APIRouter()


class FavoriteStationResponse(BaseModel):
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
    current_e5: Optional[float]
    current_e10: Optional[float]
    current_diesel: Optional[float]

    class Config:
        from_attributes = True


class AddFavoriteRequest(BaseModel):
    station_id: str


@router.get("/", response_model=list[FavoriteStationResponse])
def get_favorites(user: User = Depends(require_current_user), db: Session = Depends(get_db)):
    """Get all favorite stations for the current user with latest prices."""
    favorites = (
        db.query(FavoriteStation)
        .filter(FavoriteStation.user_id == user.id)
        .all()
    )

    results = []
    for fav in favorites:
        station = fav.station
        if not station:
            continue

        # Get latest price for this station
        latest_price = (
            db.query(FuelPrice)
            .filter(FuelPrice.station_id == station.id)
            .order_by(FuelPrice.timestamp.desc())
            .first()
        )

        results.append(FavoriteStationResponse(
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
            current_e5=latest_price.e5 if latest_price else None,
            current_e10=latest_price.e10 if latest_price else None,
            current_diesel=latest_price.diesel if latest_price else None,
        ))

    return results


@router.post("/", status_code=status.HTTP_201_CREATED)
def add_favorite(request: AddFavoriteRequest, user: User = Depends(require_current_user), db: Session = Depends(get_db)):
    """Add a station to favorites."""
    # Check station exists
    station = db.query(Station).filter(Station.id == request.station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")

    # Check if already favorited
    existing = (
        db.query(FavoriteStation)
        .filter(FavoriteStation.user_id == user.id, FavoriteStation.station_id == request.station_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Station already in favorites")

    fav = FavoriteStation(user_id=user.id, station_id=request.station_id)
    db.add(fav)
    db.commit()
    return {"message": "Station added to favorites"}


@router.delete("/{station_id}", status_code=status.HTTP_200_OK)
def remove_favorite(station_id: str, user: User = Depends(require_current_user), db: Session = Depends(get_db)):
    """Remove a station from favorites."""
    fav = (
        db.query(FavoriteStation)
        .filter(FavoriteStation.user_id == user.id, FavoriteStation.station_id == station_id)
        .first()
    )
    if not fav:
        raise HTTPException(status_code=404, detail="Station not in favorites")

    db.delete(fav)
    db.commit()
    return {"message": "Station removed from favorites"}
