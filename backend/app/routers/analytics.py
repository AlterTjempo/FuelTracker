from datetime import datetime, timedelta, timezone
from hashlib import sha256
from ipaddress import ip_address
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from limiter import limiter
from models import TrafficEvent, VisitorLocationCache
from routers.admin import invalidate_summary_cache

router = APIRouter()


class PageViewRequest(BaseModel):
    page: str
    path: str = "/"
    referrer: str | None = None


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    return request.client.host if request.client else "unknown"


def _is_public_ip(value: str) -> bool:
    try:
        parsed = ip_address(value)
    except ValueError:
        return False
    return not (
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_unspecified
    )


def _normalize_source(referrer: str | None) -> str:
    if not referrer:
        return "direct"

    try:
        parsed = urlparse(referrer)
    except ValueError:
        return "direct"

    host = parsed.netloc.strip()
    return host or "direct"


async def _resolve_location(client_ip: str, db: Session) -> dict:
    ip_hash = sha256(client_ip.encode("utf-8")).hexdigest()
    cached = db.query(VisitorLocationCache).filter(VisitorLocationCache.ip_hash == ip_hash).first()
    now = datetime.now(timezone.utc)

    if cached and cached.resolved_at >= now - timedelta(days=30):
        return {
            "country": cached.country,
            "region": cached.region,
            "city": cached.city,
            "latitude": cached.latitude,
            "longitude": cached.longitude,
        }

    if not _is_public_ip(client_ip):
        location = {
            "country": "Private Network",
            "region": None,
            "city": "Local Traffic",
            "latitude": None,
            "longitude": None,
        }
    else:
        location = {
            "country": "Unknown",
            "region": None,
            "city": "Unknown",
            "latitude": None,
            "longitude": None,
        }
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                response = await client.get(f"https://ipapi.co/{client_ip}/json/")
                response.raise_for_status()
                data = response.json()
                location = {
                    "country": data.get("country_name") or data.get("country") or "Unknown",
                    "region": data.get("region") or data.get("region_code"),
                    "city": data.get("city") or "Unknown",
                    "latitude": data.get("latitude"),
                    "longitude": data.get("longitude"),
                }
        except Exception:
            pass

    if cached is None:
        cached = VisitorLocationCache(ip_hash=ip_hash)
        db.add(cached)

    cached.country = location["country"]
    cached.region = location["region"]
    cached.city = location["city"]
    cached.latitude = location["latitude"]
    cached.longitude = location["longitude"]
    cached.resolved_at = now
    db.commit()

    return location


@router.post("/page-view")
@limiter.limit("240/minute")
async def track_page_view(request: Request, body: PageViewRequest, db: Session = Depends(get_db)):
    location = await _resolve_location(_get_client_ip(request), db)

    event = TrafficEvent(
        page=body.page.strip()[:80] or "unknown",
        path=body.path.strip()[:200] or "/",
        source=_normalize_source(body.referrer),
        country=location["country"],
        region=location["region"],
        city=location["city"],
        latitude=location["latitude"],
        longitude=location["longitude"],
    )
    db.add(event)
    db.commit()
    invalidate_summary_cache()

    return {"status": "ok"}