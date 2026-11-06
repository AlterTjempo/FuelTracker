"""Trend models for the area-average pump price (pure Python, no ML dependencies).

Pure functions only (no database access) so everything can be unit-tested and
backtested on any data. The router in ``routers/insights.py`` assembles the
daily series and calls :func:`build_trend_forecast`; the CLI in
``trend_backtest.py`` prints the full evaluation.

Three things are predicted
--------------------------
1. **Daily level change** (baseline target): ``y = price[t+h] - price[t]`` in
   cents, h = 1, 2, 3, 5, 7 days, with ridge or quantile regression.
2. **Probability of a rise** larger than X cents within 24 h / 48 h
   (regularised logistic regression, calibration checked).
3. **Hourly shape of the next day**: daily level + learned hour-of-day shape.

Inputs (all known at the end of day t, no look-ahead)
-----------------------------------------------------
weekday of the target, price momentum / weekly drift / mean reversion, Brent
(EUR/L), keyword news pressure and lagged changes of gasoil (HO), RBOB, EUR/USD
and Brent in USD. Variants that need an input only run where the data exists.

Honesty rules
-------------
* Expanding-window walk-forward backtest; a training sample is only used once
  its target has happened.
* Every candidate is compared to the naive baseline ("stays the same" / base
  rate / same hour yesterday or last week). A variant is SELECTED on the first
  half of the backtest (needs >= 3% better MAE and a Diebold-Mariano p < 0.1)
  and REPORTED on the second half.
* The 80% band comes from empirical error quantiles of the selection half, its
  coverage is then measured on the second half.
* If nothing beats the baseline, the baseline is returned and says so.
  Missing days are never filled.
"""

import math
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, pstdev
from typing import Optional

import analytics_config as cfg
from services.stats_utils import (
    brier_score,
    diebold_mariano,
    pinball_loss,
    reliability_table,
)

HORIZONS = cfg.TREND_HORIZONS
MIN_TRAIN = cfg.TREND_MIN_TRAIN
MIN_TEST_FOLDS = cfg.TREND_MIN_TEST_FOLDS
MIN_SKILL_TO_SELECT = cfg.TREND_MIN_SKILL
MAX_ORIGIN_AGE_DAYS = cfg.TREND_MAX_ORIGIN_AGE_DAYS
MAX_TRAIN = cfg.TREND_MAX_TRAIN

PRICE_FEATURES = ["mom_short", "mom_week", "reversion"]
OIL_FEATURES = ["oil_mom", "oil_rel"]
MARKET_SERIES = tuple(cfg.MARKET_SERIES)
MARKET_FEATURES = [f"{s}_L{lag}" for s in MARKET_SERIES for lag in cfg.MARKET_LAGS]

BASE_LABELS = {
    "mom_short": "recent momentum",
    "mom_week": "weekly drift",
    "reversion": "distance from 28-day average",
    "oil_mom": "Brent trend",
    "oil_rel": "Brent vs. its 28-day average",
    "news_3d": "supply-risk news",
}
SERIES_LABELS = {
    "gasoil_proxy": "gasoil",
    "rbob": "gasoline (RBOB)",
    "eurusd": "EUR/USD",
    "brent_usd": "Brent (USD)",
}


def feature_label(name: str) -> str:
    if name in BASE_LABELS:
        return BASE_LABELS[name]
    series, _, lag = name.rpartition("_L")
    return f"{SERIES_LABELS.get(series, series)} ({lag} d ago)"


FEATURE_LABELS = {n: feature_label(n) for n in BASE_LABELS} | {
    n: feature_label(n) for n in MARKET_FEATURES
}

# Candidate models. `weekday` adds six target-weekday dummies; with little data
# they can overfit, so lean variants without them are tried as well.
VARIANTS = {
    "weekday": {"features": [], "weekday": True, "kind": "ridge"},
    "momentum": {"features": PRICE_FEATURES, "weekday": False, "kind": "ridge"},
    "price": {"features": PRICE_FEATURES, "weekday": True, "kind": "ridge"},
    "momentum_oil": {
        "features": PRICE_FEATURES + OIL_FEATURES,
        "weekday": False,
        "kind": "ridge",
    },
    "momentum_oil_news": {
        "features": PRICE_FEATURES + OIL_FEATURES + ["news_3d"],
        "weekday": False,
        "kind": "ridge",
    },
    "momentum_market": {
        "features": PRICE_FEATURES + MARKET_FEATURES,
        "weekday": False,
        "kind": "ridge",
        "lam": cfg.TREND_RIDGE_LAMBDA_MARKET,
    },
    "qr_momentum": {"features": PRICE_FEATURES, "weekday": False, "kind": "quantile"},
    "qr_market": {
        "features": PRICE_FEATURES + MARKET_FEATURES,
        "weekday": False,
        "kind": "quantile",
        "lam": cfg.TREND_RIDGE_LAMBDA_MARKET,
    },
}
PROB_VARIANTS = {
    "momentum": VARIANTS["momentum"],
    "momentum_market": VARIANTS["momentum_market"],
}


# --- tiny linear algebra ----------------------------------------------------


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Solve a·x = b by Gaussian elimination with partial pivoting."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            continue
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(col + 1, n):
            f = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= f * m[col][c]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))
        x[i] = s / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0
    return x


class _Linear:
    """Linear model on standardised inputs: intercept + sum(coef * z)."""

    def __init__(self):
        self.means: list[float] = []
        self.stds: list[float] = []
        self.coef: list[float] = []
        self.intercept = 0.0

    def _standardise(self, X):
        k = len(X[0]) if X else 0
        self.means = [mean(col) for col in zip(*X)] if k else []
        self.stds = [(pstdev(col) or 1.0) for col in zip(*X)] if k else []
        return [
            [(row[j] - self.means[j]) / self.stds[j] for j in range(k)] for row in X
        ]

    def predict(self, x: list[float]) -> float:
        return self.intercept + sum(
            c * (v - m) / s for c, v, m, s in zip(self.coef, x, self.means, self.stds)
        )

    def contributions(self, x: list[float]) -> list[float]:
        return [
            c * (v - m) / s for c, v, m, s in zip(self.coef, x, self.means, self.stds)
        ]


def _weighted_normal_equations(Z, y, w, lam):
    """Solve for [intercept, coef] minimising sum w*(y-b0-Z.coef)^2 + lam*|coef|^2."""
    n, k = len(Z), len(Z[0]) if Z else 0
    a = [[0.0] * (k + 1) for _ in range(k + 1)]
    b = [0.0] * (k + 1)
    for i in range(n):
        wi, zi = w[i], [1.0] + Z[i]
        for p in range(k + 1):
            wp = wi * zi[p]
            b[p] += wp * y[i]
            for q in range(p, k + 1):
                a[p][q] += wp * zi[q]
    for p in range(k + 1):
        for q in range(p):
            a[p][q] = a[q][p]
    for p in range(1, k + 1):
        a[p][p] += lam
    sol = _solve(a, b)
    return sol[0], sol[1:]


class Ridge(_Linear):
    """Ridge regression (unpenalised intercept)."""

    def __init__(self, lam: float = cfg.TREND_RIDGE_LAMBDA):
        super().__init__()
        self.lam = lam

    def fit(self, X, y):
        Z = self._standardise(X)
        if not Z or not Z[0]:
            self.intercept = mean(y)
            self.coef = []
            return self
        self.intercept, self.coef = _weighted_normal_equations(
            Z, y, [1.0] * len(Z), self.lam
        )
        return self


class QuantileLinear(_Linear):
    """Linear quantile regression (default: median), smoothed IRLS with an L2 penalty."""

    def __init__(self, tau: float = 0.5, lam: float = cfg.TREND_RIDGE_LAMBDA):
        super().__init__()
        self.tau, self.lam = tau, lam

    def fit(self, X, y):
        Z = self._standardise(X)
        if not Z or not Z[0]:
            ys = sorted(y)
            self.intercept = ys[int(self.tau * (len(ys) - 1))]
            self.coef = []
            return self
        w = [1.0] * len(Z)
        b0, coef = 0.0, []
        for _ in range(cfg.QUANTILE_IRLS_ITERATIONS):
            b0, coef = _weighted_normal_equations(Z, y, w, self.lam)
            res = [
                yi - b0 - sum(c * z for c, z in zip(coef, zi)) for yi, zi in zip(y, Z)
            ]
            w = [
                (self.tau if r >= 0 else 1 - self.tau)
                / max(abs(r), cfg.QUANTILE_IRLS_DELTA)
                for r in res
            ]
        self.intercept, self.coef = b0, coef
        return self


class Logistic(_Linear):
    """L2-regularised logistic regression (Newton / IRLS) on standardised inputs."""

    def __init__(self, lam: float = cfg.PROB_LAMBDA):
        super().__init__()
        self.lam = lam

    @staticmethod
    def _sigmoid(z: float) -> float:
        return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))

    def fit(self, X, y):
        Z = self._standardise(X)
        n = len(Z)
        k = len(Z[0]) if Z else 0
        beta = [0.0] * (k + 1)  # [intercept, coef...]
        for _ in range(12):
            p = [
                self._sigmoid(beta[0] + sum(c * z for c, z in zip(beta[1:], zi)))
                for zi in Z
            ]
            w = [max(pi * (1 - pi), 1e-6) for pi in p]
            a = [[0.0] * (k + 1) for _ in range(k + 1)]
            g = [0.0] * (k + 1)
            for i in range(n):
                zi = [1.0] + Z[i]
                for pidx in range(k + 1):
                    g[pidx] += (y[i] - p[i]) * zi[pidx]
                    for q in range(pidx, k + 1):
                        a[pidx][q] += w[i] * zi[pidx] * zi[q]
            for pidx in range(k + 1):
                for q in range(pidx):
                    a[pidx][q] = a[q][pidx]
            for pidx in range(1, k + 1):
                a[pidx][pidx] += self.lam
                g[pidx] -= self.lam * beta[pidx]
            step = _solve(a, g)
            beta = [b + s for b, s in zip(beta, step)]
            if max(abs(s) for s in step) < 1e-6:
                break
        self.intercept, self.coef = beta[0], beta[1:]
        return self

    def predict(self, x: list[float]) -> float:  # probability
        return self._sigmoid(_Linear.predict(self, x))


def _make_model(spec: dict):
    lam = spec.get("lam", cfg.TREND_RIDGE_LAMBDA)
    return QuantileLinear(0.5, lam) if spec["kind"] == "quantile" else Ridge(lam)


# --- features ----------------------------------------------------------------


def _vals(series: dict, t: date, a: int, b: int) -> list[float]:
    """Values on days t-b .. t-a that exist (a <= b, a=0 is day t itself)."""
    return [
        series[d] for k in range(a, b + 1) if (d := t - timedelta(days=k)) in series
    ]


def _avg(series: dict, t: date, a: int, b: int, min_count: int = 1) -> Optional[float]:
    v = _vals(series, t, a, b)
    return mean(v) if len(v) >= min_count else None


def features_at(
    t: date, price: dict, oil: dict, news: dict, market: Optional[dict] = None
) -> dict[str, Optional[float]]:
    """Features known at the end of day t. Values are in cents / percent."""
    f: dict[str, Optional[float]] = {k: None for k in FEATURE_LABELS}
    p0 = price.get(t)
    if p0 is None:
        return f
    prev3 = _avg(price, t, 1, 3)
    recent3, older3 = _avg(price, t, 0, 2), _avg(price, t, 7, 9)
    base28 = _avg(price, t, 0, 27, min_count=10)
    if prev3 is not None:
        f["mom_short"] = (p0 - prev3) * 100
    if recent3 is not None and older3 is not None:
        f["mom_week"] = (recent3 - older3) * 100
    if base28 is not None:
        f["reversion"] = (p0 - base28) * 100

    o_recent, o_older = _avg(oil, t, 0, 2), _avg(oil, t, 7, 9)
    o_base = _avg(oil, t, 0, 27, min_count=10)
    if o_recent and o_older:
        f["oil_mom"] = (o_recent / o_older - 1) * 100
    if o_recent and o_base:
        f["oil_rel"] = (o_recent / o_base - 1) * 100

    n = _vals(news, t, 0, 2)
    if n:
        f["news_3d"] = math.log1p(mean(n))

    # Lagged CHANGES (not levels): 3-day mean ending `lag` days ago vs. the 3-day
    # mean before it. 3-day windows always contain a trading day (futures do not
    # trade at weekends), so weekends do not create false gaps. Nothing is imputed.
    for series_name, series in (market or {}).items():
        for lag in cfg.MARKET_LAGS:
            a = _avg(series, t, lag, lag + 2)
            b = _avg(series, t, lag + 3, lag + 5)
            if a is not None and b:
                f[f"{series_name}_L{lag}"] = (a / b - 1) * 100
    return f


def _row(feats: dict, spec: dict, target_weekday: int) -> Optional[list[float]]:
    xs = []
    for name in spec["features"]:
        if feats.get(name) is None:
            return None
        xs.append(feats[name])
    if spec["weekday"]:
        xs.extend(
            1.0 if target_weekday == wd else 0.0 for wd in range(1, 7)
        )  # Monday = baseline
    return xs


def _mae(errs) -> float:
    return sum(abs(e) for e in errs) / len(errs)


def _quantile(sorted_vals: list[float], q: float) -> float:
    pos = q * (len(sorted_vals) - 1)
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


# --- walk-forward backtest -----------------------------------------------------


def _samples(price, oil, news, market, h):
    out = []
    for t in sorted(price):
        target = t + timedelta(days=h)
        if target in price:
            out.append(
                (
                    t,
                    features_at(t, price, oil, news, market),
                    target.weekday(),
                    (price[target] - price[t]) * 100,
                )
            )
    return out


def _walk_forward(samples, spec: dict, h: int):
    """[(origin, y, prediction)] per usable fold; training only uses realised targets."""
    usable = [(t, _row(f, spec, wd), wd, y) for t, f, wd, y in samples]
    usable = [u for u in usable if u[1] is not None]
    stride = (
        cfg.TREND_REFIT_EVERY_QUANTILE
        if spec["kind"] == "quantile"
        else cfg.TREND_REFIT_EVERY
    )
    folds, model, since_fit = [], None, stride
    for t, x, _, y in usable:
        if since_fit >= stride or model is None:
            train = [
                (xx, yy) for tt, xx, _, yy in usable if tt + timedelta(days=h) <= t
            ][-MAX_TRAIN:]
            if len(train) < MIN_TRAIN:
                continue
            model = _make_model(spec).fit([a for a, _ in train], [b for _, b in train])
            since_fit = 0
        since_fit += 1
        folds.append((t, y, model.predict(x)))
    return folds


def evaluate_folds(folds, h: int) -> Optional[dict]:
    """Out-of-sample metrics for one variant and horizon (selection half / evaluation half)."""
    n = len(folds)
    if n < MIN_TEST_FOLDS:
        return None
    half = n // 2
    sel, ev = folds[:half], folds[half:]

    def err(fs):
        return [y - p for _, y, p in fs]

    def base(fs):
        return [y for _, y, _ in fs]

    def skill(fs):
        return 1 - _mae(err(fs)) / max(1e-9, _mae(base(fs)))

    def dm(fs):
        r = diebold_mariano([abs(e) for e in err(fs)], [abs(y) for y in base(fs)], h=h)
        return r[1] if r else None

    # 80% band from the SELECTION half's empirical error quantiles; its coverage
    # is then measured on the evaluation half (honest, not tuned on the same data).
    q_lo, q_hi = cfg.TREND_BAND
    es, bs = sorted(err(sel)), sorted(base(sel))
    lo_e, hi_e = _quantile(es, q_lo), _quantile(es, q_hi)
    blo, bhi = _quantile(bs, q_lo), _quantile(bs, q_hi)
    coverage = mean(1.0 if p + lo_e <= y <= p + hi_e else 0.0 for _, y, p in ev)
    sigma = pstdev(err(sel)) if len(sel) > 1 else None
    raw_coverage = (
        mean(1.0 if abs(y - p) <= 1.2816 * sigma else 0.0 for _, y, p in ev)
        if sigma
        else None
    )
    moves = [(y, p) for _, y, p in ev if abs(y) >= cfg.DIRECTION_MIN_MOVE_CENTS]
    up_share = mean(1.0 if y > 0 else 0.0 for y, _ in moves) if moves else None
    return {
        "n_folds": n,
        "skill_select": skill(sel),
        "skill_eval": skill(ev),
        "mae_eval": _mae(err(ev)),
        "mae_persistence_eval": _mae(base(ev)),
        "dm_p_select": dm(sel),
        "dm_p_eval": dm(ev),
        "band_low": lo_e,
        "band_high": hi_e,
        "base_band_low": blo,
        "base_band_high": bhi,
        "coverage80": coverage,
        "coverage80_raw_sigma": raw_coverage,
        "calibrated": abs(coverage - (q_hi - q_lo)) <= cfg.TREND_COVERAGE_TOLERANCE,
        "pinball10": mean(pinball_loss(y, p + lo_e, q_lo) for _, y, p in ev),
        "pinball90": mean(pinball_loss(y, p + hi_e, q_hi) for _, y, p in ev),
        "pinball10_base": mean(pinball_loss(y, blo, q_lo) for _, y, _ in ev),
        "pinball90_base": mean(pinball_loss(y, bhi, q_hi) for _, y, _ in ev),
        "directional_accuracy": (
            mean(1.0 if (p > 0) == (y > 0) else 0.0 for y, p in moves)
            if moves
            else None
        ),
        "directional_base": (
            max(up_share, 1 - up_share) if up_share is not None else None
        ),
        "sigma": sigma,
    }


def reliability_level(ev: dict, beats: bool) -> dict:
    """High / Medium / Low from the out-of-sample metrics."""
    if not beats:
        return {"level": "Low", "why": "no model beats the 'no change' baseline"}
    skill, p, cov_ok = ev["skill_eval"], ev["dm_p_eval"], ev["calibrated"]
    if (
        skill >= cfg.RELIABILITY_HIGH_SKILL
        and p is not None
        and p < cfg.RELIABILITY_HIGH_DM_P
        and cov_ok
    ):
        return {
            "level": "High",
            "why": "clearly better than baseline, significant, band well calibrated",
        }
    if (
        skill >= cfg.RELIABILITY_MEDIUM_SKILL
        and p is not None
        and p < cfg.RELIABILITY_MEDIUM_DM_P
    ):
        return {
            "level": "Medium",
            "why": "better than baseline, moderately significant",
        }
    return {"level": "Low", "why": "small or not significant improvement over baseline"}


# --- probability of a rise ----------------------------------------------------


def _prob_walk_forward(samples, spec, h, x_cents):
    usable = [
        (t, _row(f, spec, wd), wd, 1.0 if y > x_cents else 0.0)
        for t, f, wd, y in samples
    ]
    usable = [u for u in usable if u[1] is not None]
    folds, model, since_fit, base_rate = [], None, cfg.TREND_REFIT_EVERY, 0.0
    for t, x, _, label in usable:
        if since_fit >= cfg.TREND_REFIT_EVERY or model is None:
            train = [
                (xx, yy) for tt, xx, _, yy in usable if tt + timedelta(days=h) <= t
            ][-MAX_TRAIN:]
            if len(train) < MIN_TRAIN or len({yy for _, yy in train}) < 2:
                continue
            model = Logistic().fit([a for a, _ in train], [b for _, b in train])
            base_rate = mean(b for _, b in train)
            since_fit = 0
        since_fit += 1
        folds.append((t, label, model.predict(x), base_rate))
    return folds


def evaluate_prob_folds(folds, h):
    n = len(folds)
    if n < MIN_TEST_FOLDS:
        return None
    half = n // 2
    sel, ev = folds[:half], folds[half:]

    def bss(fs):
        b_model = brier_score([p for _, _, p, _ in fs], [int(o) for _, o, _, _ in fs])
        b_base = brier_score([r for _, _, _, r in fs], [int(o) for _, o, _, _ in fs])
        return 1 - b_model / max(1e-9, b_base), b_model, b_base

    def dm(fs):
        lm = [(p - o) ** 2 for _, o, p, _ in fs]
        lb = [(r - o) ** 2 for _, o, _, r in fs]
        r = diebold_mariano(lm, lb, h=h)
        return r[1] if r else None

    bs_ev, b_model, b_base = bss(ev)
    table = reliability_table(
        [p for _, _, p, _ in ev], [int(o) for _, o, _, _ in ev], bins=5
    )
    ece = sum(r["n"] * abs(r["observed"] - r["mean_predicted"]) for r in table) / len(
        ev
    )
    return {
        "n_folds": n,
        "bss_select": bss(sel)[0],
        "bss_eval": bs_ev,
        "brier": b_model,
        "brier_base": b_base,
        "dm_p_select": dm(sel),
        "dm_p_eval": dm(ev),
        "ece": ece,
        "reliability_table": table,
        "base_rate_eval": mean(o for _, o, _, _ in ev),
    }


def probability_forecast(
    price, oil, news, market, origin, feats_now, x_cents, debug=None
) -> dict:
    out = {"x_cents": x_cents, "horizons": [], "any_validated": False}
    for h in cfg.PROB_HORIZON_DAYS:
        samples = _samples(price, oil, news, market, h)
        target_wd = (origin + timedelta(days=h)).weekday()
        evals = {}
        for name, spec in PROB_VARIANTS.items():
            ev = evaluate_prob_folds(_prob_walk_forward(samples, spec, h, x_cents), h)
            if ev:
                evals[name] = ev
        if debug is not None:
            debug.setdefault("prob", {})[h] = evals
        entry = {"hours": h * 24, "validated": False, "probability": None}
        eligible = {
            n: e
            for n, e in evals.items()
            if e["bss_select"] >= cfg.PROB_MIN_BSS
            and e["dm_p_select"] is not None
            and e["dm_p_select"] < cfg.TREND_MAX_DM_P
            and _row(feats_now, PROB_VARIANTS[n], target_wd) is not None
        }
        chosen = (
            max(eligible, key=lambda n: eligible[n]["bss_select"]) if eligible else None
        )
        shown = (
            evals[chosen]
            if chosen
            else (max(evals.values(), key=lambda e: e["bss_eval"]) if evals else None)
        )
        if shown:
            validated = bool(
                chosen
                and shown["bss_eval"] >= cfg.PROB_MIN_BSS
                and shown["ece"] <= cfg.PROB_MAX_ECE
            )
            entry.update(
                model=chosen,
                validated=validated,
                brier=round(shown["brier"], 4),
                brier_base=round(shown["brier_base"], 4),
                brier_skill=round(shown["bss_eval"], 3),
                dm_p_eval=(
                    None if shown["dm_p_eval"] is None else round(shown["dm_p_eval"], 3)
                ),
                ece=round(shown["ece"], 3),
                base_rate=round(shown["base_rate_eval"], 3),
                reliability_table=[
                    {
                        k: (round(v, 3) if isinstance(v, float) else v)
                        for k, v in r.items()
                    }
                    for r in shown["reliability_table"]
                ],
                n_test=shown["n_folds"],
            )
            if chosen:
                spec = PROB_VARIANTS[chosen]
                train = [
                    (_row(f, spec, wd), 1.0 if y > x_cents else 0.0)
                    for t, f, wd, y in samples
                    if t + timedelta(days=h) <= origin and _row(f, spec, wd) is not None
                ][-MAX_TRAIN:]
                model = Logistic().fit([a for a, _ in train], [b for _, b in train])
                entry["probability"] = round(
                    model.predict(_row(feats_now, spec, target_wd)), 3
                )
                if validated:
                    entry["level"] = (
                        "High"
                        if shown["bss_eval"] >= cfg.PROB_HIGH_BSS
                        and shown["ece"] <= cfg.PROB_HIGH_ECE
                        else "Medium"
                    )
        out["horizons"].append(entry)
    out["any_validated"] = any(e["validated"] for e in out["horizons"])
    return out


# --- hourly forecast -----------------------------------------------------------


def _hour_shape_at(days: dict, upto: date, weekend: Optional[bool] = None):
    """Recency-weighted mean deviation of each hour from its day's mean, days <= upto."""
    num, den = defaultdict(float), defaultdict(float)
    n_days = 0
    for d, hrs in days.items():
        age = (upto - d).days
        if age < 0 or age >= cfg.HOURLY_SHAPE_DAYS or len(hrs) < cfg.HOURLY_MIN_HOURS:
            continue
        if weekend is not None and (d.weekday() >= 5) != weekend:
            continue
        w = 0.5 ** (age / cfg.HOURLY_SHAPE_HALF_LIFE_DAYS)
        m = mean(hrs.values())
        n_days += 1
        for h, v in hrs.items():
            num[h] += w * (v - m)
            den[h] += w
    if n_days < cfg.HOURLY_MIN_SHAPE_DAYS:
        return None
    return {h: num[h] / den[h] for h in den if den[h] > 0}


def _hourly_predict(days, origin, target, variant):
    """Predicted {hour: price} for day `target` using only days <= origin."""
    shape = None
    if variant == "weekend_split":
        shape = _hour_shape_at(days, origin, weekend=target.weekday() >= 5)
    if shape is None:  # plain variant, or too few weekend/weekday days
        shape = _hour_shape_at(days, origin)
    hrs = days.get(origin)
    if shape is None or not hrs or len(hrs) < cfg.HOURLY_MIN_HOURS:
        return None
    level = mean(
        v - shape.get(h, 0.0) for h, v in hrs.items()
    )  # day level, shape removed
    return {h: level + s for h, s in shape.items()}


def hourly_forecast(days: dict, today: date) -> dict:
    """Hourly forecast of the day after the latest complete day, with its backtest."""
    out = {"validated": False, "reason": None}
    complete = sorted(d for d, hrs in days.items() if len(hrs) >= cfg.HOURLY_MIN_HOURS)
    if len(complete) < cfg.HOURLY_MIN_SHAPE_DAYS + MIN_TEST_FOLDS:
        out["reason"] = "not enough days with hourly data"
        return out
    variants = ("plain", "weekend_split")
    per_day = {
        v: [] for v in variants
    }  # [(target, model_mae, same_hour_yesterday, same_hour_last_week)]
    for origin in complete:
        target = origin + timedelta(days=1)
        actual = days.get(target)
        b1 = days.get(origin)
        b2 = days.get(target - timedelta(days=7))
        if not actual or len(actual) < cfg.HOURLY_MIN_HOURS or not b1 or not b2:
            continue
        for v in variants:
            pred = _hourly_predict(days, origin, target, v)
            if pred is None:
                continue
            hrs = [h for h in actual if h in pred and h in b1 and h in b2]
            if len(hrs) < cfg.HOURLY_MIN_HOURS:
                continue
            per_day[v].append(
                (
                    target,
                    mean(abs(actual[h] - pred[h]) for h in hrs) * 100,
                    mean(abs(actual[h] - b1[h]) for h in hrs) * 100,
                    mean(abs(actual[h] - b2[h]) for h in hrs) * 100,
                )
            )
    best = None
    for v in variants:
        rows = per_day[v]
        if len(rows) < MIN_TEST_FOLDS:
            continue
        half = len(rows) // 2
        sel, ev = rows[:half], rows[half:]
        score = mean(r[1] for r in sel) - min(
            mean(r[2] for r in sel), mean(r[3] for r in sel)
        )
        if best is None or score < best[0]:
            best = (score, v, ev)
    if best is None:
        out["reason"] = "not enough backtest days"
        return out
    _, variant, ev = best
    m_mae = mean(r[1] for r in ev)
    b1_mae, b2_mae = mean(r[2] for r in ev), mean(r[3] for r in ev)
    better = 2 if b1_mae <= b2_mae else 3
    dm = diebold_mariano([r[1] for r in ev], [r[better] for r in ev], h=1)
    out.update(
        variant=variant,
        mae_cents=round(m_mae, 2),
        baseline_same_hour_yesterday_mae=round(b1_mae, 2),
        baseline_same_hour_last_week_mae=round(b2_mae, 2),
        dm_p_vs_best_baseline=None if dm is None else round(dm[1], 3),
        n_test_days=len(ev),
    )
    out["validated"] = bool(
        m_mae < min(b1_mae, b2_mae) and dm is not None and dm[1] < cfg.TREND_MAX_DM_P
    )
    origin = complete[-1]
    if out["validated"] and (today - origin).days <= MAX_ORIGIN_AGE_DAYS:
        target = origin + timedelta(days=1)
        pred = _hourly_predict(days, origin, target, variant)
        if pred:
            out["target_date"] = target.isoformat()
            out["forecast"] = [
                {"hour": h, "price": round(p, 4)} for h, p in sorted(pred.items())
            ]
    return out


# --- public API ----------------------------------------------------------------


def build_trend_forecast(
    price: dict[date, float],
    oil: dict[date, float],
    news: dict[date, float],
    today: date,
    horizons: tuple[int, ...] = HORIZONS,
    market: Optional[dict[str, dict[date, float]]] = None,
    hourly_days: Optional[dict] = None,
    rise_cents: float = cfg.PROB_RISE_CENTS,
    debug: Optional[dict] = None,
) -> dict:
    """`debug`, if given, receives the full per-variant evaluations (used by trend_backtest.py)."""
    result = {
        "insufficient_data": True,
        "reason": None,
        "origin_date": None,
        "latest_price": None,
        "days_used": len(price),
        "oil_days": len(oil),
        "news_days": len(news),
        "market_days": {k: len(v) for k, v in (market or {}).items()},
        "horizons": [],
        "method": (
            "Ridge and quantile regression on price momentum, mean reversion, weekday, Brent, "
            "refined products, EUR/USD and news pressure, validated with a walk-forward backtest "
            "against the 'price stays the same' baseline."
        ),
    }
    if not price:
        result["reason"] = "No usable price history yet."
        return result
    origin = max(price)
    result["origin_date"] = origin.isoformat()
    result["latest_price"] = round(price[origin], 4)
    if (today - origin).days > MAX_ORIGIN_AGE_DAYS:
        result["reason"] = (
            f"The latest complete day of data is {origin.isoformat()}, "
            f"which is too old for a trend forecast."
        )
        return result
    if len(price) < cfg.TREND_MIN_USABLE_DAYS:
        result["reason"] = f"Need more history (have {len(price)} usable days)."
        return result

    result["insufficient_data"] = False
    feats_now = features_at(origin, price, oil, news, market)

    for h in horizons:
        target_date = origin + timedelta(days=h)
        samples = _samples(price, oil, news, market, h)
        evals = {}
        for name, spec in VARIANTS.items():
            ev = evaluate_folds(_walk_forward(samples, spec, h), h)
            if ev:
                evals[name] = ev
        if debug is not None:
            debug.setdefault("trend", {})[h] = evals

        eligible = {
            n: e
            for n, e in evals.items()
            if e["skill_select"] >= MIN_SKILL_TO_SELECT
            and e["dm_p_select"] is not None
            and e["dm_p_select"] < cfg.TREND_MAX_DM_P
            and _row(feats_now, VARIANTS[n], target_date.weekday()) is not None
        }
        chosen = (
            max(eligible, key=lambda n: eligible[n]["skill_select"])
            if eligible
            else None
        )

        entry = {
            "h": h,
            "date": target_date.isoformat(),
            "variants_tested": {n: round(e["skill_eval"], 3) for n, e in evals.items()},
        }
        if chosen and evals[chosen]["skill_eval"] > 0:
            ev = evals[chosen]
            spec = VARIANTS[chosen]
            names = spec["features"]
            train = [
                (_row(f, spec, wd), y)
                for t, f, wd, y in samples
                if t + timedelta(days=h) <= origin and _row(f, spec, wd) is not None
            ][-MAX_TRAIN:]
            model = _make_model(spec).fit([a for a, _ in train], [b for _, b in train])
            x_now = _row(feats_now, spec, target_date.weekday())
            change = model.predict(x_now)
            contrib = model.contributions(x_now)[: len(names)]
            drivers = sorted(
                (
                    {"feature": FEATURE_LABELS[n], "effect_cents": round(c, 2)}
                    for n, c in zip(names, contrib)
                ),
                key=lambda d: -abs(d["effect_cents"]),
            )[:3]
            entry.update(
                model=chosen,
                beats_baseline=True,
                expected_change_cents=round(change, 2),
                range_low_cents=round(change + ev["band_low"], 2),
                range_high_cents=round(change + ev["band_high"], 2),
                interval_cents=round((ev["band_high"] - ev["band_low"]) / 2, 2),
                skill_vs_persistence=round(ev["skill_eval"], 3),
                mae_cents=round(ev["mae_eval"], 2),
                baseline_mae_cents=round(ev["mae_persistence_eval"], 2),
                n_train=len(train),
                n_test=ev["n_folds"],
                drivers=drivers,
            )
        else:
            best = max(evals.values(), key=lambda e: e["skill_eval"]) if evals else None
            ev = best
            entry.update(
                model="persistence",
                beats_baseline=False,
                expected_change_cents=0.0,
                range_low_cents=round(best["base_band_low"], 2) if best else None,
                range_high_cents=round(best["base_band_high"], 2) if best else None,
                interval_cents=(
                    round((best["base_band_high"] - best["base_band_low"]) / 2, 2)
                    if best
                    else None
                ),
                skill_vs_persistence=round(best["skill_eval"], 3) if best else None,
                mae_cents=round(best["mae_persistence_eval"], 2) if best else None,
                baseline_mae_cents=(
                    round(best["mae_persistence_eval"], 2) if best else None
                ),
                n_train=len(samples),
                n_test=best["n_folds"] if best else 0,
                drivers=[],
            )
        if ev:
            entry.update(
                dm_p_eval=(
                    None if ev["dm_p_eval"] is None else round(ev["dm_p_eval"], 3)
                ),
                dm_p_select=(
                    None if ev["dm_p_select"] is None else round(ev["dm_p_select"], 3)
                ),
                coverage80=round(ev["coverage80"], 3),
                coverage80_raw_sigma=(
                    None
                    if ev["coverage80_raw_sigma"] is None
                    else round(ev["coverage80_raw_sigma"], 3)
                ),
                band_calibrated=ev["calibrated"],
                directional_accuracy=(
                    None
                    if ev["directional_accuracy"] is None
                    else round(ev["directional_accuracy"], 3)
                ),
                directional_baseline=(
                    None
                    if ev["directional_base"] is None
                    else round(ev["directional_base"], 3)
                ),
                pinball10=round(ev["pinball10"], 3),
                pinball90=round(ev["pinball90"], 3),
                pinball10_baseline=round(ev["pinball10_base"], 3),
                pinball90_baseline=round(ev["pinball90_base"], 3),
                reliability=reliability_level(ev, entry["beats_baseline"]),
            )
        else:
            entry["reliability"] = {"level": "Low", "why": "not enough backtest days"}
        change = entry["expected_change_cents"]
        thr = max(0.3, 0.5 * (entry["interval_cents"] or 0) / 1.28)
        entry["direction"] = (
            "rising" if change >= thr else "falling" if change <= -thr else "flat"
        )
        entry["expected_price"] = round(price[origin] + change / 100, 4)
        result["horizons"].append(entry)

    result["any_model_beats_baseline"] = any(
        e["beats_baseline"] for e in result["horizons"]
    )
    result["probability"] = probability_forecast(
        price, oil, news, market, origin, feats_now, rise_cents, debug
    )
    if hourly_days:
        result["hourly"] = hourly_forecast(hourly_days, today)
        if debug is not None:
            debug["hourly"] = result["hourly"]
    return result
