from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from cache import cached
from config import settings
from database import get_db
from limiter import limiter
from models import (
    EnergyNews,
    FavoriteStation,
    FuelPrice,
    NlFuelPrice,
    OilPrice,
    RefuelLog,
    Station,
    TrafficEvent,
    User,
)
from services.admin_stats import (
    age_seconds,
    coverage_ratio,
    freshness_status,
    mask_email,
)
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


# --- System overview (read-only) ---------------------------------------------
#
# NOTE: there is deliberately no endpoint here that creates, promotes, demotes
# or deletes users. Admin rights are granted ONLY by setting `is_admin` in the
# database by hand.

EXPECTED_CYCLES_PER_DAY = 96  # fuel prices are collected every 15 minutes
DEFAULT_JWT_SECRET = "overwritten-in-config-env-change-me"
BERLIN = "Europe/Berlin"
_OVERVIEW_TABLES = [
    "fuel_prices",
    "traffic_events",
    "energy_news",
    "oil_prices",
    "nl_fuel_prices",
    "stations",
    "users",
    "favorite_stations",
    "refuel_logs",
    "visitor_location_cache",
]


def _collector_entry(label, latest, ok_within, warn_within, now, **extra):
    age = age_seconds(latest, now)
    return {
        "label": label,
        "latest": latest,
        "age_seconds": age,
        "status": freshness_status(age, ok_within, warn_within),
        **extra,
    }


def _build_system(app, db: Session) -> dict:
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    fuel_latest, fuel_total = db.query(
        func.max(FuelPrice.timestamp), func.count(FuelPrice.id)
    ).one()
    fuel_24h, cycles_24h = (
        db.query(
            func.count(FuelPrice.id), func.count(func.distinct(FuelPrice.timestamp))
        )
        .filter(FuelPrice.timestamp >= day_ago)
        .one()
    )
    stations_in_latest = (
        db.query(func.count(FuelPrice.id))
        .filter(FuelPrice.timestamp == fuel_latest)
        .scalar()
        if fuel_latest
        else 0
    )
    stations_total = db.query(func.count(Station.id)).scalar()
    first_fuel = db.query(func.min(FuelPrice.timestamp)).scalar()

    oil_latest, oil_total = db.query(
        func.max(OilPrice.timestamp), func.count(OilPrice.id)
    ).one()
    oil_24h = (
        db.query(func.count(OilPrice.id)).filter(OilPrice.timestamp >= day_ago).scalar()
    )
    oil_last = db.query(OilPrice).order_by(OilPrice.timestamp.desc()).first()

    news_latest, news_total = db.query(
        func.max(EnergyNews.fetched_at), func.count(EnergyNews.link)
    ).one()
    news_24h = (
        db.query(func.count(EnergyNews.link))
        .filter(EnergyNews.fetched_at >= day_ago)
        .scalar()
    )
    news_sources = [
        {"source": src, "count": n}
        for src, n in db.query(EnergyNews.source, func.count(EnergyNews.link))
        .filter(EnergyNews.fetched_at >= now - timedelta(days=7))
        .group_by(EnergyNews.source)
        .order_by(func.count(EnergyNews.link).desc())
        .all()
    ]

    nl_latest_day, nl_total = db.query(
        func.max(NlFuelPrice.day), func.count(NlFuelPrice.day)
    ).one()
    nl_latest = (
        datetime.combine(nl_latest_day, datetime.min.time(), tzinfo=timezone.utc)
        if nl_latest_day
        else None
    )

    # Collection history: completed 15-minute cycles per local day, last 60 days.
    local_day = func.date(func.timezone(BERLIN, FuelPrice.timestamp))
    per_day = {
        d: n
        for d, n in db.query(local_day, func.count(func.distinct(FuelPrice.timestamp)))
        .filter(FuelPrice.timestamp >= now - timedelta(days=61))
        .group_by(local_day)
        .all()
    }
    today = now.astimezone(ZoneInfo(BERLIN)).date()
    history = []
    for i in range(59, -1, -1):
        d = today - timedelta(days=i)
        cycles = per_day.get(d, 0)
        history.append(
            {
                "date": d.isoformat(),
                "cycles": cycles,
                "coverage": round(coverage_ratio(cycles, EXPECTED_CYCLES_PER_DAY), 3),
            }
        )
    covered_days = sum(1 for h in history if h["cycles"] > 0)
    avg_coverage = (
        round(sum(h["coverage"] for h in history if h["cycles"] > 0) / covered_days, 3)
        if covered_days
        else 0.0
    )

    scheduler = getattr(app.state, "scheduler", None)
    jobs = []
    if scheduler is not None:
        for job in scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "next_run": getattr(job, "next_run_time", None),
                    "trigger": str(job.trigger),
                }
            )

    db_size = db.execute(text("select pg_database_size(current_database())")).scalar()
    tables = []
    for name in _OVERVIEW_TABLES:
        size = db.execute(
            text("select pg_total_relation_size(to_regclass(:t))"), {"t": name}
        ).scalar()
        if size is not None:
            tables.append({"table": name, "bytes": int(size)})
    tables.sort(key=lambda t: -t["bytes"])

    checks = [
        {
            "id": "jwt",
            "label": "Login signing secret is custom and at least 32 characters",
            "ok": settings.JWT_SECRET_KEY != DEFAULT_JWT_SECRET
            and len(settings.JWT_SECRET_KEY) >= 32,
            "detail": "Set JWT_SECRET_KEY in config.env to a long random value.",
        },
        {
            "id": "docs",
            "label": "Public API docs (/docs) disabled",
            "ok": not settings.ENABLE_DOCS,
            "detail": "Set ENABLE_DOCS=false in production.",
        },
        {
            "id": "captcha",
            "label": "Sign-up CAPTCHA configured",
            "ok": bool(settings.RECAPTCHA_SECRET_KEY),
            "detail": "Set RECAPTCHA_SECRET_KEY, otherwise registration is not bot-protected.",
        },
        {
            "id": "geoip",
            "label": "Visitor IPs are not sent to a third-party geolocation service",
            "ok": not settings.ENABLE_IP_GEOLOCATION,
            "detail": "ENABLE_IP_GEOLOCATION=true sends visitor IP addresses to ipapi.co; disclose it in your privacy notice.",
        },
        {
            "id": "cors",
            "label": "CORS restricted to specific origins",
            "ok": "*" not in settings.get_allowed_origins,
            "detail": "ALLOWED_ORIGINS should list your site, not *.",
        },
        {
            "id": "tankerkoenig",
            "label": "Tankerkönig API key present",
            "ok": bool(settings.TANKERKONIG_API_KEY),
            "detail": "TANKERKONIG_API_KEY is required for price collection.",
        },
    ]

    return {
        "generated_at": now,
        "collectors": {
            "fuel": _collector_entry(
                "Fuel prices (Tankerkönig, every 15 min)",
                fuel_latest,
                30 * 60,
                2 * 3600,
                now,
                rows_total=fuel_total,
                rows_24h=fuel_24h,
                cycles_24h=cycles_24h,
                expected_cycles_24h=EXPECTED_CYCLES_PER_DAY,
                stations_in_latest_cycle=stations_in_latest,
                stations_known=stations_total,
                first_observation=first_fuel,
            ),
            "oil": _collector_entry(
                "Brent crude (hourly)",
                oil_latest,
                2 * 3600,
                6 * 3600,
                now,
                rows_total=oil_total,
                rows_24h=oil_24h,
                last_usd_per_barrel=oil_last.price_usd_per_barrel if oil_last else None,
            ),
            "news": _collector_entry(
                "Energy news (hourly)",
                news_latest,
                3 * 3600,
                12 * 3600,
                now,
                rows_total=news_total,
                rows_24h=news_24h,
                sources_7d=news_sources,
            ),
            "nl": _collector_entry(
                "Dutch averages (CBS, weekly)",
                nl_latest,
                10 * 86400,
                21 * 86400,
                now,
                rows_total=nl_total,
            ),
        },
        "collection_history": history,
        "collection_summary": {
            "days_with_data": covered_days,
            "days_without_data": 60 - covered_days,
            "avg_coverage_on_days_with_data": avg_coverage,
        },
        "scheduler_jobs": jobs,
        "database": {"size_bytes": int(db_size or 0), "tables": tables},
        "security_checks": checks,
        "cache_note": "Overview is cached for 30 seconds.",
    }


@router.get("/system")
def get_system_overview(
    request: Request,
    _: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """Collector health, data coverage, database size and security settings."""
    return cached(("admin-system",), 30, lambda: _build_system(request.app, db))


@router.get("/users")
def get_users_overview(
    _: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """Read-only account overview. Emails are masked; no write actions exist."""
    now = datetime.now(timezone.utc)

    fav = (
        db.query(FavoriteStation.user_id.label("uid"), func.count().label("n"))
        .group_by(FavoriteStation.user_id)
        .subquery()
    )
    ref = (
        db.query(RefuelLog.user_id.label("uid"), func.count().label("n"))
        .group_by(RefuelLog.user_id)
        .subquery()
    )
    rows = (
        db.query(User, func.coalesce(fav.c.n, 0), func.coalesce(ref.c.n, 0))
        .outerjoin(fav, fav.c.uid == User.id)
        .outerjoin(ref, ref.c.uid == User.id)
        .order_by(User.created_at.desc())
        .limit(100)
        .all()
    )

    total = db.query(func.count(User.id)).scalar()
    admins = db.query(func.count(User.id)).filter(User.is_admin.is_(True)).scalar()
    new_7d = (
        db.query(func.count(User.id))
        .filter(User.created_at >= now - timedelta(days=7))
        .scalar()
    )
    new_30d = (
        db.query(func.count(User.id))
        .filter(User.created_at >= now - timedelta(days=30))
        .scalar()
    )
    with_favorites = db.query(
        func.count(func.distinct(FavoriteStation.user_id))
    ).scalar()
    with_refuels = db.query(func.count(func.distinct(RefuelLog.user_id))).scalar()
    refuels_total = db.query(func.count(RefuelLog.id)).scalar()

    return {
        "summary": {
            "total": total,
            "admins": admins,
            "new_7d": new_7d,
            "new_30d": new_30d,
            "with_favorites": with_favorites,
            "with_refuels": with_refuels,
            "refuels_total": refuels_total,
        },
        "users": [
            {
                "username": u.username,
                "email": mask_email(u.email),
                "is_admin": u.is_admin,
                "created_at": u.created_at,
                "favorites": int(favs),
                "refuels": int(refs),
            }
            for u, favs, refs in rows
        ],
        "shown": len(rows),
        "note": (
            "Read-only. Admin rights can only be granted by setting is_admin in "
            "the database."
        ),
    }
