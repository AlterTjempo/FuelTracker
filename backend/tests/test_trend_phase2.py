"""Phase 2: probability model, hourly forecast, market features, quantile regression, metrics."""

import random
from datetime import date, timedelta

import analytics_config as cfg
from services import forecast_model as fm

START = date(2026, 1, 1)


def ar_series(days=360, phi=0.85, noise=1.0, seed=3):
    """Daily price whose CHANGES are autocorrelated (momentum): a known, learnable signal."""
    rng = random.Random(seed)
    price, p, ch = {}, 2.0, 0.0
    for i in range(days):
        ch = phi * ch + rng.gauss(0, noise)
        p += ch / 100
        price[START + timedelta(days=i)] = p
    return price


def random_walk(days=320, seed=11, step=1.2):
    rng = random.Random(seed)
    price, p = {}, 2.0
    for i in range(days):
        p += rng.gauss(0, step) / 100
        price[START + timedelta(days=i)] = p
    return price


def noise_market(days, seed):
    rng = random.Random(seed)
    out = {}
    for name in cfg.MARKET_SERIES:
        v, series = 100.0, {}
        for i in range(-20, days):
            v *= 1 + rng.gauss(0, 0.01)
            series[START + timedelta(days=i)] = v
        out[name] = series
    return out


# ----------------------------------------------------------- probability ----


def test_probability_model_is_validated_and_calibrated_on_a_known_signal():
    price = ar_series()
    today = max(price) + timedelta(days=1)
    res = fm.build_trend_forecast(price, {}, {}, today)
    p24 = res["probability"]["horizons"][0]
    assert p24["validated"], p24
    assert p24["brier_skill"] > 0.03
    assert p24["ece"] <= cfg.PROB_MAX_ECE
    assert 0.0 < p24["probability"] < 1.0
    # reliability table: observed frequency rises with the predicted probability
    rows = p24["reliability_table"]
    assert rows[-1]["observed"] > rows[0]["observed"]


def test_random_walk_gives_no_fake_models_and_no_validated_probability():
    price = random_walk()
    today = max(price) + timedelta(days=1)
    res = fm.build_trend_forecast(price, {}, {}, today, market=noise_market(320, 5))
    assert not res["probability"]["any_validated"]
    assert (
        sum(not h["beats_baseline"] for h in res["horizons"]) >= 4
    )  # at most one lucky horizon
    for h in res["horizons"]:
        if not h["beats_baseline"]:
            assert (
                h["expected_change_cents"] == 0.0 and h["reliability"]["level"] == "Low"
            )


def test_market_features_never_look_ahead():
    price = random_walk(days=120)
    market = noise_market(120, 2)
    t = START + timedelta(days=60)
    before = fm.features_at(t, price, {}, {}, market)
    poisoned = {
        s: {d: (v * 5 if d > t else v) for d, v in series.items()}
        for s, series in market.items()
    }
    assert fm.features_at(t, price, {}, {}, poisoned) == before
    assert any(
        v is not None
        for k, v in before.items()
        if k.endswith(tuple(f"_L{lag}" for lag in cfg.MARKET_LAGS))
    )


def test_market_features_are_changes_not_levels_and_not_imputed():
    price = random_walk(days=60)
    flat = {"gasoil_proxy": {START + timedelta(days=i): 100.0 for i in range(-20, 60)}}
    t = START + timedelta(days=40)
    f = fm.features_at(t, price, {}, {}, flat)
    assert f["gasoil_proxy_L1"] == 0.0  # a constant level has zero change
    sparse = {"gasoil_proxy": {START + timedelta(days=1): 100.0}}
    assert (
        fm.features_at(t, price, {}, {}, sparse)["gasoil_proxy_L1"] is None
    )  # missing stays missing


# ---------------------------------------------------------------- learners ----


def test_logistic_regression_learns_a_separable_signal():
    rng = random.Random(1)
    X = [[rng.gauss(0, 1)] for _ in range(300)]
    y = [1.0 if x[0] + rng.gauss(0, 0.3) > 0 else 0.0 for x in X]
    m = fm.Logistic().fit(X, y)
    assert m.predict([2.0]) > 0.9 and m.predict([-2.0]) < 0.1


def test_median_quantile_regression_resists_outliers_better_than_ridge():
    rng = random.Random(2)
    X = [[rng.gauss(0, 1)] for _ in range(200)]
    y = [3 * x[0] + rng.gauss(0, 0.2) for x in X]
    for i in range(0, 200, 20):
        y[i] += 80  # 10 wild outliers
    ridge = fm.Ridge(lam=0.1).fit(X, y)
    qr = fm.QuantileLinear(0.5, lam=0.1).fit(X, y)
    err = lambda m: abs(m.predict([1.0]) - m.predict([0.0]) - 3.0)  # noqa: E731
    assert err(qr) < 0.5 and err(qr) < err(ridge)


# ----------------------------------------------------------------- metrics ----


def test_band_calibration_hits_the_target_coverage_out_of_sample():
    rng = random.Random(9)
    folds = [
        (START + timedelta(days=i), y, 0.0)
        for i, y in enumerate(rng.gauss(0, 2) for _ in range(400))
    ]
    ev = fm.evaluate_folds(folds, h=1)
    assert 0.72 <= ev["coverage80"] <= 0.88
    assert ev["calibrated"]
    assert ev["band_low"] < 0 < ev["band_high"]


def test_reliability_level_uses_out_of_sample_metrics():
    base = {"skill_eval": 0.2, "dm_p_eval": 0.01, "calibrated": True}
    assert fm.reliability_level(base, True)["level"] == "High"
    assert (
        fm.reliability_level({**base, "calibrated": False}, True)["level"] == "Medium"
    )
    assert fm.reliability_level({**base, "skill_eval": 0.02}, True)["level"] == "Low"
    assert fm.reliability_level(base, False)["level"] == "Low"


# ----------------------------------------------------------------- hourly ----


def make_days(n=90, noise=0.012, seed=4, shape=True):
    rng = random.Random(seed)
    days, level = {}, 2.0
    for i in range(n):
        level += rng.gauss(0, 0.01)
        d = START + timedelta(days=i)
        days[d] = {
            h: level
            + (
                (-0.05 + 0.004 * h if h < 12 else 0.08 - 0.003 * (h - 12))
                if shape
                else 0
            )
            + rng.gauss(0, noise)
            for h in range(24)
        }
    return days


def test_hourly_forecast_beats_naive_baselines_when_a_shape_exists():
    days = make_days()
    out = fm.hourly_forecast(days, max(days) + timedelta(days=1))
    assert out["validated"], out
    assert out["mae_cents"] < min(
        out["baseline_same_hour_yesterday_mae"], out["baseline_same_hour_last_week_mae"]
    )
    assert len(out["forecast"]) == 24


def test_hourly_forecast_skips_days_with_missing_hours_instead_of_filling():
    days = make_days(n=60)
    for d in list(days)[10:30]:
        days[d] = {
            h: v for h, v in days[d].items() if h < 10
        }  # too few hours -> unusable
    out = fm.hourly_forecast(days, max(days) + timedelta(days=1))
    assert "reason" in out or out.get("n_test_days", 0) < 40
