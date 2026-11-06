# How FuelTracker's Models Work

This document explains the three analytical features of FuelTracker: the **Outlook** page, the **Go Now indicator** and the **Literboard**. It describes what the code does today, so every number and threshold here can be found in the source (file references are given in each section).

All three are deliberately simple, transparent statistics that run on a small home server. None of them is a black box, and none of them claims more than the data supports.

## Contents

1. [Shared concepts](#1-shared-concepts)
2. [Outlook](#2-outlook)
   - [2.1 Price trend model](#21-price-trend-model-next-17-days)
   - [2.2 Best time to refuel (weekday and hour pattern)](#22-best-time-to-refuel-weekday--hour-pattern)
   - [2.3 Market context (Brent oil and news)](#23-market-context-brent-oil-and-news)
3. [Go Now indicator](#3-go-now-indicator)
4. [Literboard](#4-literboard)
5. [Known limitations](#5-known-limitations)

---

## 1. Shared concepts

**Data.** A collector fetches every station in the configured radius from Tankerkönig every 15 minutes and stores one row per station per fuel type in `fuel_prices`. Brent crude (via Yahoo Finance, converted to EUR) and energy news (RSS) are collected hourly.

**Time zone.** Everything that depends on the clock (hour of day, weekday, "today") is computed in **Europe/Berlin** time, not UTC.

**The noon price jump.** In this data prices fall through the morning to a low around 11:00 and then jump by roughly 10 to 14 cents at 12:00. This is the single strongest pattern in the data (far stronger than any weekday effect), and several design decisions below exist to handle it correctly.

**Missing data is never filled in.** If a period has no observations it stays empty: charts show gaps, and models skip days that do not have enough coverage. The development database is not continuous, so most features check how much data they have and say so when it is not enough.

**Backtesting, not trust.** Where a model makes a forecast (the Outlook trend model), it must prove itself on past data it has not seen before it is shown, and it is compared against the simplest possible alternative.

---

## 2. Outlook

Code: [`backend/app/routers/insights.py`](../backend/app/routers/insights.py), [`backend/app/services/forecast_model.py`](../backend/app/services/forecast_model.py), UI in [`frontend/src/components/Outlook.svelte`](../frontend/src/components/Outlook.svelte) and `TrendChart.svelte`.

The Outlook page combines three separate things that answer different questions:

| Section | Question it answers | Endpoint |
|---|---|---|
| Price trend model | Will the average price be higher or lower in the next days? | `GET /api/insights/trend` |
| Best time to refuel | Which hour and weekday are usually cheapest? | `GET /api/insights/forecast` |
| Market context | What are Brent oil and the news doing? | `GET /api/insights/market` |

Results are cached in memory for 5 minutes (30 minutes for the trend model).

### 2.1 Price trend model (next 1 to 7 days)

**What it predicts.** The *change* of the daily area-average price, compared with the latest complete day, for 1, 2, 3, 5 and 7 days ahead.

```
y = price[t + h] - price[t]        (in cents per litre)
```

**The daily price level.** One number per day: the average over all stations and all hours of that day, with two safeguards:

1. Only hours with reasonable coverage count (at least 40% of the typical number of rows per hour).
2. A day is only used if at least **18 of 24 hours** are covered.
3. Because of the noon jump, a plain average would swing by about a cent depending on *which* hours happen to be missing. So each hourly price is first corrected by the typical hour-of-day shape (learned from nearly complete days with 22+ hours) before averaging.

**Features** (all known at the end of day *t*, no look-ahead):

| Feature | Meaning |
|---|---|
| `weekday` | The weekday of the target day (6 dummy variables) |
| `mom_short` | Today's price vs. the average of the previous 3 days (momentum) |
| `mom_week` | Average of the last 3 days vs. 7 to 9 days ago (weekly drift) |
| `reversion` | Today vs. the 28-day average (mean reversion; needs 10+ days) |
| `oil_mom` | Brent in EUR/L: last 3 days vs. 7 to 9 days ago |
| `oil_rel` | Brent: last 3 days vs. its 28-day average |
| `news_3d` | Keyword-scored supply-risk news over the last 3 days (log-scaled) |

**Candidate models.** Ridge regression (a linear model with a penalty that stops it from overfitting small datasets), standardised inputs, penalty λ = 3. Five variants are tried for each horizon:

| Variant | Inputs |
|---|---|
| `weekday` | weekday only |
| `momentum` | momentum, weekly drift, mean reversion |
| `price` | the above plus weekday |
| `momentum_oil` | momentum features plus Brent |
| `momentum_oil_news` | momentum features plus Brent plus news |

Variants that need Brent or news are only usable on days where those inputs exist. Nothing is imputed.

**Validation (the important part).** Each variant is tested with an *expanding-window walk-forward backtest*:

1. For every past day, train only on samples whose target day had already happened by then (no peeking).
2. Predict that day's outcome and record the error.
3. Compare with the **baseline: "the price stays the same"** (predicted change = 0).

To avoid fooling ourselves, the backtest folds are split in half **in time**:

- the **first half** is used to *choose* the best variant (it must beat the baseline by at least 3%);
- the **second half** is used to *report* how good it is. That half played no part in the choice.

A variant needs at least 24 backtest folds and 25 training samples to be considered at all (the model is refitted every 4 folds to keep this fast).

**Outcome.**

- If a variant wins and is also better than the baseline on the reporting half, it is used. The page shows the expected price, the expected change and an 80% range (±1.28 × the model's out-of-sample error).
- Otherwise the **baseline is shown**: expected change 0, the verdict "No significant change expected", and the 80% range is the baseline's typical error. The band then describes normal noise, not a predicted move.

**Reliability badge on the page.**

| Badge | When |
|---|---|
| High | the model beats the baseline by 20% or more (out-of-sample) |
| Medium | 8% to 20% |
| Low | under 8%, or no model beats the baseline |

**Direction label.** *Rising* or *falling* only if the expected change is at least 0.3 cents and at least half the model's typical error; otherwise *flat*.

**Refusals.** The model returns "not enough data" if the latest complete day is more than 3 days old, or fewer than about 35 usable days exist.

**What the model found on the development data.** With about 200 usable days, no variant beat the baseline: day-to-day moves are about ±1.2 cents of noise, and the weekday effect is below 0.5 cents. The page therefore says "no clear change". The model switches itself on when a real signal exists. This machinery is covered by tests in `backend/tests/test_forecast_model.py`: an oil-led synthetic series is detected, a pure random walk does not produce a fake model, and features never use future data.

### 2.2 Best time to refuel (weekday and hour pattern)

**What it shows.** The cheapest and priciest hour, how big the difference is, and how each of the next 7 days compares with the weekly average.

**Method.**

1. Average price per Berlin-local hour across all stations, using up to **365 days** of history.
2. Same day-level correction as above (days need 18+ covered hours).
3. **Weekday effect** = a day's level minus the average of the surrounding 7 days (centred window, at least 5 days present). Subtracting the local weekly baseline removes slow price-level moves (for example oil-driven ones), so only the weekday pattern remains.
4. **Hour effect** = an hour's price minus that day's average, per weekday.
5. Both are averaged with **recency weighting**: a day's weight halves every 120 days, so the last weeks count most. The standard error uses the effective sample size.

**Labels.** A weekday is called *cheaper* or *pricier* than usual only if its offset is larger than max(0.3 cents, its standard error); otherwise *about average*. Every weekday needs at least 3 samples (roughly 3 weeks of data) before anything is shown.

**For today** the page picks the cheapest hour *remaining* from now, since earlier hours are gone.

**Pattern confidence** is *low* below 5 samples per weekday, *medium* below 9, otherwise *high*.

**Honest framing.** The summary shows both spreads side by side (about 13 cents between the best and worst hour, but under 0.5 cents between the best and worst weekday), so users learn that *the hour matters far more than the day*.

### 2.3 Market context (Brent oil and news)

This is context, not a forecast. It feeds the "Why this prediction?" section.

- **Brent and pump price, 7 days:** percentage change of the latest daily level against about 7 days earlier. Shown only when both ends exist; otherwise "Not enough data".
- **Oil to pump relationship:** the correlation between day-over-day *changes* in the pump price and Brent's changes, with Brent leading by 0 to 10 days. Changes are used, not levels, because two trending series correlate spuriously. It needs at least 20 paired days; |r| ≥ 0.3 counts as meaningful, otherwise "weak".
- **Oil signal:** rising/falling if Brent moved more than ±2% over 7 days. Only when the relationship is meaningful *and* positive does the page mention upward or downward pressure.
- **News:** articles from the last 72 hours are scored by a keyword list (for example OPEC, Hormuz, sanctions, refinery outage, each with a weight). Only articles scoring 2 or more are shown, the top 5. Stories unrelated to oil supply (such as electricity statistics) score 0 and are ignored. This is keyword matching, not language understanding.

---

## 3. Go Now indicator

Code: `get_go_now_indicator` in [`backend/app/routers/prices.py`](../backend/app/routers/prices.py), UI in `GoNowIndicator.svelte`. Endpoint: `GET /api/prices/analytics/go-now`.

**Question.** Is the best price right now cheap compared with what is normal at this time of day, and is it going up or down?

It is **not** a forecast of future prices. It ranks the present against the recent past.

**Step 1: the current best price.** Each station's *latest* price row is taken. A station only counts if its latest row is **at most 30 minutes old** and the station is open. The lowest of those is the "current best price". The station name and the age of the price are returned, so the recommendation can never point to a price that is no longer offered.

**Step 2: same-hour percentile.** The past 7 days are reduced to one number per hour: the lowest price across all stations in that hour. The current price is then ranked against the values from the *same time of day* (current hour ±1 hour, Berlin time). This matters because of the noon jump: a 7:00 price must be compared with other early-morning prices, not with cheap evening prices.

```
percentile = (number of hourly lows <= current price) / (number of hourly lows) x 100
```

A low percentile means cheap. The page shows "Cheaper than (100 − percentile)% of prices at this time of day".

Data requirements: at least 6 same-hour data points. If fewer exist, it falls back to all hours of the week, which needs at least 12 points; below that the result is "insufficient data".

**Step 3: short-term trend.** A straight line (least squares) is fitted through the hourly lows of the **last 3 hours**. Its slope in cents per hour is *falling* below −0.1, *rising* above +0.1, otherwise *stable*. At least two hourly values are needed.

**Step 4: the recommendation.**

| Percentile | Falling | Stable | Rising |
|---|---|---|---|
| ≤ 35 (cheap) | **excellent** | good | good (grab it before it rises) |
| 36 to 65 (middle) | neutral | neutral | wait |
| > 65 (expensive) | wait | wait | **avoid** |

The week low, median and high shown on the card are taken from the same set of hourly lows used for the percentile.

**Limits.** It uses the lowest price across all stations, so it answers "is there a good price somewhere near me?", not "is *my* usual station cheap?". With a 3-hour window the trend is noisy, which is why it only nudges between the labels above.

---

## 4. Literboard

Code: `get_top_stations` in [`backend/app/routers/prices.py`](../backend/app/routers/prices.py), UI in `Statistics.svelte` (leaderboard mode). Endpoint: `GET /api/prices/analytics/top-stations`. It lives on the Statistics page below the heatmap.

**Ranking.** Stations are ranked by their **average price over the selected period** (the period chosen at the top of the page), cheapest first. The top 10 are shown, each with its average, minimum, maximum and range for that period.

**"Cheapest X% of the time".** For every hour in the period, each station's lowest price in that hour is ranked against all other stations. The station with the lowest value is "cheapest" for that hour (ties all count). The percentage is the number of hours a station was cheapest divided by the number of hours with any data. This is a real count, not an estimate.

**Stability** (always measured over a fixed 30-day window, so a station's label does not change just because the user picks a different period).

An earlier version used the raw standard deviation of all prices. That labelled every station "very volatile", because all stations share the daily noon jump and any longer-term price level change. The current method asks a more useful question: *how big are this station's daily price swings compared with other stations?*

1. For each station and each local day, take the **daily range** = highest minus lowest price that day. Only days with at least 48 observations (about 12 hours of 15-minute data) count.
2. Average these daily ranges (the "daily swing", shown in cents). A station needs at least 7 qualifying days.
3. Divide by the **median** daily swing of all stations to get a ratio.

| Ratio vs. typical station | Label |
|---|---|
| up to 0.75 | Very stable |
| up to 0.92 | Stable |
| up to 1.08 | Typical |
| up to 1.25 | Volatile |
| above 1.25 | Very volatile |

The label is relative by design: "Typical" means "about as swingy as the median station". A station with fewer than 7 qualifying days shows "Not enough data". The bar under each station is the ratio, where 50% of the bar equals the typical station.

---

## 5. Known limitations

- **Single-area average.** The Outlook trend and weekday pattern describe the *average over all tracked stations*, not an individual station.
- **Short oil and news history.** Brent is collected hourly, but on the development database only a few weeks exist. Until about 20 to 60 overlapping days are available, oil inputs cannot be validated and are not used. Production data should improve this automatically.
- **Keyword news scoring** can include irrelevant articles that happen to mention a keyword, and miss relevant ones that do not.
- **Prices are stored every 15 minutes even when unchanged,** so counts per station reflect collection frequency, not the number of real price changes. The statistics are built to avoid depending on this (hourly buckets, daily ranges), but exact timing of price changes is not known.
- **Not advice.** Everything here is a statistical description of past data. The Outlook page, the Go Now indicator and the Literboard help with decisions; they do not guarantee any future price.

## Where to improve next

1. Run on production data. The trend model re-tests itself automatically and will start using a variant as soon as one proves better than the baseline.
2. Store Brent from more than one source and at finer resolution, with a consensus value.
3. Store news with timestamps and a per-article relevance label instead of keyword weights.
4. Store a price only when it changes, together with a "last confirmed" time.
5. Only then consider a heavier model, and accept it only if it beats the current ridge model in the same backtest.
