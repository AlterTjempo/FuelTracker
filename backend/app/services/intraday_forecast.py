"""Next-12-hours forecast of the area-average pump price, hour by hour.

Pure functions only (no database access), so it can be unit-tested and
backtested on any data. ``routers/insights.py`` builds the hourly series and
calls :func:`build_intraday_forecast`; a scheduled job refreshes the result.

Candidates
----------
* ``anchored_yesterday``: yesterday's curve, shifted by how much the latest
  hour differs from the same hour yesterday. Strong for the first hours.
* ``shape``: the learned hour-of-day shape (weekday/weekend, recency weighted,
  from complete days *before* the forecast day) anchored on the latest hours.
* ``blend``: the average of the two above.
* ``same_hour_yesterday``: the price 24 hours earlier (baseline).
* ``persistence``: "stays as it is now" (baseline).

Which candidate works best depends on how far ahead you look (anchoring on
the current price helps most in the first hours, the daily rhythm later), so
the method is chosen **per hour ahead**.

Honesty rules (same as forecast_model.py)
-----------------------------------------
* Walk-forward: a prediction from origin hour ``o`` only uses hours <= ``o``
  and day shapes from days before ``o``'s date.
* All candidates are compared on the same (origin, hour-ahead) pairs. The first
  half of the backtest SELECTS the method per hour ahead and sets the band
  (empirical error quantiles); the second half REPORTS the accuracy, the
  baselines' accuracy and how often the real price fell inside the band.
* Missing hours are never filled; with too little or too old data the result
  says so instead of guessing.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Optional

import analytics_config as cfg
from services.forecast_model import _hour_shape_at

HOUR = timedelta(hours=1)
METHODS = (
    "anchored_yesterday",
    "shape",
    "blend",
    "same_hour_yesterday",
    "persistence",
)
BASELINES = ("same_hour_yesterday", "persistence")
METHOD_NAMES = {
    "anchored_yesterday": "yesterday's curve shifted to today's level",
    "shape": "daily price rhythm",
    "blend": "mix of yesterday's curve and the daily rhythm",
    "same_hour_yesterday": "same hour yesterday",
    "persistence": "price stays as it is now",
}


def _complete_days(hours: dict) -> dict:
    """{date: {hour: price}} for days with enough hours to learn a shape from."""
    days = defaultdict(dict)
    for t, p in hours.items():
        days[t.date()][t.hour] = p
    return {d: h for d, h in days.items() if len(h) >= cfg.HOURLY_MIN_HOURS}


class _Shapes:
    """Hour-of-day shapes learned from days strictly before a given date (cached)."""

    def __init__(self, days: dict):
        self.days = days
        self._cache: dict = {}

    def get(self, before: date, target_day: date) -> Optional[dict]:
        weekend = target_day.weekday() >= 5
        key = (before, weekend)
        if key not in self._cache:
            upto = before - timedelta(days=1)
            hl = cfg.INTRADAY_SHAPE_HALF_LIFE_DAYS
            shape = _hour_shape_at(self.days, upto, weekend=weekend, half_life=hl)
            if shape is None:  # too few weekend (or weekday) days: use all days
                shape = _hour_shape_at(self.days, upto, half_life=hl)
            self._cache[key] = shape
        return self._cache[key]


def _targets(origin: datetime) -> list:
    return [origin + k * HOUR for k in range(1, cfg.INTRADAY_HORIZON_HOURS + 1)]


def _shape_pred(hours: dict, origin: datetime, shapes: _Shapes) -> dict:
    level_samples = []
    for i in range(cfg.INTRADAY_ANCHOR_HOURS):
        a = origin - i * HOUR
        shape = shapes.get(origin.date(), a.date())
        if a in hours and shape and a.hour in shape:
            level_samples.append(hours[a] - shape[a.hour])
    if not level_samples:
        return {}
    level = mean(level_samples)
    out = {}
    for t in _targets(origin):
        shape = shapes.get(origin.date(), t.date())
        if shape and t.hour in shape:
            out[t] = level + shape[t.hour]
    return out


def _anchored_yesterday(hours: dict, origin: datetime, n_anchor: int) -> dict:
    """Yesterday's prices shifted by the mean of (latest hours - same hours yesterday)."""
    diffs = [
        hours[a] - hours[a - 24 * HOUR]
        for a in (origin - i * HOUR for i in range(n_anchor))
        if a in hours and (a - 24 * HOUR) in hours
    ]
    if not diffs:
        return {}
    offset = mean(diffs)
    return {
        t: hours[t - 24 * HOUR] + offset
        for t in _targets(origin)
        if (t - 24 * HOUR) in hours
    }


def _predict_all(hours: dict, origin: datetime, shapes: _Shapes) -> dict:
    """{method: {target hour: price}} for 1..horizon hours after `origin`, using hours <= origin."""
    if origin not in hours:
        return {m: {} for m in METHODS}
    now_price = hours[origin]
    shape = _shape_pred(hours, origin, shapes)
    anchored = _anchored_yesterday(hours, origin, 1)
    anchored_n = _anchored_yesterday(hours, origin, cfg.INTRADAY_ANCHOR_HOURS)
    return {
        "anchored_yesterday": anchored,
        "shape": shape,
        "blend": {t: (shape[t] + anchored_n[t]) / 2 for t in shape if t in anchored_n},
        # t - 24 h is always <= origin because the horizon is shorter than a day
        "same_hour_yesterday": {
            t: hours[t - 24 * HOUR]
            for t in _targets(origin)
            if (t - 24 * HOUR) in hours
        },
        "persistence": {t: now_price for t in _targets(origin)},
    }


def _quantile(xs: list, q: float) -> float:
    s = sorted(xs)
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _backtest(hours: dict, shapes: _Shapes, latest: datetime) -> list:
    """Per origin: {lead: {method: (predicted, actual)}} where every method predicted."""
    start = latest - timedelta(days=cfg.INTRADAY_BACKTEST_DAYS)
    rows = []
    for origin in sorted(
        t for t in hours if start <= t <= latest - cfg.INTRADAY_HORIZON_HOURS * HOUR
    ):
        preds = _predict_all(hours, origin, shapes)
        per_lead = {}
        for k, t in enumerate(_targets(origin), start=1):
            if t in hours and all(t in preds[m] for m in METHODS):
                per_lead[k] = {m: (preds[m][t], hours[t]) for m in METHODS}
        if per_lead:
            rows.append(per_lead)
    return rows


def _errors(rows: list, method: str, lead: int) -> list:
    """Signed errors (actual - predicted) in EUR for one method and hour ahead."""
    return [r[lead][method][1] - r[lead][method][0] for r in rows if lead in r]


def build_intraday_forecast(hours: dict, now: datetime) -> dict:
    """Forecast the next hours from `hours` ({local naive hour start: price}).

    `now` is local naive time. Returns the forecast, its band and its backtest.
    """
    out = {"insufficient_data": True, "reason": None}
    if not hours:
        out["reason"] = "No hourly price data yet."
        return out
    latest = max(hours)
    shapes = _Shapes(_complete_days(hours))
    leads = range(1, cfg.INTRADAY_HORIZON_HOURS + 1)

    rows = _backtest(hours, shapes, latest)
    half = len(rows) // 2
    if half < cfg.INTRADAY_MIN_ORIGINS:
        out["reason"] = (
            "Not enough recent hourly data to test the forecast yet "
            f"({len(rows)} of {2 * cfg.INTRADAY_MIN_ORIGINS} test hours)."
        )
        return out
    select, evaluate = rows[:half], rows[half:]

    # Per hour ahead: rank the methods on the selection half (best first) and
    # take each method's band from its selection-half errors.
    lo_q, hi_q = cfg.INTRADAY_BAND
    ranking, band = {}, {}
    for k in leads:
        mae = {m: mean(abs(e) for e in _errors(select, m, k) or [9.9]) for m in METHODS}
        ranking[k] = sorted(METHODS, key=lambda m: mae[m])
        for m in METHODS:
            errs = _errors(select, m, k)
            if len(errs) >= cfg.INTRADAY_MIN_ORIGINS:
                band[(k, m)] = (_quantile(errs, lo_q), _quantile(errs, hi_q))

    # Report on the evaluation half: the chosen method per hour ahead vs. baselines.
    def eval_mae(k: int, method: str) -> Optional[float]:
        errs = _errors(evaluate, method, k)
        return mean(abs(e) for e in errs) * 100 if errs else None

    chosen = {k: ranking[k][0] for k in leads}
    by_lead = [
        {"h": k, "method": chosen[k], "mae_cents": round(v, 2)}
        for k in leads
        if (v := eval_mae(k, chosen[k])) is not None
    ]
    inside = total = 0
    for k in leads:
        b = band.get((k, chosen[k]))
        if b:
            for e in _errors(evaluate, chosen[k], k):
                total += 1
                inside += b[0] <= e <= b[1]
    mae = mean(r["mae_cents"] for r in by_lead)
    baselines = {}
    for m in BASELINES:
        vals = [v for k in leads if (v := eval_mae(k, m)) is not None]
        baselines[m] = round(mean(vals), 2) if vals else None
    steps = []  # distinct methods in hour-ahead order, for a readable description
    for k in leads:
        if not steps or steps[-1] != chosen[k]:
            steps.append(chosen[k])
    level = (
        "High"
        if mae <= cfg.INTRADAY_HIGH_MAE_CENTS
        else "Medium" if mae <= cfg.INTRADAY_MEDIUM_MAE_CENTS else "Low"
    )
    out["accuracy"] = {
        "method_name": ", then ".join(METHOD_NAMES[m] for m in steps),
        "mae_cents": round(mae, 2),
        "mae_by_hour_ahead": by_lead,
        "baselines": baselines,
        "beats_baselines": all(v is None or mae < v for v in baselines.values()),
        "band_coverage": round(inside / total, 3) if total else None,
        "band_target": round(hi_q - lo_q, 2),
        "test_hours": len(evaluate),
        "level": level,
    }

    age_hours = (now - latest) / HOUR
    if age_hours > cfg.INTRADAY_MAX_DATA_AGE_HOURS:
        out["reason"] = (
            f"The latest price data is {age_hours:.0f} hours old, too old to forecast from."
        )
        return out

    preds = _predict_all(hours, latest, shapes)
    forecast = []
    for k, t in enumerate(_targets(latest), start=1):
        # Best available method for this hour ahead (a method can lack an input, e.g. yesterday's hour).
        m = next((m for m in ranking[k] if t in preds[m]), None)
        if m is None:
            continue
        row = {"t": t, "h": k, "method": m, "price": round(preds[m][t], 4)}
        if (k, m) in band:
            row["low"] = round(preds[m][t] + band[(k, m)][0], 4)
            row["high"] = round(preds[m][t] + band[(k, m)][1], 4)
        forecast.append(row)
    if not forecast:
        out["reason"] = "Not enough recent hours to anchor the forecast."
        return out

    now_price = hours[latest]
    cheapest = min(forecast, key=lambda r: r["price"])
    priciest = max(forecast, key=lambda r: r["price"])
    jumps = [(forecast[0]["t"], forecast[0]["price"] - now_price)] + [
        (b["t"], b["price"] - a["price"]) for a, b in zip(forecast, forecast[1:])
    ]
    jump_t, jump = max(jumps, key=lambda s: s[1])

    used = (
        []
    )  # methods this forecast really used (a fallback can differ from the backtest pick)
    for r in forecast:
        if not used or used[-1] != r["method"]:
            used.append(r["method"])

    out.update(
        insufficient_data=False,
        reason=None,
        method_name=", then ".join(METHOD_NAMES[m] for m in used),
        origin={"t": latest, "price": round(now_price, 4)},
        history=[
            {"t": t, "price": round(p, 4)}
            for t, p in sorted(hours.items())
            if latest - t < timedelta(hours=cfg.INTRADAY_HORIZON_HOURS)
        ],
        forecast=forecast,
        summary={
            "cheapest": {"t": cheapest["t"], "price": cheapest["price"]},
            "priciest": {"t": priciest["t"], "price": priciest["price"]},
            "cheapest_vs_now_cents": round((cheapest["price"] - now_price) * 100, 1),
            "biggest_rise": (
                {"t": jump_t, "cents": round(jump * 100, 1)} if jump > 0 else None
            ),
        },
    )
    return out
