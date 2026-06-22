from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from limiter import limiter
from models import TrafficEvent, User
from routers.auth import require_current_user

router = APIRouter()

_SUMMARY_CACHE: dict[int, tuple[datetime, dict]] = {}
_SUMMARY_CACHE_SECONDS = 300
_TILE_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "osm_tiles"
_TILE_CACHE_ROOT = _TILE_CACHE_DIR.resolve()
_MAX_CACHED_TILES = 5000


def require_admin_user(user: User = Depends(require_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return user


def invalidate_summary_cache() -> None:
    _SUMMARY_CACHE.clear()


@router.get("/map-tiles/{z}/{x}/{y}.png", include_in_schema=False)
@limiter.limit("120/minute")
async def get_map_tile(request: Request, z: int, x: int, y: int):
    if z < 0 or z > 6:
        raise HTTPException(status_code=404, detail="Tile not found")

    max_index = 2**z
    if x < 0 or x >= max_index or y < 0 or y >= max_index:
        raise HTTPException(status_code=404, detail="Tile not found")

    tile_path = (_TILE_CACHE_ROOT / str(z) / str(x) / f"{y}.png").resolve()
    if _TILE_CACHE_ROOT not in tile_path.parents:
        raise HTTPException(status_code=404, detail="Tile not found")

    if tile_path.exists():
        return FileResponse(
            tile_path,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=2592000"},
        )

    tile_parent = tile_path.parent
    if _TILE_CACHE_ROOT not in tile_parent.parents and tile_parent != _TILE_CACHE_ROOT:
        raise HTTPException(status_code=404, detail="Tile not found")
    tile_parent.mkdir(parents=True, exist_ok=True)
    tile_url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        response = await client.get(
            tile_url,
            headers={"User-Agent": "FuelTracker/1.0 (admin map tile cache)"},
        )

    if response.status_code != 200:
        raise HTTPException(status_code=404, detail="Tile not found")

    if sum(1 for _ in _TILE_CACHE_DIR.rglob("*.png")) >= _MAX_CACHED_TILES:
        raise HTTPException(status_code=503, detail="Tile cache limit reached")

    tile_path.write_bytes(response.content)
    return FileResponse(
        tile_path,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=2592000"},
    )


@router.get("/traffic-summary")
async def get_traffic_summary(
    days: int = Query(default=30, ge=1, le=180),
    _: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    cached = _SUMMARY_CACHE.get(days)
    if cached and (now - cached[0]).total_seconds() < _SUMMARY_CACHE_SECONDS:
        return cached[1]

    since = now - timedelta(days=days)
    base_query = db.query(TrafficEvent).filter(TrafficEvent.visited_at >= since)

    total_visits = base_query.count()

    top_pages = [
        {"page": page, "count": count}
        for page, count in (
            db.query(TrafficEvent.page, func.count(TrafficEvent.id))
            .filter(TrafficEvent.visited_at >= since)
            .group_by(TrafficEvent.page)
            .order_by(func.count(TrafficEvent.id).desc(), TrafficEvent.page.asc())
            .limit(8)
            .all()
        )
    ]

    top_sources = [
        {"source": source, "count": count}
        for source, count in (
            db.query(TrafficEvent.source, func.count(TrafficEvent.id))
            .filter(TrafficEvent.visited_at >= since)
            .group_by(TrafficEvent.source)
            .order_by(func.count(TrafficEvent.id).desc(), TrafficEvent.source.asc())
            .limit(8)
            .all()
        )
    ]

    grouped_points = (
        db.query(
            TrafficEvent.country,
            TrafficEvent.city,
            TrafficEvent.latitude,
            TrafficEvent.longitude,
            func.count(TrafficEvent.id),
        )
        .filter(
            TrafficEvent.visited_at >= since,
            TrafficEvent.latitude.isnot(None),
            TrafficEvent.longitude.isnot(None),
        )
        .group_by(
            TrafficEvent.country,
            TrafficEvent.city,
            TrafficEvent.latitude,
            TrafficEvent.longitude,
        )
        .order_by(func.count(TrafficEvent.id).desc())
        .limit(100)
        .all()
    )

    map_points = []
    for country, city, latitude, longitude, count in grouped_points:
        pages = [
            page
            for page, _page_count in (
                db.query(TrafficEvent.page, func.count(TrafficEvent.id))
                .filter(
                    TrafficEvent.visited_at >= since,
                    TrafficEvent.country == country,
                    TrafficEvent.city == city,
                    TrafficEvent.latitude == latitude,
                    TrafficEvent.longitude == longitude,
                )
                .group_by(TrafficEvent.page)
                .order_by(func.count(TrafficEvent.id).desc(), TrafficEvent.page.asc())
                .limit(3)
                .all()
            )
        ]
        map_points.append(
            {
                "country": country,
                "city": city,
                "latitude": latitude,
                "longitude": longitude,
                "count": count,
                "pages": pages,
            }
        )

    recent_visits = [
        {
            "page": event.page,
            "path": event.path,
            "source": event.source,
            "country": event.country,
            "city": event.city,
            "visited_at": event.visited_at,
        }
        for event in (
            base_query.order_by(TrafficEvent.visited_at.desc()).limit(40).all()
        )
    ]

    summary = {
        "days": days,
        "cached_at": now,
        "total_visits": total_visits,
        "top_pages": top_pages,
        "top_sources": top_sources,
        "map_points": map_points,
        "recent_visits": recent_visits,
    }
    _SUMMARY_CACHE[days] = (now, summary)
    return summary
