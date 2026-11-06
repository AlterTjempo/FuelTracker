"""Every tunable threshold of the analytical models lives here.

Each value says where it comes from:
  default   = hand-picked starting value, not tuned on data
  backtest  = chosen/validated by one of the backtest scripts in app/services
              (see docs/go-now-backtest.md, docs/trend-backtest.md)

Go Now parameters can be overridden by app/go_now_params.json, which is only
written by `python -m app.services.go_now_backtest --write-params` when the
tuned values beat the current ones OUT OF SAMPLE.
"""

import json
from pathlib import Path

_TUNED_FILE = Path(__file__).with_name("go_now_params.json")


def _load_tuned() -> dict:
    try:
        return json.loads(_TUNED_FILE.read_text())
    except (OSError, ValueError):
        return {}


_tuned = _load_tuned()

# ---------------------------------------------------------------- Go Now ----
GO_NOW_FRESH_MINUTES = 30  # default: a price older than this is not "current"
GO_NOW_HISTORY_DAYS = 7  # default: window for the same-hour percentile
GO_NOW_MIN_SAME_HOUR_POINTS = 6  # default: below this, fall back to all hours
GO_NOW_MIN_ALL_HOUR_POINTS = 12  # default: below this, "insufficient data"
GO_NOW_CHEAP_PCT = _tuned.get("cheap_pct", 35)  # default (see go-now-backtest.md)
GO_NOW_EXPENSIVE_PCT = _tuned.get(
    "expensive_pct", 65
)  # default (see go-now-backtest.md)
GO_NOW_TREND_THRESHOLD_C_PER_H = _tuned.get("trend_threshold_c_per_h", 0.1)  # default
GO_NOW_TREND_METHOD = _tuned.get(
    "trend_method", "legacy"
)  # "legacy" | "robust"; default legacy
GO_NOW_JUMP_AWARE = _tuned.get(
    "jump_aware", False
)  # default off until it wins out of sample
GO_NOW_LEGACY_TREND_HOURS = 3  # default: legacy least-squares window
GO_NOW_ROBUST_TREND_HOURS = 6  # default: Theil-Sen window (hours of hourly lows)
GO_NOW_ROBUST_MIN_POINTS = 4  # default: points needed for the robust slope
GO_NOW_SHAPE_DAYS = 28  # default: history used to learn the hour-of-day shape
GO_NOW_SHAPE_MIN_DAYS = 5  # default: days with 20+ hours needed for a shape
GO_NOW_SHAPE_MIN_HOURS = 20  # default: hours a day needs to count for the shape
GO_NOW_MIN_JUMP_CENTS = 1.0  # default: smaller steps are not called "a jump"
GO_NOW_PRE_JUMP_MIN_H = 1.0  # default: "roughly 1 to 2 hours before the jump"
GO_NOW_PRE_JUMP_MAX_H = 2.0  # default

# Backtest (outcome definition and quality gates)
BACKTEST_FUTURE_MEAN_HOURS = 6  # default: outcome (a) window
BACKTEST_FUTURE_MIN_HOURS = 12  # default: outcome (b) window
BACKTEST_MIN_FUTURE_COVERAGE = 0.7  # default: share of expected cycles that must exist
BACKTEST_CYCLE_MINUTES = 15  # fixed by the collector
BACKTEST_BOOTSTRAP_N = 1000  # default
BACKTEST_MIN_GROUP = 30  # default: min decisions per group when scoring
GO_NOW_MIN_OOS_IMPROVEMENT_CENTS = (
    0.1  # default: tuned values must beat current by this
)

# Grid searched on the first half of the data (values are candidates, not defaults)
GO_NOW_GRID_CHEAP = (25, 30, 35, 40, 45)
GO_NOW_GRID_EXPENSIVE = (55, 60, 65, 70, 75)
GO_NOW_GRID_TREND = (0.05, 0.1, 0.2, 0.3, 0.5)

# Location filter
GO_NOW_MAX_DISTANCE_KM_LIMIT = 100  # default: upper bound accepted by the API

# ------------------------------------------------------------ Market data ----
# Free sources only. ICE gasoil and Eurobob/ARA are not available on Yahoo
# Finance (checked: G=F, LGO=F, EBOB.L, ICE.L return "not found"), so the closest
# free benchmarks are used:
#   gasoil_proxy = HO=F   NY Harbor ULSD futures (the standard diesel/gasoil benchmark)
#   rbob         = RB=F   RBOB gasoline futures (closest free proxy for Eurobob)
#   eurusd       = EURUSD=X
#   brent_usd    = BZ=F   Brent in USD/barrel (long history; oil_prices has only EUR/L since collection began)
MARKET_SERIES = {
    "gasoil_proxy": "HO=F",
    "rbob": "RB=F",
    "eurusd": "EURUSD=X",
    "brent_usd": "BZ=F",
}
MARKET_BACKFILL_RANGE = "2y"  # default: one daily close per day is back-filled once
MARKET_LAGS = (
    1,
    2,
    3,
    5,
    10,
)  # default: lags (days) of 2-day-mean changes, 1 to 10 as requested

# ------------------------------------------------------------ Trend model ----
TREND_HORIZONS = (1, 2, 3, 5, 7)  # default: days ahead
TREND_MIN_TRAIN = 25  # default: samples before a walk-forward fold is trusted
TREND_MIN_TEST_FOLDS = 24  # default: folds needed to validate a variant
TREND_MIN_SKILL = 0.03  # default: must beat persistence by 3% MAE on the selection half
TREND_MAX_DM_P = (
    0.1  # requested: Diebold-Mariano p-value must be below this (selection half)
)
TREND_RIDGE_LAMBDA = 3.0  # default: ridge penalty (small feature sets)
TREND_RIDGE_LAMBDA_MARKET = (
    20.0  # default: stronger penalty when ~20 market lag features are used
)
TREND_REFIT_EVERY = 4  # default: walk-forward refit stride (ridge)
TREND_REFIT_EVERY_QUANTILE = (
    12  # default: quantile regression is ~50x slower, refit less often
)
TREND_MAX_TRAIN = 400  # default: most recent samples used for fitting
TREND_MAX_ORIGIN_AGE_DAYS = 3  # default: latest complete day may be at most this old
TREND_MIN_USABLE_DAYS = 35  # default: TREND_MIN_TRAIN + 10
TREND_BAND = (0.1, 0.9)  # requested: 80% band = 10% and 90% error quantiles
TREND_COVERAGE_TOLERANCE = (
    0.08  # default: |coverage - 0.8| above this is flagged as miscalibrated
)
QUANTILE_IRLS_ITERATIONS = 12  # default: IRLS steps for quantile regression
QUANTILE_IRLS_DELTA = 0.05  # default: smoothing of |residual| (cents)
DIRECTION_MIN_MOVE_CENTS = (
    0.05  # default: |change| below this is not counted as a direction
)

# Reliability badge (based on out-of-sample metrics of the horizon)
RELIABILITY_HIGH_SKILL = 0.15  # default
RELIABILITY_HIGH_DM_P = 0.05  # default
RELIABILITY_MEDIUM_SKILL = 0.05  # default
RELIABILITY_MEDIUM_DM_P = 0.15  # default

# Probability of a rise
PROB_RISE_CENTS = 1.0  # requested default (configurable): rise larger than this counts
PROB_HORIZON_DAYS = (1, 2)  # requested: 24 h and 48 h
PROB_LAMBDA = 3.0  # default: L2 penalty of the logistic regression
PROB_MIN_BSS = (
    0.03  # default: Brier skill vs. base rate required (selection and evaluation)
)
PROB_MAX_ECE = 0.12  # default: expected calibration error allowed
PROB_HIGH_BSS = 0.15  # default: "High" reliability needs this Brier skill
PROB_HIGH_ECE = 0.07  # default: ... and this calibration error

# Hourly forecast
HOURLY_MIN_HOURS = 20  # default: hours a day needs to be used
HOURLY_SHAPE_DAYS = 28  # default: history for the hour-of-day shape
HOURLY_SHAPE_HALF_LIFE_DAYS = 14  # default: recency weighting of the shape
HOURLY_MIN_SHAPE_DAYS = 7  # default: days needed to estimate the shape
