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
