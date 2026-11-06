"""Small, dependency-free trend model for the area-average pump price.

Pure functions only (no database access), so the model can be unit-tested and
backtested on any data. The router in ``routers/insights.py`` assembles the
daily series and calls :func:`build_trend_forecast`.

What it does
------------
For each horizon h (days ahead) it predicts the CHANGE in the daily average
price versus the latest complete day:

    y = price[t + h] - price[t]          (in cents)

using ridge regression on a handful of features known at the end of day t:

    weekday of the target day   (learned, replaces the old fixed weekday table)
    mom_short   today vs. the previous 3 days            (momentum)
    mom_week    last 3 days vs. 7-9 days ago             (weekly drift)
    reversion   today vs. the 28-day mean                (mean reversion)
    oil_mom     Brent EUR/L, last 3 days vs. 7-9 days ago
    oil_rel     Brent EUR/L, last 3 days vs. its 28-day mean
    news_3d     keyword-scored supply-risk news, last 3 days

Honesty rules
-------------
* Every candidate model is evaluated with an expanding-window walk-forward
  backtest, using only information that was available at each origin day
  (a training sample is only used once its target day has actually happened).
* Candidates are compared to the naive baseline "price stays the same". The
  variant is SELECTED on the first half of the backtest and its skill is
  REPORTED on the second half, so the reported number is not the one that was
  optimised.
* If no candidate beats the baseline out-of-sample, the baseline is returned
  (expected change 0) and the result says so. Missing days are never filled.
"""

import math
from datetime import date, timedelta
from statistics import mean, pstdev
from typing import Callable, Optional

HORIZONS = (1, 2, 3, 5, 7)
MIN_TRAIN = 25  # samples needed before a walk-forward fold is trusted
MIN_TEST_FOLDS = 24  # folds needed (split in two halves) to validate a variant
MIN_SKILL_TO_SELECT = 0.03  # must beat persistence by >= 3% MAE on selection half
RIDGE_LAMBDA = 3.0
REFIT_EVERY = (
    4  # walk-forward: refit every N folds (keeps backtest fast; still leak-free)
)
MAX_TRAIN = 400  # most recent samples used for fitting
MAX_ORIGIN_AGE_DAYS = 3  # latest complete day may be at most this old

PRICE_FEATURES = ["mom_short", "mom_week", "reversion"]
# Candidate models. `weekday` adds six target-weekday dummies; with little data they
# can overfit, so lean variants without them are tried as well.
VARIANTS = {
    "weekday": {"features": [], "weekday": True},
    "momentum": {"features": PRICE_FEATURES, "weekday": False},
    "price": {"features": PRICE_FEATURES, "weekday": True},
    "momentum_oil": {
        "features": PRICE_FEATURES + ["oil_mom", "oil_rel"],
        "weekday": False,
    },
    "momentum_oil_news": {
        "features": PRICE_FEATURES + ["oil_mom", "oil_rel", "news_3d"],
        "weekday": False,
    },
}
FEATURE_LABELS = {
    "mom_short": "recent momentum",
    "mom_week": "weekly drift",
    "reversion": "distance from 28-day average",
    "oil_mom": "Brent trend",
    "oil_rel": "Brent vs. its 28-day average",
    "news_3d": "supply-risk news",
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


class Ridge:
    """Ridge regression on standardised inputs with an unpenalised intercept."""

    def __init__(self, lam: float = RIDGE_LAMBDA):
        self.lam = lam
        self.means: list[float] = []
        self.stds: list[float] = []
        self.coef: list[float] = []
        self.y_mean = 0.0

    def fit(self, X: list[list[float]], y: list[float]) -> "Ridge":
        n, k = len(X), len(X[0]) if X else 0
        self.y_mean = mean(y)
        self.means = [mean(col) for col in zip(*X)] if k else []
        self.stds = [(pstdev(col) or 1.0) for col in zip(*X)] if k else []
        if k == 0:
            self.coef = []
            return self
        Z = [[(row[j] - self.means[j]) / self.stds[j] for j in range(k)] for row in X]
        yc = [v - self.y_mean for v in y]
        a = [
            [sum(Z[i][p] * Z[i][q] for i in range(n)) for q in range(k)]
            for p in range(k)
        ]
        for p in range(k):
            a[p][p] += self.lam
        b = [sum(Z[i][p] * yc[i] for i in range(n)) for p in range(k)]
        self.coef = _solve(a, b)
        return self

    def predict(self, x: list[float]) -> float:
        return self.y_mean + sum(
            c * (v - m) / s for c, v, m, s in zip(self.coef, x, self.means, self.stds)
        )

    def contributions(self, x: list[float]) -> list[float]:
        return [
            c * (v - m) / s for c, v, m, s in zip(self.coef, x, self.means, self.stds)
        ]


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
    t: date, price: dict, oil: dict, news: dict
) -> dict[str, Optional[float]]:
    """Features known at the end of day t. Values are in cents / percent."""
    p0 = price.get(t)
    f: dict[str, Optional[float]] = {k: None for k in FEATURE_LABELS}
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
    return f


def _row(feats: dict, spec: dict, target_weekday: int) -> Optional[list[float]]:
    xs = []
    for name in spec["features"]:
        if feats[name] is None:
            return None
        xs.append(feats[name])
    if spec["weekday"]:
        xs.extend(
            1.0 if target_weekday == wd else 0.0 for wd in range(1, 7)
        )  # Monday = baseline
    return xs


def _mae(errs: list[float]) -> float:
    return sum(abs(e) for e in errs) / len(errs)


# --- walk-forward backtest -----------------------------------------------------


def _samples(price, oil, news, h):
    out = []
    for t in sorted(price):
        target = t + timedelta(days=h)
        if target in price:
            out.append(
                (
                    t,
                    features_at(t, price, oil, news),
                    target.weekday(),
                    (price[target] - price[t]) * 100,
                )
            )
    return out


def _walk_forward(samples, spec: dict, h: int):
    """Return [(origin, error_model, error_persistence)] for each usable fold."""
    usable = [(t, _row(f, spec, wd), wd, y) for t, f, wd, y in samples]
    usable = [u for u in usable if u[1] is not None]
    folds = []
    model, since_fit = None, REFIT_EVERY
    for t, x, _, y in usable:
        if since_fit >= REFIT_EVERY or model is None:
            # a sample is only known once its target day (t' + h) has happened
            train = [
                (xx, yy) for tt, xx, _, yy in usable if tt + timedelta(days=h) <= t
            ][-MAX_TRAIN:]
            if len(train) < MIN_TRAIN:
                continue
            model = Ridge().fit([a for a, _ in train], [b for _, b in train])
            since_fit = 0
        since_fit += 1
        folds.append((t, y - model.predict(x), y))
    return folds


def _evaluate_variant(folds):
    if len(folds) < MIN_TEST_FOLDS:
        return None
    half = len(folds) // 2
    sel, ev = folds[:half], folds[half:]
    skill = lambda fs: 1 - _mae([e for _, e, _ in fs]) / max(
        1e-9, _mae([p for _, _, p in fs])
    )
    return {
        "n_folds": len(folds),
        "skill_select": skill(sel),
        "skill_eval": skill(ev),
        "mae_eval": _mae([e for _, e, _ in ev]),
        "mae_persistence_eval": _mae([p for _, _, p in ev]),
        "sigma": pstdev([e for _, e, _ in ev]) if len(ev) > 1 else None,
    }


# --- public API ----------------------------------------------------------------


def build_trend_forecast(
    price: dict[date, float],
    oil: dict[date, float],
    news: dict[date, float],
    today: date,
    horizons: tuple[int, ...] = HORIZONS,
) -> dict:
    result = {
        "insufficient_data": True,
        "reason": None,
        "origin_date": None,
        "latest_price": None,
        "days_used": len(price),
        "oil_days": len(oil),
        "news_days": len(news),
        "horizons": [],
        "method": (
            "Ridge regression on price momentum, mean reversion, weekday, Brent and "
            "news pressure, validated with a walk-forward backtest against the "
            "'price stays the same' baseline."
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
    if len(price) < MIN_TRAIN + 10:
        result["reason"] = f"Need more history (have {len(price)} usable days)."
        return result

    result["insufficient_data"] = False
    feats_now = features_at(origin, price, oil, news)

    for h in horizons:
        target_date = origin + timedelta(days=h)
        samples = _samples(price, oil, news, h)
        evals = {}
        for name, spec in VARIANTS.items():
            ev = _evaluate_variant(_walk_forward(samples, spec, h))
            if ev:
                evals[name] = ev

        eligible = {
            n: e
            for n, e in evals.items()
            if e["skill_select"] >= MIN_SKILL_TO_SELECT
            and _row(feats_now, VARIANTS[n], target_date.weekday())
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
            model = Ridge().fit([a for a, _ in train], [b for _, b in train])
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
            sigma = ev["sigma"] or ev["mae_eval"]
            entry.update(
                model=chosen,
                beats_baseline=True,
                expected_change_cents=round(change, 2),
                interval_cents=round(1.28 * sigma, 2),  # ~80% interval
                skill_vs_persistence=round(ev["skill_eval"], 3),
                mae_cents=round(ev["mae_eval"], 2),
                baseline_mae_cents=round(ev["mae_persistence_eval"], 2),
                n_train=len(train),
                n_test=ev["n_folds"],
                drivers=drivers,
            )
        else:
            best = max(evals.values(), key=lambda e: e["skill_eval"]) if evals else None
            entry.update(
                model="persistence",
                beats_baseline=False,
                expected_change_cents=0.0,
                interval_cents=(
                    round(1.28 * best["mae_persistence_eval"], 2) if best else None
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
    return result
