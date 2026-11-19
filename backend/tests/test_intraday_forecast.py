"""Next-12-hours forecast: learns the daily rhythm, no look-ahead, honest band."""

import random
from datetime import datetime, timedelta

import analytics_config as cfg
from services import intraday_forecast as ifc

START = datetime(2026, 6, 1, 0, 0)  # local naive hours, like the router passes in
H = timedelta(hours=1)


def _rhythm(hour):
    """Fall through the morning, +12 cents jump at 12:00, easing in the evening."""
    if hour < 12:
        return -0.04 + 0.002 * (11 - hour)
    return 0.08 - 0.004 * (hour - 12)


def synthetic_hours(days=100, seed=3, noise=0.003):
    rng = random.Random(seed)
    level = 1.90
    hours = {}
    for d in range(days):
        level += rng.gauss(0, 0.01)  # the daily level drifts
        for h in range(24):
            t = START + timedelta(days=d, hours=h)
            hours[t] = level + _rhythm(h) + rng.gauss(0, noise)
    return hours


def test_learns_the_noon_jump_and_beats_both_baselines():
    hours = synthetic_hours()
    latest = max(hours)
    # Cut the series at 08:00 so the next 12 hours include the noon jump.
    cut = latest.replace(hour=8) - timedelta(days=1)
    data = {t: p for t, p in hours.items() if t <= cut}

    out = ifc.build_intraday_forecast(data, now=cut + timedelta(minutes=20))

    assert out["insufficient_data"] is False
    acc = out["accuracy"]
    assert acc["beats_baselines"] is True
    assert acc["mae_cents"] < min(acc["baselines"].values())
    assert {r["method"] for r in acc["mae_by_hour_ahead"]} <= set(ifc.METHODS)
    assert len(out["forecast"]) == cfg.INTRADAY_HORIZON_HOURS
    rise = out["summary"]["biggest_rise"]
    assert rise is not None and rise["t"].hour == 12 and rise["cents"] > 8


def test_falls_back_when_yesterday_is_missing_and_says_so():
    hours = synthetic_hours()
    latest = max(hours)
    gap = {latest - k * H for k in range(12, 36)}  # yesterday's hours for the next 12 h
    data = {t: p for t, p in hours.items() if t not in gap}
    out = ifc.build_intraday_forecast(data, now=latest)
    assert out["insufficient_data"] is False
    assert {r["method"] for r in out["forecast"]} <= {"shape", "persistence"}
    assert "yesterday" not in out["method_name"]


def test_band_is_calibrated_on_unseen_hours():
    out = ifc.build_intraday_forecast(
        synthetic_hours(), now=START + timedelta(days=100)
    )
    coverage = out["accuracy"]["band_coverage"]
    assert 0.7 <= coverage <= 0.9  # target 80 %
    for row in out["forecast"]:
        assert row["low"] <= row["price"] <= row["high"]


def test_no_look_ahead():
    hours = synthetic_hours()
    origin = START + timedelta(days=80, hours=9)
    shapes = ifc._Shapes(ifc._complete_days(hours))
    before = ifc._predict_all(hours, origin, shapes)

    future_changed = {t: (p + 0.5 if t > origin else p) for t, p in hours.items()}
    shapes2 = ifc._Shapes(ifc._complete_days(future_changed))
    after = ifc._predict_all(future_changed, origin, shapes2)
    assert before == after


def test_no_rhythm_means_no_invented_jump():
    """A random walk without a daily pattern must not produce a fake noon jump."""
    rng = random.Random(7)
    price, hours = 1.9, {}
    for i in range(100 * 24):
        price += rng.gauss(0, 0.002)
        hours[START + i * H] = price
    out = ifc.build_intraday_forecast(hours, now=max(hours))
    assert out["insufficient_data"] is False
    assert out["accuracy"]["mae_by_hour_ahead"][0]["method"] in (
        "persistence",
        "anchored_yesterday",
    )
    rise = out["summary"]["biggest_rise"]
    assert rise is None or rise["cents"] < 1.5


def test_stale_data_gives_no_forecast_but_keeps_the_backtest():
    hours = synthetic_hours()
    out = ifc.build_intraday_forecast(hours, now=max(hours) + timedelta(hours=10))
    assert out["insufficient_data"] is True
    assert "old" in out["reason"]
    assert out["accuracy"]["test_hours"] > 0


def test_too_little_history_says_so():
    hours = synthetic_hours(days=5)
    out = ifc.build_intraday_forecast(hours, now=max(hours))
    assert out["insufficient_data"] is True
    assert "accuracy" not in out


def test_gaps_are_not_filled():
    hours = synthetic_hours()
    latest = max(hours)
    gap = {
        latest - k * H for k in range(1, 40)
    }  # remove the day before the latest hour
    data = {t: p for t, p in hours.items() if t not in gap}
    out = ifc.build_intraday_forecast(data, now=latest)
    # The history shown is only real observations.
    assert all(
        datetime.fromisoformat(str(r["t"])) not in gap for r in out.get("history", [])
    )
