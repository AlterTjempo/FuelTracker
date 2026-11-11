"""Does the hour-of-day price pattern differ between brands?

Pure functions. Input: {group: {date: {berlin_hour: avg_price}}}. For every
group the typical hour-of-day shape (deviation from the day's mean) is learned,
the noon-type price jump is located (hour and size) and the groups are compared.
If the groups differ by less than BRAND_MAX_JUMP_DIFF_CENTS in jump size and
BRAND_MAX_TIMING_DIFF_HOURS in timing, the single area-wide pattern is kept.
"""

from collections import defaultdict
from statistics import mean
from typing import Optional

import analytics_config as cfg
from services.go_now import typical_jump


def group_brands(station_brands: dict[str, Optional[str]]) -> dict[str, str]:
    """station_id -> group. Brands with fewer than BRAND_MIN_STATIONS stations become 'Other'."""
    norm = {sid: (b or "").strip() or "Other" for sid, b in station_brands.items()}
    counts: dict[str, int] = defaultdict(int)
    for b in norm.values():
        counts[b] += 1
    return {
        sid: (b if counts[b] >= cfg.BRAND_MIN_STATIONS else "Other")
        for sid, b in norm.items()
    }


def _shape(days: dict) -> tuple[dict[int, float], int]:
    samples: dict[int, list[float]] = defaultdict(list)
    n = 0
    for hrs in days.values():
        if len(hrs) >= cfg.HOURLY_MIN_HOURS:
            n += 1
            m = mean(hrs.values())
            for h, v in hrs.items():
                samples[h].append(v - m)
    return {h: mean(v) for h, v in samples.items()}, n


def _circular_diff(a: int, b: int) -> int:
    d = abs(a - b) % 24
    return min(d, 24 - d)


def analyse(groups: dict[str, dict]) -> dict:
    out = []
    for name, days in sorted(groups.items()):
        shape, n_days = _shape(days)
        if n_days < cfg.BRAND_MIN_DAYS or len(shape) < 20:
            continue
        jump = typical_jump(shape)
        out.append(
            {
                "group": name,
                "days": n_days,
                "cheapest_hour": min(shape, key=shape.get),
                "priciest_hour": max(shape, key=shape.get),
                "jump_hour": jump[0] if jump else None,
                "jump_cents": round(jump[1] * 100, 2) if jump else None,
                "spread_cents": round(
                    (max(shape.values()) - min(shape.values())) * 100, 2
                ),
            }
        )
    jumps = [g for g in out if g["jump_hour"] is not None]
    size_diff = (
        max(g["jump_cents"] for g in jumps) - min(g["jump_cents"] for g in jumps)
        if len(jumps) > 1
        else 0.0
    )
    timing_diff = (
        max(
            _circular_diff(a["jump_hour"], b["jump_hour"]) for a in jumps for b in jumps
        )
        if len(jumps) > 1
        else 0
    )
    differs = (
        size_diff >= cfg.BRAND_MAX_JUMP_DIFF_CENTS
        or timing_diff >= cfg.BRAND_MAX_TIMING_DIFF_HOURS
    )
    return {
        "groups": out,
        "max_jump_size_diff_cents": round(size_diff, 2),
        "max_jump_timing_diff_hours": timing_diff,
        "brands_differ": bool(differs),
        "decision": "per-brand patterns" if differs else "single area-wide pattern",
    }
