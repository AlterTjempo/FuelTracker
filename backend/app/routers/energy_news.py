from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from models import EnergyNews

router = APIRouter()


class EnergyNewsResponse(BaseModel):
    id: int
    title: str
    link: str
    source: str
    published_at: Optional[datetime]
    summary: Optional[str]
    fetched_at: datetime

    class Config:
        from_attributes = True


@router.get("/latest", response_model=List[EnergyNewsResponse])
def get_latest_news(
    limit: int = Query(5, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Return the most recent energy news articles, ordered by publication date."""
    return (
        db.query(EnergyNews)
        .order_by(
            EnergyNews.published_at.desc().nullslast(),
            EnergyNews.fetched_at.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
