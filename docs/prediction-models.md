# How FuelTracker's Models Work

This document explains the analytical features of FuelTracker: the **Outlook** page, the **Go Now indicator** and the **Literboard**. It describes what the code does today, so every number and threshold can be found in the source. All tunable values live in one module, [`backend/app/analytics_config.py`](../backend/app/analytics_config.py), and each says whether it is a default or came from a backtest.

All of it is deliberately simple, transparent statistics that runs on a small home server. Nothing is a black box, and nothing claims more than the data supports.

Generated evidence (re-run the scripts to refresh it):

| Report | Script | Content |
|---|---|---|
| [go-now-backtest.md](go-now-backtest.md) | `python -m app.services.go_now_backtest` | realised savings per Go Now label, tuning |
| [trend-backtest.md](trend-backtest.md) | `python -m app.services.trend_backtest` | every trend variant, probability model, hourly forecast |
| (printed) | `python -m app.services.literboard_check` | which stability window is most repeatable |

Inside the backend container use `python -m services.<name>` (the app directory is the working directory there).

## Contents

1. [Shared concepts](#1-shared-concepts)
2. [Outlook](#2-outlook)
3. [Go Now indicator](#3-go-now-indicator)
4. [Literboard](#4-literboard)
5. [Configuration, tables and migrations](#5-configuration-tables-and-migrations)
6. [Known limitations](#6-known-limitations)
7. [Where to improve next](#7-where-to-improve-next)

---

## 1. Shared concepts

**Data.** A collector fetches every station in the configured radius from Tankerkönig every 15 minutes ([`data_collector.py`](../backend/app/services/data_collector.py)). Hourly collectors fetch Brent in EUR ([`oil_collector.py`](../backend/app/services/oil_collector.py)), energy news ([`news_collector.py`](../backend/app/services/news_collector.py)) and the market series described in [2.1](#21-inputs): gasoil proxy, RBOB, EUR/USD, Brent in USD ([`market_collector.py`](../backend/app/services/market_collector.py)).

**Time zone.** Everything that depends on the clock (hour of day, weekday, "today") is Europe/Berlin time.

**The noon price jump.** Prices fall through the morning to a low around 11:00 and then jump by roughly 10 to 15 cents at 12:00. This is by far the strongest pattern in the data, and several design decisions exist to handle it correctly.

**Missing data is never filled in.** A gap stays a gap: charts show gaps, days without enough coverage are skipped, outcomes in the backtests are only computed when the future window really exists.

**No look-ahead, honest validation.** Every model that forecasts is trained walk-forward (a sample is only used once its target has happened). The first half of the backtest *selects* a model and calibrates its band; everything reported is measured on the second half. Every forecast must beat a naive baseline before it is shown. Statistics helpers (bootstrap, Theil-Sen, Diebold-Mariano, pinball loss, Brier score, reliability table) are in [`stats_utils.py`](../backend/app/services/stats_utils.py).

**Calendar features were deliberately left out** (public holidays, school holidays, bridge days, month-end, tax or CO2 changes). They would add inputs and UI clutter, and the data do not show a weekday effect worth modelling (see 2.2).

---

## 2. Outlook

Code: [`routers/insights.py`](../backend/app/routers/insights.py), [`services/forecast_model.py`](../backend/app/services/forecast_model.py), [`services/brand_pattern.py`](../backend/app/services/brand_pattern.py); UI in `Outlook.svelte` and `TrendChart.svelte`.

| Section | Question | Endpoint |
|---|---|---|
| Price trend | Will the average price be higher or lower in the next days? | `GET /api/insights/trend` |
| Best time to refuel | Which hour is cheapest? | `GET /api/insights/forecast` |
| Market context | What are Brent and the news doing? | `GET /api/insights/market` |

Caches: forecast and market 5 minutes, trend 30 minutes (re-computed by a scheduled job every 20 minutes, because one computation takes about 10 seconds), brand patterns 1 hour.

### 2.1 Price trend model

**The daily price level.** One number per day: the average over all stations and hours, using only hours with reasonable coverage (at least 40% of the typical rows per hour) on days with at least 18 of 24 hours. A plain average would swing by about a cent depending on which hours happen to be missing (because of the noon jump), so each hourly price is first corrected by the typical hour-of-day shape learned from nearly complete days (22+ hours) (`_daily_levels`).

**Three targets** (all from the same features):

| Target | Model | Where it shows |
|---|---|---|
| Change of the daily level, 1, 2, 3, 5, 7 days ahead, in cents (`price[t+h] − price[t]`) | ridge or median quantile regression, whichever wins the backtest, otherwise the baseline | trend card and chart |
| Probability that the level rises by more than **1 cent** (`PROB_RISE_CENTS`) within 24 h and 48 h | L2-regularised logistic regression | one line in the trend card, **only if validated** |
| Hourly price shape of the next day | latest day level + recency-weighted hour-of-day shape | API only (`hourly`) |

#### Inputs

All are known at the end of day *t*; variants that need an input only run where the data exist (nothing imputed).

| Feature | Meaning |
|---|---|
| weekday | weekday of the target day (6 dummies) |
| `mom_short`, `mom_week`, `reversion` | momentum (today vs. previous 3 days), weekly drift (last 3 days vs. 7 to 9 days ago), distance from the 28-day average |
| `oil_mom`, `oil_rel` | Brent in EUR/L: trend and distance from its 28-day average |
| `news_3d` | keyword-scored supply-risk news over the last 3 days |
| `<series>_L<lag>` | **new:** lagged *changes* (not levels) of gasoil, RBOB, EUR/USD and Brent in USD. Lags 1, 2, 3, 5, 10 days (`MARKET_LAGS`). Each is the change of the 3-day mean ending *lag* days ago vs. the 3-day mean before it. 3-day windows always contain a trading day, so weekends do not create false gaps. |

**Market sources.** ICE gasoil and Eurobob/ARA are not available for free on Yahoo Finance (checked: `G=F`, `LGO=F`, `EBOB.L`, `ICE.L` all return "not found"). The closest free benchmarks are used and stored in `market_prices`: `HO=F` (NY Harbor ULSD, the standard diesel/gasoil benchmark, used as **gasoil proxy**), `RB=F` (RBOB gasoline, the closest free proxy for Eurobob), `EURUSD=X` and `BZ=F` (Brent in USD, because it has a long history). A one-time backfill of two years of daily closes (stored at noon UTC of the trading date) lets the features be validated on more than a few weeks; afterwards the hourly collector adds real timestamps.

#### Candidate models

| Variant | Inputs | Learner |
|---|---|---|
| `weekday` | weekday | ridge |
| `momentum` | momentum, drift, reversion | ridge |
| `price` | the above + weekday | ridge |
| `momentum_oil`, `momentum_oil_news` | + Brent, + news | ridge |
| `momentum_market` | momentum + all market lags (20 features, penalty 20 instead of 3) | ridge |
| `qr_momentum`, `qr_market` | as above | **median quantile regression** (smoothed IRLS, L2 penalty), more robust to outliers |

The ridge model stays the default; a quantile variant only runs if it wins the same backtest.

#### Evaluation (every variant, every horizon)

Reported by [`trend_backtest.py`](../backend/app/services/trend_backtest.py), second half only:

- **MAE vs. the "no change" baseline** and the resulting *skill* (1 − MAE/MAE_baseline);
- **directional accuracy** (vs. the share of the majority direction);
- **pinball loss** of the 10% and 90% quantiles (vs. the baseline's);
- **Diebold-Mariano test** against the baseline (one-sided, Newey-West variance with *h−1* lags, Harvey small-sample correction);
- **coverage of the 80% band**.

**Selection rule:** a variant must beat the baseline by at least 3% MAE (`TREND_MIN_SKILL`) **and** have a Diebold-Mariano p-value below 0.1 (`TREND_MAX_DM_P`) on the selection half. The best of those by selection-half skill is used, and only if it also beats the baseline on the evaluation half.

**The 80% band** is the 10% and 90% quantile of the model's own errors on the selection half (not ±1.28σ, which assumes normal errors). Its coverage is then measured on the evaluation half, shown as `coverage80` and flagged when it is more than 8 points from 80%. On the dev data the old ±1.28σ band covered 85% to 97% at 1 to 3 days (too wide) and 70% to 78% at 7 days (too narrow). The empirical band lands between 71% and 87% for most variants and horizons; the report marks values outside 72% to 88% with a warning (E5 at 7 days is only 61%, so its band is too narrow).

**Fallback.** If no variant qualifies, the baseline is returned (expected change 0, verdict "No significant change expected"). The band is then the baseline's typical error, not a predicted move.

**Reliability badge** (per horizon, from out-of-sample metrics, `reliability_level`):

| Badge | When |
|---|---|
| High | beats baseline, skill ≥ 15%, Diebold-Mariano p < 0.05 **and** the 80% band is calibrated |
| Medium | skill ≥ 5% and Diebold-Mariano p < 0.15 |
| Low | otherwise, or no model beats the baseline |

**Probability of a rise.** Same features, same walk-forward discipline (`probability_forecast`). Candidates `momentum` and `momentum_market`. Compared with the **base rate** (the share of rises in the training data):

- **Brier score** and Brier skill vs. the base rate, Diebold-Mariano on the squared errors;
- **reliability table** (predicted vs. observed frequency in 5 bins) and the **expected calibration error** (ECE).

A variant is selected if Brier skill ≥ 3% and Diebold-Mariano p < 0.1 on the selection half; it is *validated* (and shown) if Brier skill ≥ 3% on the evaluation half and ECE ≤ 0.12. Reliability: High needs Brier skill ≥ 15% and ECE ≤ 0.07, otherwise Medium. If it is not validated, **nothing is shown**.

**Hourly forecast.** Day level (latest day with the shape removed) plus a recency-weighted hour-of-day shape (28 days, half-life 14 days); the variant `weekend_split` uses separate shapes for weekends. Baselines: *same hour yesterday* and *same hour, same weekday last week*. Validated only if the MAE is below both and the Diebold-Mariano p-value against the better baseline is below 0.1.

**Refusals.** "Not enough data" if the latest complete day is more than 3 days old or fewer than 35 usable days exist.

**What the dev data show** (details in [trend-backtest.md](trend-backtest.md)): with about 200 usable days no variant beats the baseline for E5 or diesel, the probability model is not validated and the hourly model is close to but not significantly better than "same hour yesterday" (E5: 1.57 vs. 1.63 cents, p = 0.15). The page therefore says "no clear change". The machinery is covered by tests on synthetic data (a learnable momentum signal is found and calibrated, an oil-led series is found, a random walk gives no fake model, features never look ahead).

### 2.2 Best time to refuel

Endpoint `GET /api/insights/forecast`; backend `_compute_forecast`.

**The hour pattern is the headline.** For every Berlin hour, the recency-weighted (half-life 120 days, up to a year of history) average deviation of that hour from its day's mean, pooled over all weekdays (`hour_pattern`: cheapest hour, priciest hour, spread, profile). For *today*, the cheapest hour **from now on** is picked from the same profile.

**Weekdays are secondary.** A weekday's offset is its daily level minus the average of the surrounding 7 days (centred window, at least 5 days present). It is called cheaper/pricier only if it clears its standard error **and** 0.3 cents (`WEEKDAY_MIN_OFFSET_CENTS`). The UI shows weekdays only in a collapsed section "Weekday differences", and only if at least one weekday is significant (`significant_weekdays`). On the dev data none is (the weekday spread is about 0.5 cents against about 13 cents for the hour).

**Brands** ([`brand_pattern.py`](../backend/app/services/brand_pattern.py)). Stations are grouped by brand (brands with fewer than 3 stations go to "Other", `BRAND_MIN_STATIONS`), the hour shape is learned per group over the last 120 days and the noon-type jump is located. If groups differ by less than 1 cent in jump size and less than 1 hour in timing, the single area-wide pattern is kept; otherwise per-brand patterns are reported (`brand_patterns`). **Finding on the dev data:** the timing is identical (12:00 for every brand), but the *size* differs by up to 7 cents (about 9 cents at Kuster Energy, about 16 at Shell). The cheapest and priciest hour are therefore the same for everyone; what differs is how much timing matters, and the UI shows this range in the "typical difference" tile.

**Confidence** is *low* below 5 samples per weekday, *medium* below 9, otherwise *high* (in `_compute_forecast`); the text under the tiles says how many days the hour pattern is based on.

### 2.3 Market context (Brent and news)

Context, not a forecast; it feeds "Why this prediction?".

- **Brent and pump price, 7 days:** change of the latest daily level against about 7 days earlier, shown only when both ends exist.
- **Oil to pump relationship:** correlation of day-over-day *changes* with Brent leading by 0 to 10 days, at least 20 paired days; |r| ≥ 0.3 counts as meaningful.
- **Oil signal:** rising/falling if Brent moved more than ±2% over 7 days. Pressure is only mentioned when the relationship is meaningful and positive.
- **News:** articles of the last 72 hours scored by a keyword list; only articles with score ≥ 2 are shown (top 5). This is keyword matching, not language understanding.

---

## 3. Go Now indicator

Code: [`services/go_now.py`](../backend/app/services/go_now.py) (pure decision logic, used by the endpoint **and** the backtest), `get_go_now_indicator` in [`routers/prices.py`](../backend/app/routers/prices.py), [`services/go_now_backtest.py`](../backend/app/services/go_now_backtest.py); UI in `GoNowIndicator.svelte`. Endpoint: `GET /api/prices/analytics/go-now`.

**Question.** Is the best price right now cheap compared with what is normal at this time of day, and is it going up or down? It is not a forecast; it ranks the present against the recent past. The backtest checks whether the labels really sort decisions by what going now saved.

**Step 1: current best price.** Each station's *latest* price row counts if it is at most 30 minutes old (`GO_NOW_FRESH_MINUTES`) and the station is open. The lowest is the current best price; the station and the price's age are returned.

**Optional station filter.** `station_id`, or `lat` + `lon` + `max_distance_km` (up to 100 km), restricts both the current price and the history to those stations; the response says which filter was used (`filter`). The UI has one compact select in the card header ("All stations" or "Within 5/10/25 km"); "near me" asks the browser for the location once and does not store it (nginx allows geolocation for the site itself).

**Step 2: same-hour percentile.** The past 7 days are reduced to one value per hour (the lowest price across the considered stations). The current price is ranked against the values from the same time of day (current hour ±1 h). At least 6 same-hour points are needed, otherwise all hours are used (at least 12), otherwise "insufficient data".

**Step 3: trend.** Two methods are implemented ([`trend_slope`](../backend/app/services/go_now.py)); the config selects one (`GO_NOW_TREND_METHOD`): *legacy* (least-squares slope over the hourly lows of the last 3 hours) and *robust* (Theil-Sen slope over the last 6 hours, with the hour-of-day shape removed). The backtest kept **legacy**: the robust slope scored lower out of sample (0.85 vs. 0.91 cents of separation).

**Step 4: jump-aware rule.** The hour of the typical price jump (and its size) is **learned** from the hour-of-day shape of the previous 28 days, not hard-coded to 12:00 (`typical_jump`; needs a jump of at least 1 cent). In the 1 to 2 hours before that jump (`GO_NOW_PRE_JUMP_MIN_H`/`MAX_H`) a *falling* trend is neutralised: it can neither cause "wait" (waiting for a drop that is about to reverse) nor upgrade a cheap price to "excellent". (The task text said it must not trigger "wait or good"; "good" does not depend on a falling trend, so the upgrade to "excellent" is what was neutralised.) The backtest turned this on: it raised the out-of-sample score for the legacy trend (1.01 vs. 0.91).

**Step 5: recommendation** (cut-offs tuned by the backtest, see below):

| Percentile | Falling | Stable | Rising |
|---|---|---|---|
| ≤ 25 (cheap) | **excellent** | good | good |
| 26 to 75 (middle) | neutral | neutral | wait |
| > 75 (expensive) | wait | wait | **avoid** |

Trend threshold ±0.2 cents per hour (`GO_NOW_TREND_THRESHOLD_C_PER_H`).

### The backtest and what it showed

[`go_now_backtest.py`](../backend/app/services/go_now_backtest.py) reproduces the decision for every hour with enough data using only data available then, and measures the outcome: *saving (a)* = mean best price over the next 6 h − best price now, *saving (b)* = minimum best price over the next 12 h − best price now. Positive means going now saved money. (The task text's "now minus future" contradicts its own "positive = saved"; the economically correct "future minus now" is used.) Outcomes need at least 70% of the future cycles to exist. Parameters (percentile cut-offs, trend threshold, trend method, jump-aware on/off) were tuned by grid search on the first half of the data and are reported on the second half; they are adopted only if they beat the old values out of sample by 0.1 cent.

Result on the dev data (E5, second half, [full report](go-now-backtest.md)): separation between "go" labels (excellent/good) and "stay" labels (wait/avoid) rose from **0.91 to 1.35 cents** per litre with the tuned values (25/75, ±0.2 c/h, legacy trend, jump-aware). **Excellent beats wait by 1.21 cents (95% CI 0.78 to 1.67, excludes 0).** The tuned values are stored in `go_now_params.json`, which the config module reads.

**Limits.** It uses the lowest price across the considered stations (hence the optional filter). Dev data are not continuous, so production numbers will differ.

---

## 4. Literboard

Code: `get_top_stations` in [`routers/prices.py`](../backend/app/routers/prices.py), [`services/literboard.py`](../backend/app/services/literboard.py); UI in `Statistics.svelte` (leaderboard mode, below the heatmap on the Statistics tab). Endpoint: `GET /api/prices/analytics/top-stations`.

**Ranking.** By average price over the selected period, cheapest first.

**Data volume behind every figure.** Each row carries `hours_with_data`, `days_with_data` and `stability_days`; the UI shows them as small muted text. **Stations with too little data are not ranked** next to well-covered ones: a station needs at least 6 hours of data (or all hours that exist in a shorter window; `LITERBOARD_MIN_HOURS`) and at least 50% of the hours of the best-covered station (`LITERBOARD_MIN_DATA_SHARE`). The others are listed at the end with "Not enough data" (at most 5, `LITERBOARD_MAX_UNRANKED`).

**"Cheapest X% of the time".** For every hour, each station's lowest price is ranked against all others; rank 1 (ties all count) means cheapest. Default: share of all hours with data in the window. With `opening_hours_weighted=true` (a small "by opening hours" toggle in the leaderboard header): share of the hours **the station itself had data**. Price rows are only stored while a station is open (and the open status itself is stored only as its *current* state, not as a history), so "hours with data" is the available measure of "open hours". Stability is already computed over open hours only, so the flag changes this share only.

**Stability** is measured over a fixed window (`LITERBOARD_STABILITY_DAYS`, **30 days**, so the label does not change with the selected period):

1. per station and local day, the **daily range** = highest minus lowest price (days with at least 48 observations only);
2. average of these ranges = the **daily swing** (needs at least 7 qualifying days);
3. divided by the **median** swing of all stations.

| Ratio | Label |
|---|---|
| ≤ 0.75 | Very stable |
| ≤ 0.92 | Stable |
| ≤ 1.08 | Typical |
| ≤ 1.25 | Volatile |
| > 1.25 | Very volatile |

**Why 30 days and not longer.** A longer window was considered. [`literboard_check.py`](../backend/app/services/literboard_check.py) measures how well a station's stability in a window of *W* days predicts its stability in the following 30 days (rank correlation): **30 days 0.75, 60 days 0.72, 90 days 0.69**. Longer windows predict slightly *worse* (older behaviour no longer applies), so 30 days is kept. The value is a config setting.

---

## 5. Configuration, tables and migrations

**Config:** every threshold is in [`analytics_config.py`](../backend/app/analytics_config.py) with a comment saying "default", "requested" or "backtest" (groups: Go Now, backtest gates, market data, trend model, reliability, probability, hourly, best time and brands, Literboard).

**Tables** (created at start-up by `create_all` and `schema_migrations.py`; SQL for manual deployments in [`migrations/`](../migrations/); the project uses plain SQL migrations, not Alembic): `market_prices` (`006`), `nl_fuel_prices` and refuel reference columns (`005`), `refuel_logs` and `password_changed_at` (`004`).

---

## 6. Known limitations

- **Single-area average.** The trend and hour pattern describe the average over all tracked stations; brands differ in the *size* of the noon jump.
- **Short history on the dev database.** About 200 usable days: models cannot show an edge over "no change", the probability model and the hourly model are not validated. Production data should help; the models re-test themselves.
- **Free market proxies.** Gasoil and RBOB futures are US benchmarks used as stand-ins for ICE gasoil and Eurobob. Yahoo Finance is an unofficial source and can change.
- **News scoring is keyword based** and can include irrelevant or miss relevant articles.
- **Prices are stored every 15 minutes even when unchanged.** All statistics use hourly buckets or daily ranges to avoid depending on that, but exact times of price changes are unknown.
- **Opening hours are only known as "hours with data"** (no history of the open flag).
- **The Go Now backtest uses the lowest price across stations**, so it is a statement about "a good price somewhere nearby", not about one station.
- **Not advice.** All numbers describe past data.

## 7. Where to improve next

1. Run on production data: the trend, probability and hourly models re-test themselves and switch on when they win.
2. Paid or official refined-product data (ICE gasoil, Eurobob/ARA) if the free proxies turn out to be the limiting factor.
3. Store a price only when it changes, with a "last confirmed" time, and a history of the open flag.
4. Per-article news relevance labels instead of keyword weights.
5. Only if all of the above is not enough: a heavier model, accepted only if it beats the ridge model in the same backtest.
