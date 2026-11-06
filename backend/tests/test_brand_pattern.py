import random
from datetime import date, timedelta

import analytics_config as cfg
from services import brand_pattern as bp

START = date(2026, 3, 1)


def make_group(jump_cents, jump_hour=12, days=30, seed=1, noise=0.002):
    rng = random.Random(seed)
    out = {}
    for i in range(days):
        out[START + timedelta(days=i)] = {
            h: 2.0 + (jump_cents / 100 if h >= jump_hour else 0.0) + rng.gauss(0, noise)
            for h in range(24)
        }
    return out


def test_small_brands_are_grouped_as_other():
    brands = {f"s{i}": "ARAL" for i in range(cfg.BRAND_MIN_STATIONS)}
    brands.update({"x": "TinyBrand", "y": "TinyBrand", "z": None, "w": "  "})
    groups = bp.group_brands(brands)
    assert groups["s0"] == "ARAL"
    assert groups["x"] == groups["y"] == groups["z"] == groups["w"] == "Other"


def test_identical_patterns_keep_the_single_area_wide_pattern():
    res = bp.analyse(
        {
            "A": make_group(14.0, seed=1),
            "B": make_group(14.3, seed=2),
            "C": make_group(14.5, seed=3),
        }
    )
    assert res["decision"] == "single area-wide pattern" and not res["brands_differ"]
    assert res["max_jump_timing_diff_hours"] == 0


def test_different_jump_size_is_detected():
    res = bp.analyse({"A": make_group(16.0, seed=1), "B": make_group(9.0, seed=2)})
    assert (
        res["brands_differ"]
        and res["max_jump_size_diff_cents"] >= cfg.BRAND_MAX_JUMP_DIFF_CENTS
    )


def test_different_jump_timing_is_detected():
    res = bp.analyse(
        {
            "A": make_group(14.0, jump_hour=12),
            "B": make_group(14.0, jump_hour=14, seed=5),
        }
    )
    assert res["brands_differ"] and res["max_jump_timing_diff_hours"] == 2


def test_groups_with_too_few_days_are_not_analysed():
    res = bp.analyse({"A": make_group(14.0, days=cfg.BRAND_MIN_DAYS - 1)})
    assert res["groups"] == []
