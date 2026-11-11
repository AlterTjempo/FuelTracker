"""Backtest and tuning of the Go Now indicator.

Run (inside the backend container, or anywhere the app's dependencies and the
database are available):

    python -m app.services.go_now_backtest --out docs/go-now-backtest.md
    python -m services.go_now_backtest      # when the working dir is app/

For every hour with data it reproduces the live decision using only data
available at that moment (same code: services/go_now.py) and measures what
going NOW would have saved compared with waiting:

    saving_a = mean(best price over the next 6 h) - best_now
    saving_b = min(best price over the next 12 h) - best_now

Positive = the user saved money by going now (waiting would have cost more).
saving_b compares with the BEST possible moment to wait for, so it is usually
negative: it is the "regret" of not waiting for the cheapest moment.

NOTE on the sign: the task text defined "current minus future" but also said
"positive means the user saved money by going now". Those contradict each
other; the economically correct definition (future minus current) is used. Gaps are never filled: an
outcome is only computed when at least 70% of the expected 15-minute cycles
exist in the future window.

Tuning follows the same discipline as the trend model: parameters are chosen
on the FIRST half of the data (in time) and everything is reported on the
SECOND half. Tuned values are only adopted if they beat the current ones out
of sample by a margin (analytics_config.GO_NOW_MIN_OOS_IMPROVEMENT_CENTS).
"""

import argparse
import bisect
import itertools
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analytics_config as cfg  # noqa: E402
from services import go_now as gn  # noqa: E402
from services.stats_utils import bootstrap_ci, bootstrap_diff_ci  # noqa: E402

GO_LABELS = ("excellent", "good")
STAY_LABELS = ("wait", "avoid")
ALL_LABELS = ("excellent", "good", "neutral", "wait", "avoid")


# ------------------------------------------------------------------ data ----


class Series:
    """Per-cycle best price plus hourly lows, built from raw (ts, station, price) rows."""

    def __init__(self, rows):
        self.cycle_ts: list[datetime] = []
        self.best: list[float] = []
        self.lows: dict[datetime, float] = {}
        last: dict = {}
        fresh = timedelta(minutes=cfg.GO_NOW_FRESH_MINUTES)
        current = None

        def finalize(ts):
            prices = [p for t, p in last.values() if ts - t <= fresh]
            if prices:
                self.cycle_ts.append(ts)
                self.best.append(min(prices))

        for ts, station, price in rows:
            if ts != current:
                if current is not None:
                    finalize(current)
                current = ts
            last[station] = (ts, price)
            hour = gn.floor_hour(ts)
            if hour not in self.lows or price < self.lows[hour]:
                self.lows[hour] = price
        if current is not None:
            finalize(current)

    def decision_times(self) -> list[int]:
        """Index of the last cycle in every hour (a decision as a user would see it)."""
        by_hour: dict = {}
        for i, ts in enumerate(self.cycle_ts):
            by_hour[gn.floor_hour(ts)] = i
        return [by_hour[h] for h in sorted(by_hour)]

    def future_window(self, i: int, hours: float) -> Optional[list[float]]:
        """Best prices of cycles in (T, T+hours], or None if coverage is too thin."""
        t0 = self.cycle_ts[i]
        end = t0 + timedelta(hours=hours)
        lo = bisect.bisect_right(self.cycle_ts, t0)
        hi = bisect.bisect_right(self.cycle_ts, end)
        expected = hours * 60 / cfg.BACKTEST_CYCLE_MINUTES
        if hi - lo < cfg.BACKTEST_MIN_FUTURE_COVERAGE * expected:
            return None
        return self.best[lo:hi]


def build_records(series: Series) -> list[dict]:
    """One record per decision time with everything needed to score any parameter set."""
    shape_cache: dict[date, dict] = {}
    records = []
    for i in series.decision_times():
        now = series.cycle_ts[i]
        price = series.best[i]
        day = now.astimezone(gn.BERLIN).date()
        if day not in shape_cache:
            day_start = now.astimezone(gn.BERLIN).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            shape_cache[day] = gn.hour_shape(series.lows, day_start)
        shape = shape_cache[day]
        stats = gn.percentile_stats(series.lows, now, price)
        if stats is None:
            continue
        fut_a = series.future_window(i, cfg.BACKTEST_FUTURE_MEAN_HOURS)
        fut_b = series.future_window(i, cfg.BACKTEST_FUTURE_MIN_HOURS)
        if fut_a is None:
            continue
        jump = gn.typical_jump(shape)
        htj = gn.hours_until(jump[0], now) if jump else None
        records.append(
            {
                "ts": now,
                "price": price,
                "pct": stats["percentile"],
                "slope_legacy": gn.trend_slope(series.lows, now, shape, "legacy"),
                "slope_robust": gn.trend_slope(series.lows, now, shape, "robust"),
                "pre_jump": htj is not None
                and cfg.GO_NOW_PRE_JUMP_MIN_H <= htj <= cfg.GO_NOW_PRE_JUMP_MAX_H,
                "saving_a": mean(fut_a) - price,
                "saving_b": (min(fut_b) - price) if fut_b is not None else None,
            }
        )
    return records


# --------------------------------------------------------------- scoring ----


def label_of(rec: dict, params: gn.GoNowParams) -> str:
    slope = (
        rec["slope_robust"] if params.trend_method == "robust" else rec["slope_legacy"]
    )
    trend_dir = gn.direction(slope, params.trend_threshold)
    return gn.recommend(rec["pct"], trend_dir, rec["pre_jump"], params)


def separation(records: list[dict], params: gn.GoNowParams) -> Optional[float]:
    """mean saving of GO labels minus mean saving of WAIT/AVOID labels, in cents.

    This is the score we optimise: a good indicator says "go" when going now
    saves money and "wait" when it does not. None if a group is too small.
    """
    go, stay = [], []
    for r in records:
        label = label_of(r, params)
        if label in GO_LABELS:
            go.append(r["saving_a"])
        elif label in STAY_LABELS:
            stay.append(r["saving_a"])
    if len(go) < cfg.BACKTEST_MIN_GROUP or len(stay) < cfg.BACKTEST_MIN_GROUP:
        return None
    return (mean(go) - mean(stay)) * 100


def label_table(records: list[dict], params: gn.GoNowParams) -> dict[str, dict]:
    groups = defaultdict(list)
    for r in records:
        groups[label_of(r, params)].append(r)
    out = {}
    for label in ALL_LABELS:
        rs = groups.get(label, [])
        a = [r["saving_a"] * 100 for r in rs]
        b = [r["saving_b"] * 100 for r in rs if r["saving_b"] is not None]
        out[label] = {
            "n": len(rs),
            "mean_a": mean(a) if a else None,
            "median_a": median(a) if a else None,
            "ci_a": bootstrap_ci(a, n=cfg.BACKTEST_BOOTSTRAP_N) if a else None,
            "share_better": (sum(1 for x in a if x >= 0) / len(a)) if a else None,
            "mean_b": mean(b) if b else None,
            "ci_b": bootstrap_ci(b, n=cfg.BACKTEST_BOOTSTRAP_N) if b else None,
            "values_a": a,
        }
    return out


def tune(train: list[dict]):
    """Grid search on the first half. Returns (best_params, best_score, n_tested)."""
    best, best_score, tested = None, None, 0
    for method, jump, cheap, exp, thr in itertools.product(
        ("legacy", "robust"),
        (False, True),
        cfg.GO_NOW_GRID_CHEAP,
        cfg.GO_NOW_GRID_EXPENSIVE,
        cfg.GO_NOW_GRID_TREND,
    ):
        if cheap >= exp:
            continue
        params = gn.GoNowParams(cheap, exp, thr, method, jump)
        score = separation(train, params)
        tested += 1
        if score is not None and (best_score is None or score > best_score):
            best, best_score = params, score
    return best, best_score, tested


# ---------------------------------------------------------------- report ----


def _c(x, d=2):
    return "–" if x is None else f"{x:.{d}f}"


def _ci(ci):
    return "–" if ci is None else f"[{ci[0]:.2f}, {ci[1]:.2f}]"


def _params_text(p: gn.GoNowParams) -> str:
    return (
        f"cheap ≤ {p.cheap_pct}, expensive > {p.expensive_pct}, trend ±{p.trend_threshold} c/h, "
        f"trend = {p.trend_method}, jump-aware = {'on' if p.jump_aware else 'off'}"
    )


def run(fuel: str, since_days: Optional[int]) -> dict:
    from database import (
        SessionLocal,
    )  # imported here so tests can import the module without a DB
    from models import FuelPrice

    column = {"e5": FuelPrice.e5, "e10": FuelPrice.e10, "diesel": FuelPrice.diesel}[
        fuel
    ]
    db = SessionLocal()
    try:
        q = db.query(FuelPrice.timestamp, FuelPrice.station_id, column).filter(
            column.isnot(None)
        )
        if since_days:
            q = q.filter(
                FuelPrice.timestamp
                >= datetime.now(timezone.utc) - timedelta(days=since_days)
            )
        rows = q.order_by(FuelPrice.timestamp).yield_per(50000)
        series = Series(rows)
    finally:
        db.close()
    return analyse(series, fuel)


def analyse(series: Series, fuel: str) -> dict:
    records = build_records(series)
    records.sort(key=lambda r: r["ts"])
    half = len(records) // 2
    train, test = records[:half], records[half:]

    current = gn.GoNowParams(
        35, 65, 0.1, "legacy", False
    )  # the values before this backtest
    variants = {
        "previous values (legacy trend, no jump-awareness)": current,
        "+ jump-aware": gn.GoNowParams(35, 65, 0.1, "legacy", True),
        "+ robust trend": gn.GoNowParams(35, 65, 0.1, "robust", False),
        "+ robust trend + jump-aware": gn.GoNowParams(35, 65, 0.1, "robust", True),
    }
    variant_scores = {
        name: {"train": separation(train, p), "test": separation(test, p)}
        for name, p in variants.items()
    }

    tuned, tuned_train, tested = (
        tune(train) if len(train) >= 2 * cfg.BACKTEST_MIN_GROUP else (None, None, 0)
    )
    tuned_test = separation(test, tuned) if tuned else None
    base_test = variant_scores["previous values (legacy trend, no jump-awareness)"][
        "test"
    ]
    adopt = (
        tuned is not None
        and tuned_test is not None
        and base_test is not None
        and tuned_test >= base_test + cfg.GO_NOW_MIN_OOS_IMPROVEMENT_CENTS
    )
    final = tuned if adopt else current
    table = label_table(test, final)
    exc, wait = table["excellent"]["values_a"], table["wait"]["values_a"]
    diff_ci = (
        bootstrap_diff_ci(exc, wait, n=cfg.BACKTEST_BOOTSTRAP_N)
        if exc and wait
        else None
    )

    return {
        "fuel": fuel,
        "n_cycles": len(series.cycle_ts),
        "first": series.cycle_ts[0] if series.cycle_ts else None,
        "last": series.cycle_ts[-1] if series.cycle_ts else None,
        "n_records": len(records),
        "n_train": len(train),
        "n_test": len(test),
        "test_from": test[0]["ts"] if test else None,
        "variants": {
            n: (_params_text(p), variant_scores[n]) for n, p in variants.items()
        },
        "tuned": tuned,
        "tuned_train": tuned_train,
        "tuned_test": tuned_test,
        "tested": tested,
        "adopt": adopt,
        "final": final,
        "table": table,
        "excellent_vs_wait": {
            "diff": (mean(exc) - mean(wait)) if exc and wait else None,
            "ci": diff_ci,
            "excludes_zero": bool(diff_ci and (diff_ci[0] > 0 or diff_ci[1] < 0)),
            "n_excellent": len(exc),
            "n_wait": len(wait),
        },
        "records": records,
    }


def render_markdown(res: dict) -> str:
    L = []
    L.append("# Go Now backtest\n")
    L.append(
        "_Generated by `python -m app.services.go_now_backtest`. Do not edit by hand._\n"
    )
    L.append(
        f"Fuel: **{res['fuel'].upper()}** · data: {res['first']:%Y-%m-%d} → {res['last']:%Y-%m-%d} "
        f"({res['n_cycles']:,} collection cycles) · decisions with usable features and outcome: "
        f"**{res['n_records']:,}** (hourly, Berlin time).\n"
        if res["first"]
        else "No data.\n"
    )
    if not res["n_records"]:
        return "\n".join(L)
    L.append(
        f"Split in time: first half ({res['n_train']:,} decisions) is used for tuning, the second half "
        f"({res['n_test']:,} decisions, from {res['test_from']:%Y-%m-%d}) for ALL reported results.\n"
    )
    L.append("## How to read this\n")
    L.append(
        "- **Saving** = (a) mean best price over the next 6 h − best price now, or (b) minimum best price over the next 12 h − "
        "best price now, in cents per litre. **Positive = going now saved money** (waiting would have cost more). "
        "Saving (b) compares with the cheapest possible moment to wait for, so it is usually negative (the 'regret' of not waiting). "
        "Cycles with missing future data are skipped, never filled.\n"
        "- Sign convention: the task text defined saving as 'now − future' but also said 'positive = saved by going now', which "
        "contradict each other; the economically correct 'future − now' is used.\n"
        "- **Better than waiting** = share of decisions with saving (a) ≥ 0.\n"
        "- **Score (separation)** = mean saving (a) of *excellent/good* minus mean saving (a) of *wait/avoid*, in cents. "
        "A useful indicator has a clearly positive separation.\n"
        f"- Dev data note: the development database is not continuous; the numbers show what the data supports, not production behaviour.\n"
    )

    L.append("## Variants, out of sample\n")
    L.append("| Variant | Parameters | Score first half (¢) | Score second half (¢) |")
    L.append("|---|---|---:|---:|")
    for name, (ptxt, sc) in res["variants"].items():
        L.append(f"| {name} | {ptxt} | {_c(sc['train'])} | **{_c(sc['test'])}** |")
    if res["tuned"]:
        L.append(
            f"| tuned on first half ({res['tested']} combinations) | {_params_text(res['tuned'])} | "
            f"{_c(res['tuned_train'])} | **{_c(res['tuned_test'])}** |"
        )
    L.append("")
    verdict = (
        f"**Adopted:** the tuned values beat the current ones out of sample by at least "
        f"{cfg.GO_NOW_MIN_OOS_IMPROVEMENT_CENTS} ¢ → `{_params_text(res['final'])}`."
        if res["adopt"]
        else f"**Not adopted:** the tuned values do not beat the current ones out of sample by "
        f"{cfg.GO_NOW_MIN_OOS_IMPROVEMENT_CENTS} ¢, so the existing behaviour is kept → `{_params_text(res['final'])}`."
    )
    L.append(verdict + "\n")

    L.append(
        f"## Realised savings per label (second half, parameters: {_params_text(res['final'])})\n"
    )
    L.append(
        "| Label | Decisions | Mean saving a (¢) | Median a (¢) | 95% CI of mean a | Better than waiting | Mean saving b (¢) | 95% CI of mean b |"
    )
    L.append("|---|---:|---:|---:|---|---:|---:|---|")
    for label in ALL_LABELS:
        t = res["table"][label]
        share = "–" if t["share_better"] is None else f"{t['share_better'] * 100:.0f}%"
        L.append(
            f"| {label} | {t['n']} | {_c(t['mean_a'])} | {_c(t['median_a'])} | {_ci(t['ci_a'])} | {share} | "
            f"{_c(t['mean_b'])} | {_ci(t['ci_b'])} |"
        )
    ev = res["excellent_vs_wait"]
    L.append("")
    if ev["diff"] is None:
        L.append(
            "**Excellent vs. wait:** not enough decisions in one of the two labels to compare.\n"
        )
    else:
        L.append(
            f"**Excellent vs. wait:** mean saving difference {_c(ev['diff'])} ¢ (95% CI {_ci(ev['ci'])}, "
            f"n = {ev['n_excellent']} vs {ev['n_wait']}). "
            + (
                "The interval **excludes 0**."
                if ev["excludes_zero"]
                else "The interval **includes 0**, so the data does not show that 'excellent' beats 'wait'."
            )
            + "\n"
        )
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fuel", default="e5", choices=["e5", "e10", "diesel"])
    ap.add_argument("--since-days", type=int, default=None)
    ap.add_argument("--out", default=None, help="write the markdown report here")
    ap.add_argument(
        "--write-params",
        action="store_true",
        help="write app/go_now_params.json if tuned values are adopted",
    )
    args = ap.parse_args(argv)

    res = run(args.fuel, args.since_days)
    md = render_markdown(res)
    if args.out:
        Path(args.out).write_text(md)
        print(f"report written to {args.out}")
    else:
        print(md)
    if args.write_params and res["adopt"]:
        p = res["final"]
        payload = {
            "cheap_pct": p.cheap_pct,
            "expensive_pct": p.expensive_pct,
            "trend_threshold_c_per_h": p.trend_threshold,
            "trend_method": p.trend_method,
            "jump_aware": p.jump_aware,
        }
        Path(cfg._TUNED_FILE).write_text(json.dumps(payload, indent=2) + "\n")
        print(f"adopted tuned parameters written to {cfg._TUNED_FILE}")
    return res


if __name__ == "__main__":
    main()
