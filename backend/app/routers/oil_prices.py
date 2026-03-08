from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone

from database import get_db
from models import OilPrice

router = APIRouter()


class OilPriceResponse(BaseModel):
    id: int
    timestamp: datetime
    price_usd_per_barrel: float
    price_eur_per_barrel: float
    price_eur_per_liter: float

    class Config:
        from_attributes = True


@router.get("/latest", response_model=Optional[OilPriceResponse])
def get_latest_oil_price(db: Session = Depends(get_db)):
    """Get the most recent Brent crude oil price entry."""
    return db.query(OilPrice).order_by(OilPrice.timestamp.desc()).first()


@router.get("/history", response_model=List[OilPriceResponse])
def get_oil_price_history(
    hours: int = Query(168, ge=1, le=1000000),
    db: Session = Depends(get_db),
):
    """Get Brent crude oil price history for the given number of hours."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    return (
        db.query(OilPrice)
        .filter(OilPrice.timestamp >= since)
        .order_by(OilPrice.timestamp.asc())
        .all()
    )
