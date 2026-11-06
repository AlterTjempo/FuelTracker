"""Go Now logic: no look-ahead, gap handling, jump-awareness."""

import random
from datetime import datetime, timedelta, timezone

import analytics_config as cfg
from services import go_now as gn
from services.go_now_backtest import Series, build_records

UTC = timezone.utc
START = datetime(2026, 3, 1, 0, 0, tzinfo=UTC)


def _shape_eur(berlin_hour):
    """Fall through the morning, +12 cents jump at 12:00 Berlin (like the real data)."""
    if berlin_hour < 12:
        return -0.04 + 0.002 * berlin_hour
    return 0.08 - 0.004 * (berlin_hour - 12)


def synthetic_lows(days=20, seed=1, noise=0.003):
    rng = random.Random(seed)
    lows = {}
    for h in range(days * 24):
        ts = START + timedelta(hours=h)
        lows[ts] = 2.0 + _shape_eur(ts.astimezone(gn.BERLIN).hour) + rng.gauss(0, noise)
    return lows


def test_typical_jump_is_learned_from_data_not_hard_coded():
    lows = synthetic_lows()
    shape = gn.hour_shape(lows, START + timedelta(days=19))
    assert gn.typical_jump(shape)[0] == 12
    # shift the jump to 14:00 and the learned hour follows
    shifted = {
        k: v
        + (0.12 if k.astimezone(gn.BERLIN).hour >= 14 else 0)
        - (0.08 if k.astimezone(gn.BERLIN).hour >= 12 else 0)
        for k, v in lows.items()
    }
    assert gn.typical_jump(gn.hour_shape(shifted, START + timedelta(days=19)))[0] == 14


def test_no_shape_without_enough_days():
    assert gn.hour_shape(synthetic_lows(days=3), START + timedelta(days=3)) == {}


def test_decision_ignores_future_data():
    lows = synthetic_lows()
    now = START + timedelta(days=15, hours=9)
    price = 1.97
    before = gn.decide(lows, now, price)
    poisoned = dict(lows)
    for k in list(poisoned):
        if k > now:
            poisoned[k] += 5.0  # wildly different future
    after = gn.decide(poisoned, now, price)
    assert before is not None
    assert (before.percentile, before.slope_c_per_h, before.recommendation) == (
        after.percentile,
        after.slope_c_per_h,
        after.recommendation,
    )


def test_insufficient_data_returns_none():
    assert gn.decide({START: 2.0}, START + timedelta(hours=1), 2.0) is None


def test_pre_jump_falling_trend_cannot_cause_wait_or_excellent():
    on = gn.GoNowParams(25, 75, 0.2, "legacy", True)
    off = gn.GoNowParams(25, 75, 0.2, "legacy", False)
    assert gn.recommend(90, "falling", False, off) == "wait"
    assert (
        gn.recommend(90, "falling", True, on) == "neutral"
    )  # no waiting for a drop that is ending
    assert gn.recommend(10, "falling", False, off) == "excellent"
    assert gn.recommend(10, "falling", True, on) == "good"  # drop is about to reverse
    # without the pre-jump window nothing changes, and the flag off disables the rule
    assert gn.recommend(90, "falling", False, on) == "wait"
    assert gn.recommend(90, "falling", True, off) == "wait"


def test_hours_until_wraps_past_midnight():
    t = datetime(2026, 3, 10, 22, 30, tzinfo=gn.BERLIN)
    assert abs(gn.hours_until(12, t) - 13.5) < 1e-9
    t2 = datetime(2026, 3, 10, 10, 0, tzinfo=gn.BERLIN)
    assert gn.hours_until(12, t2) == 2.0


def test_robust_trend_ignores_one_outlier_hour():
    lows = synthetic_lows()
    now = START + timedelta(days=15, hours=9, minutes=30)
    shape = gn.hour_shape(lows, START + timedelta(days=15))
    lows[
        START + timedelta(days=15, hours=6)
    ] += 0.5  # a single bad hour inside the window
    robust = gn.trend_slope(lows, now, shape, "robust")
    legacy = gn.trend_slope(lows, now, shape, "legacy")
    assert abs(robust) < 1.0  # shape removed and outlier ignored
    assert legacy is None or isinstance(legacy, float)


def _rows(days, skip_days=(), step_min=15, stations=("a", "b")):
    rng = random.Random(7)
    t = START
    end = START + timedelta(days=days)
    while t < end:
        if (t - START).days not in skip_days:
            base = 2.0 + _shape_eur(t.astimezone(gn.BERLIN).hour)
            for i, s in enumerate(stations):
                yield (t, s, base + 0.01 * i + rng.gauss(0, 0.002))
        t += timedelta(minutes=step_min)


def test_backtest_skips_decisions_without_future_coverage_instead_of_imputing():
    series = Series(list(_rows(14, skip_days=(10, 11))))
    records = build_records(series)
    assert records
    gap_start = START + timedelta(days=10)
    # a decision just before the gap has no 6 h future -> must not exist
    for r in records:
        assert not (
            gap_start - timedelta(hours=5) < r["ts"] < gap_start + timedelta(days=2)
        )
    # outcomes only use real cycles
    for r in records:
        assert r["saving_a"] == r["saving_a"]  # not NaN


def test_stale_station_does_not_count_as_current_price():
    rows = [
        (START, "a", 1.90),
        (START + timedelta(minutes=15), "b", 2.10),
        (START + timedelta(minutes=60), "b", 2.10),
    ]
    series = Series(rows)
    # at +60 min station a's 1.90 is 60 min old (> 30 min freshness) and must be ignored
    assert series.best[-1] == 2.10


def test_adopted_parameters_come_from_one_config_module():
    p = gn.GoNowParams()
    assert (
        p.cheap_pct == cfg.GO_NOW_CHEAP_PCT
        and p.expensive_pct == cfg.GO_NOW_EXPENSIVE_PCT
    )
