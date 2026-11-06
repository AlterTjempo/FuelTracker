"""Small pure helpers for the admin overview (no database or settings imports)."""

from datetime import datetime, timezone
from typing import Optional


def mask_email(email: str) -> str:
    """j***@example.com : enough to recognise an account, not to harvest addresses."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    return f"{local[:1]}***@{domain}"


def age_seconds(
    ts: Optional[datetime], now: Optional[datetime] = None
) -> Optional[float]:
    if ts is None:
        return None
    now = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (now - ts).total_seconds())


def freshness_status(age: Optional[float], ok_within: float, warn_within: float) -> str:
    """'ok' if recent enough, 'warn' if getting stale, 'error' if stale or never seen."""
    if age is None:
        return "error"
    if age <= ok_within:
        return "ok"
    if age <= warn_within:
        return "warn"
    return "error"


def coverage_ratio(cycles: int, expected: int) -> float:
    """Share (0..1) of expected collection cycles that actually ran."""
    if expected <= 0:
        return 0.0
    return max(0.0, min(1.0, cycles / expected))
