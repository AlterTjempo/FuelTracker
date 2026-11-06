"""Go Now decision logic as pure functions.

The live endpoint (routers/prices.py) and the backtest (go_now_backtest.py)
both call :func:`decide`, so what is validated is exactly what runs.

Input data is `lows`: {UTC hour start -> lowest price across the stations
considered in that hour}. Nothing is imputed: a missing hour is simply absent.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean, median
from typing import Optional
from zoneinfo import ZoneInfo

import analytics_config as cfg
from services.stats_utils import least_squares_slope, theil_sen

BERLIN = ZoneInfo("Europe/Berlin")


@dataclass(frozen=True)
class GoNowParams:
    cheap_pct: float = cfg.GO_NOW_CHEAP_PCT
    expensive_pct: float = cfg.GO_NOW_EXPENSIVE_PCT
    trend_threshold: float = cfg.GO_NOW_TREND_THRESHOLD_C_PER_H
    trend_method: str = cfg.GO_NOW_TREND_METHOD  # "legacy" | "robust"
    jump_aware: bool = cfg.GO_NOW_JUMP_AWARE


def floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def berlin_hour(dt: datetime) -> int:
    return dt.astimezone(BERLIN).hour


def hour_shape(lows: dict, before: datetime) -> dict[int, float]:
    """Typical Berlin-hour deviation from the day's mean, from days before `before`."""
    start = before - timedelta(days=cfg.GO_NOW_SHAPE_DAYS)
    by_day: dict = defaultdict(dict)
    for key, value in lows.items():
        if start <= key < before:
            b = key.astimezone(BERLIN)
            by_day[b.date()][b.hour] = value
    samples: dict[int, list[float]] = defaultdict(list)
    usable_days = 0
    for hours in by_day.values():
        if len(hours) >= cfg.GO_NOW_SHAPE_MIN_HOURS:
            usable_days += 1
            m = mean(hours.values())
            for h, v in hours.items():
                samples[h].append(v - m)
    if usable_days < cfg.GO_NOW_SHAPE_MIN_DAYS:
        return {}
    return {h: mean(v) for h, v in samples.items()}


def typical_jump(shape: dict[int, float]) -> Optional[tuple[int, float]]:
    """(Berlin hour at which the price typically jumps, size in EUR), learned from data."""
    if len(shape) < 20:
        return None
    best = None
    for h in range(24):
        prev = (h - 1) % 24
        if h in shape and prev in shape:
            step = shape[h] - shape[prev]
            if best is None or step > best[1]:
                best = (h, step)
    if best is None or best[1] * 100 < cfg.GO_NOW_MIN_JUMP_CENTS:
        return None
    return best


def hours_until(jump_hour: int, now: datetime) -> float:
    b = now.astimezone(BERLIN)
    return (jump_hour - (b.hour + b.minute / 60)) % 24


def percentile_stats(lows: dict, now: datetime, current_price: float) -> Optional[dict]:
    """Rank the current price against the same time of day (+-1 h) over the last 7 days."""
    since = now - timedelta(days=cfg.GO_NOW_HISTORY_DAYS)
    hour = berlin_hour(now)
    window = {(hour - 1) % 24, hour, (hour + 1) % 24}
    in_range = [(k, v) for k, v in lows.items() if since <= k <= now]
    rows = [v for k, v in in_range if berlin_hour(k) in window]
    if len(rows) < cfg.GO_NOW_MIN_SAME_HOUR_POINTS:
        rows = [v for _, v in in_range]
        if len(rows) < cfg.GO_NOW_MIN_ALL_HOUR_POINTS:
            return None
    rows.sort()
    return {
        "percentile": round(
            sum(1 for p in rows if p <= current_price) / len(rows) * 100, 1
        ),
        "week_low": min(rows),
        "week_high": max(rows),
        "week_median": median(rows),
        "n": len(rows),
    }


def trend_slope(
    lows: dict, now: datetime, shape: dict[int, float], method: str
) -> Optional[float]:
    """Price trend in cents per hour, or None if there is not enough data."""
    cur = floor_hour(now)
    if method == "robust":
        start = cur - timedelta(hours=cfg.GO_NOW_ROBUST_TREND_HOURS)
        pts = sorted((k, v) for k, v in lows.items() if start <= k <= cur)
        if len(pts) < cfg.GO_NOW_ROBUST_MIN_POINTS:
            return None
        xs = [(k - pts[0][0]).total_seconds() / 3600 for k, _ in pts]
        ys = [
            v - shape.get(berlin_hour(k), 0.0) for k, v in pts
        ]  # remove the hour-of-day shape
        slope = theil_sen(xs, ys)
    else:
        start = cur - timedelta(hours=cfg.GO_NOW_LEGACY_TREND_HOURS)
        ys = [v for k, v in sorted(lows.items()) if start <= k <= cur]
        slope = least_squares_slope(ys)
    return None if slope is None else slope * 100


def direction(slope_c_per_h: Optional[float], threshold: float) -> str:
    if slope_c_per_h is None:
        return "stable"
    if slope_c_per_h < -threshold:
        return "falling"
    if slope_c_per_h > threshold:
        return "rising"
    return "stable"


def recommend(pct: float, trend_dir: str, pre_jump: bool, params: GoNowParams) -> str:
    """Percentile x trend matrix.

    Pre-jump rule: shortly before the typical price jump a FALLING trend is
    neutralised, because the drop is about to reverse. It can then neither
    make us wait for a further drop nor upgrade a cheap price to "excellent".
    """
    if params.jump_aware and pre_jump and trend_dir == "falling":
        trend_dir = "stable"
        if pct > params.cheap_pct:  # no "wait" because of a drop that is about to end
            return "neutral"
    if pct <= params.cheap_pct:
        return "excellent" if trend_dir == "falling" else "good"
    if pct <= params.expensive_pct:
        return "wait" if trend_dir == "rising" else "neutral"
    return "avoid" if trend_dir == "rising" else "wait"


@dataclass
class Decision:
    recommendation: str
    percentile: float
    slope_c_per_h: Optional[float]
    trend_direction: str
    week_low: float
    week_high: float
    week_median: float
    hours_to_jump: Optional[float] = None
    jump_hour: Optional[int] = None
    pre_jump: bool = False
    extra: dict = field(default_factory=dict)


def decide(
    lows: dict,
    now: datetime,
    current_price: float,
    shape: Optional[dict] = None,
    params: Optional[GoNowParams] = None,
) -> Optional[Decision]:
    """Full Go Now decision at time `now`, or None if there is not enough data."""
    params = params or GoNowParams()
    stats = percentile_stats(lows, now, current_price)
    if stats is None:
        return None
    if shape is None:
        # shape from days before today (Berlin), so it never includes the current day
        day_start = now.astimezone(BERLIN).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        shape = hour_shape(lows, day_start)
    slope = trend_slope(lows, now, shape, params.trend_method)
    trend_dir = direction(slope, params.trend_threshold)

    jump = typical_jump(shape)
    htj = hours_until(jump[0], now) if jump else None
    pre = (
        htj is not None
        and cfg.GO_NOW_PRE_JUMP_MIN_H <= htj <= cfg.GO_NOW_PRE_JUMP_MAX_H
    )
    return Decision(
        recommendation=recommend(stats["percentile"], trend_dir, pre, params),
        percentile=stats["percentile"],
        slope_c_per_h=slope,
        trend_direction=trend_dir,
        week_low=stats["week_low"],
        week_high=stats["week_high"],
        week_median=stats["week_median"],
        hours_to_jump=htj,
        jump_hour=jump[0] if jump else None,
        pre_jump=pre,
    )
