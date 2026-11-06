"""Personal savings meter.

Savings are only claimed when they can be defended:

    saved = (reference_price - price_paid) * liters

``reference_price`` is the average price of the same fuel across ALL tracked
stations within +/-1 hour of the refuel, taken from our own observations.
If we have too few observations around that moment, no reference exists and
the session is shown but NOT counted towards savings. Savings can be negative
(you paid more than the area average) and are reported as such.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from limiter import limiter
from models import FuelPrice, RefuelLog, Station, User
from routers.auth import require_current_user

router = APIRouter()

FUEL_COLUMNS = {"e5": FuelPrice.e5, "e10": FuelPrice.e10, "diesel": FuelPrice.diesel}
REFERENCE_WINDOW = timedelta(hours=1)
MIN_REFERENCE_ROWS = 20
MAX_LOGS_RETURNED = 200
MAX_LOGS_PER_USER = 5000


class RefuelCreate(BaseModel):
    fuel_type: str = Field(pattern="^(e5|e10|diesel)$")
    liters: float = Field(gt=0, le=200)
    price_per_liter: float = Field(ge=0.5, le=5.0)
    fueled_at: Optional[datetime] = None  # defaults to now
    station_id: Optional[str] = Field(default=None, max_length=64)


def _reference_price(db: Session, fuel_type: str, at: datetime) -> Optional[float]:
    col = FUEL_COLUMNS[fuel_type]
    avg, n = (
        db.query(func.avg(col), func.count(col))
        .filter(
            FuelPrice.timestamp >= at - REFERENCE_WINDOW,
            FuelPrice.timestamp <= at + REFERENCE_WINDOW,
            col.isnot(None),
        )
        .one()
    )
    if n is None or n < MIN_REFERENCE_ROWS or avg is None:
        return None
    return float(avg)


def _serialize(log: RefuelLog, db: Session) -> dict:
    ref = _reference_price(db, log.fuel_type, log.fueled_at)
    saved = (ref - log.price_per_liter) * log.liters if ref is not None else None
    return {
        "id": log.id,
        "fuel_type": log.fuel_type,
        "liters": log.liters,
        "price_per_liter": log.price_per_liter,
        "total_cost": round(log.liters * log.price_per_liter, 2),
        "fueled_at": log.fueled_at,
        "station_id": log.station_id,
        "station_name": log.station.name if log.station else None,
        "reference_price": round(ref, 3) if ref is not None else None,
        "saved": round(saved, 2) if saved is not None else None,
    }


@router.get("")
@router.get("/", include_in_schema=False)
def get_savings(
    limit: int = Query(50, ge=1, le=MAX_LOGS_RETURNED),
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    """Summary over all of the user's sessions + the latest `limit` sessions."""
    logs = (
        db.query(RefuelLog)
        .filter(RefuelLog.user_id == user.id)
        .order_by(RefuelLog.fueled_at.desc())
        .limit(MAX_LOGS_PER_USER)
        .all()
    )
    items = [_serialize(log, db) for log in logs]
    counted = [i for i in items if i["saved"] is not None]
    return {
        "summary": {
            "sessions": len(items),
            "liters": round(sum(i["liters"] for i in items), 1),
            "total_spent": round(sum(i["total_cost"] for i in items), 2),
            "saved": round(sum(i["saved"] for i in counted), 2),
            "sessions_with_reference": len(counted),
            "sessions_without_reference": len(items) - len(counted),
        },
        "method": (
            "Saved = (average price of the same fuel at all tracked stations within "
            "±1 hour of your refuel − your price) × litres. Sessions without enough "
            "price data around that time are not counted."
        ),
        "sessions": items[:limit],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED, include_in_schema=False)
@limiter.limit("30/minute")
def add_refuel(
    request: Request,
    body: RefuelCreate,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    fueled_at = body.fueled_at or now
    if fueled_at.tzinfo is None:
        fueled_at = fueled_at.replace(tzinfo=timezone.utc)
    if fueled_at > now + timedelta(minutes=5):
        raise HTTPException(status_code=400, detail="Refuel time cannot be in the future")
    if fueled_at < now - timedelta(days=365 * 5):
        raise HTTPException(status_code=400, detail="Refuel time is too far in the past")

    if body.station_id and not db.query(Station.id).filter(Station.id == body.station_id).first():
        raise HTTPException(status_code=400, detail="Unknown station")

    count = db.query(func.count(RefuelLog.id)).filter(RefuelLog.user_id == user.id).scalar()
    if count >= MAX_LOGS_PER_USER:
        raise HTTPException(status_code=400, detail="Refuel log limit reached")

    log = RefuelLog(
        user_id=user.id,
        station_id=body.station_id or None,
        fuel_type=body.fuel_type,
        liters=round(body.liters, 2),
        price_per_liter=round(body.price_per_liter, 3),
        fueled_at=fueled_at,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return _serialize(log, db)


@router.delete("/{log_id}")
def delete_refuel(
    log_id: int,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    log = (
        db.query(RefuelLog)
        .filter(RefuelLog.id == log_id, RefuelLog.user_id == user.id)
        .first()
    )
    if not log:
        raise HTTPException(status_code=404, detail="Refuel not found")
    db.delete(log)
    db.commit()
    return {"message": "Deleted"}
