"""Personal savings meter.

Savings are only claimed when they can be defended:

    saved = (reference_price - price_paid) * liters

The reference is chosen per refuel:

* ``area``   average of the same fuel across ALL tracked stations within
             +/-1 hour of the refuel (our own observations);
* ``nl``     the Dutch national average (CBS open data, Euro95 for E5/E10);
* ``manual`` a price the user enters.

If no reference exists for a session (too few observations, Dutch figure not
published yet) it is shown but NOT counted. Savings can be negative.
"""

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from limiter import limiter
from models import FuelPrice, NlFuelPrice, RefuelLog, Station, User
from routers.auth import require_current_user

router = APIRouter()

FUEL_COLUMNS = {"e5": FuelPrice.e5, "e10": FuelPrice.e10, "diesel": FuelPrice.diesel}
REFERENCE_WINDOW = timedelta(hours=1)
MIN_REFERENCE_ROWS = 20
MAX_LOGS_RETURNED = 200
MAX_LOGS_PER_USER = 5000
NL_MAX_AGE_DAYS = 10  # use the latest published Dutch figure at most this many days old
TZ = ZoneInfo("Europe/Berlin")
REFERENCE_LABELS = {
    "area": "Area average (tracked stations)",
    "nl": "Dutch average (CBS)",
    "manual": "Your reference price",
}


class RefuelCreate(BaseModel):
    fuel_type: str = Field(pattern="^(e5|e10|diesel)$")
    liters: float = Field(gt=0, le=200)
    price_per_liter: float = Field(ge=0.5, le=5.0)
    fueled_at: Optional[datetime] = None  # defaults to now
    station_id: Optional[str] = Field(default=None, max_length=64)
    reference_source: Literal["area", "nl", "manual"] = "area"
    manual_reference_price: Optional[float] = Field(default=None, ge=0.5, le=5.0)


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


def _nl_price(db: Session, fuel_type: str, at: datetime) -> Optional[float]:
    """Dutch average on the refuel day (or the latest published day before it)."""
    day = at.astimezone(TZ).date()
    row = (
        db.query(NlFuelPrice)
        .filter(
            NlFuelPrice.day <= day,
            NlFuelPrice.day >= day - timedelta(days=NL_MAX_AGE_DAYS),
        )
        .order_by(NlFuelPrice.day.desc())
        .first()
    )
    if row is None:
        return None
    value = row.diesel if fuel_type == "diesel" else row.euro95
    return float(value) if value is not None else None


def _resolve_reference(log: RefuelLog, db: Session) -> Optional[float]:
    if log.reference_source == "nl":
        return _nl_price(db, log.fuel_type, log.fueled_at)
    if log.reference_source == "manual":
        return log.manual_reference_price
    return _reference_price(db, log.fuel_type, log.fueled_at)


def _serialize(log: RefuelLog, db: Session) -> dict:
    ref = _resolve_reference(log, db)
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
        "reference_source": log.reference_source,
        "reference_label": REFERENCE_LABELS.get(
            log.reference_source, log.reference_source
        ),
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
            "Saved = (reference price − your price) × litres. The reference is the one "
            "you picked for each refuel: the area average of tracked stations (±1 hour), "
            "the Dutch national average (CBS), or your own price. Sessions without a "
            "reference are not counted."
        ),
        "sessions": items[:limit],
    }


@router.get("/nl-average")
def get_nl_average(db: Session = Depends(get_db)):
    """Latest published Dutch national average pump prices (CBS)."""
    row = db.query(NlFuelPrice).order_by(NlFuelPrice.day.desc()).first()
    if row is None:
        return {"available": False}
    return {
        "available": True,
        "day": row.day.isoformat(),
        "euro95": row.euro95,
        "diesel": row.diesel,
        "source": "CBS Statistics Netherlands, table 80416ENG",
        "note": "Euro95 is the Dutch equivalent of E10; it is used for both E5 and E10.",
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
        raise HTTPException(
            status_code=400, detail="Refuel time cannot be in the future"
        )
    if fueled_at < now - timedelta(days=365 * 5):
        raise HTTPException(
            status_code=400, detail="Refuel time is too far in the past"
        )

    if (
        body.station_id
        and not db.query(Station.id).filter(Station.id == body.station_id).first()
    ):
        raise HTTPException(status_code=400, detail="Unknown station")

    if body.reference_source == "manual" and body.manual_reference_price is None:
        raise HTTPException(status_code=400, detail="Enter your reference price")

    count = (
        db.query(func.count(RefuelLog.id)).filter(RefuelLog.user_id == user.id).scalar()
    )
    if count >= MAX_LOGS_PER_USER:
        raise HTTPException(status_code=400, detail="Refuel log limit reached")

    log = RefuelLog(
        user_id=user.id,
        station_id=body.station_id or None,
        fuel_type=body.fuel_type,
        liters=round(body.liters, 2),
        price_per_liter=round(body.price_per_liter, 3),
        fueled_at=fueled_at,
        reference_source=body.reference_source,
        manual_reference_price=(
            round(body.manual_reference_price, 3)
            if body.reference_source == "manual"
            else None
        ),
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
