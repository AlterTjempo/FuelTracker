"""Tests for the trend model: it must find real signal and must not invent one."""

import random
from datetime import date, timedelta

from services.forecast_model import build_trend_forecast, features_at

START = date(2026, 1, 1)
DAYS = 260


def _random_walk(seed, step_cents=1.2):
    rng = random.Random(seed)
    price, p = {}, 2.00
    for i in range(DAYS):
        p += rng.gauss(0, step_cents) / 100
        price[START + timedelta(days=i)] = p
    return price


def _oil_led(seed):
    """Pump price follows Brent changes with a ~2 day lag plus small noise."""
    rng = random.Random(seed)
    oil, price = {}, {}
    o, p = 0.55, 2.00
    oil_changes = []
    for i in range(DAYS):
        step = rng.gauss(0, 0.012)  # +-1.2% per day
        o *= 1 + step
        oil_changes.append(step)
        lagged = oil_changes[i - 2] if i >= 2 else 0.0
        p += lagged * 2.0 + rng.gauss(0, 0.002)  # 1% oil -> 2 cents
        d = START + timedelta(days=i)
        oil[d], price[d] = o, p
    return price, oil


def test_random_walk_gets_baseline_not_a_fake_model():
    price = _random_walk(seed=1)
    today = max(price) + timedelta(days=1)
    result = build_trend_forecast(price, {}, {}, today)
    assert not result["insufficient_data"]
    for h in result["horizons"]:
        if h["beats_baseline"]:
            # a model may only be shown if it generalised out-of-sample
            assert h["skill_vs_persistence"] > 0
        else:
            assert h["expected_change_cents"] == 0.0 and h["direction"] == "flat"
    # with pure noise, most horizons must fall back to the baseline
    assert sum(not h["beats_baseline"] for h in result["horizons"]) >= 3


def test_oil_led_series_is_detected():
    price, oil = _oil_led(seed=7)
    today = max(price) + timedelta(days=1)
    result = build_trend_forecast(price, oil, {}, today)
    h1 = result["horizons"][0]
    assert h1["beats_baseline"], h1
    assert h1["skill_vs_persistence"] > 0.1
    assert h1["model"].startswith("momentum_oil")
    assert any(d["feature"].startswith("Brent") for d in h1["drivers"])


def test_stale_data_is_refused():
    price = _random_walk(seed=3)
    today = max(price) + timedelta(days=10)
    result = build_trend_forecast(price, {}, {}, today)
    assert result["insufficient_data"] and "too old" in result["reason"]


def test_too_little_history_is_refused():
    price = {START + timedelta(days=i): 2.0 for i in range(10)}
    result = build_trend_forecast(price, {}, {}, START + timedelta(days=10))
    assert result["insufficient_data"]


def test_features_never_look_ahead():
    price = _random_walk(seed=5)
    t = START + timedelta(days=100)
    before = features_at(t, price, {}, {})
    future_changed = dict(price)
    for d in list(price):
        if d > t:
            future_changed[d] += 5.0  # wildly different future
    assert features_at(t, future_changed, {}, {}) == before
