# FuelTracker – Project Model & Development Guide

## 1. Project Overview

FuelTracker is a fuel price tracking and analysis platform focused on Germany.

The primary goal is to collect fuel prices from German filling stations, store historical price data, and provide users with insights into fuel price movements.

The project goes beyond simply displaying current fuel prices. It aims to become an energy and market intelligence platform that combines:

- Historical fuel price data.
- Live and historical Brent crude oil prices.
- Geopolitical and energy-related news.
- Fuel price statistics and trends.
- Price predictions and market insights.
- Personalized user features.

The original inspiration for the project was the **Pentagon Pizza Index**. The idea is to collect real-world data and use it to identify patterns, trends, and potentially meaningful events.

FuelTracker should maintain this identity: a data-driven platform that helps users understand not only fuel prices, but also why those prices change.

## 2. Technology Stack

The currently known technology stack:

| Component | Technology |
|---|---|
| Frontend | Svelte 4 + Vite SPA (served by nginx) |
| Backend | FastAPI (Python), APScheduler in-process |
| Database | PostgreSQL |
| Development environment | Local development server |
| Production environment | Self-hosted infrastructure |
| Fuel price source | Tankerkönig API |
| Oil price source | Brent crude oil price API |
| News source | Energy and oil-related RSS feeds |

The repository has been inspected: see `backend/app` (routers, services) and `frontend/src`. Note that this is NOT SvelteKit.

**Important:** The repository must be indexed and analyzed before making assumptions about existing implementations.

Do not invent file paths, functions, database tables, or API endpoints.

## 3. Data Architecture

FuelTracker is fundamentally a data collection and analysis project.

The intended logical architecture is:

```text
External Data Sources
        |
        v
  Data Collection
        |
        v
  Data Validation
        |
        v
    PostgreSQL
        |
        v
  Analysis & Processing
        |
        v
    SvelteKit
        |
        v
      Users
```

### 3.1 Fuel Price Data

Fuel prices are collected from Tankerkönig.

The project focuses on German filling stations and stores historical price observations.

The collected data enables:

- Historical price charts.
- Station comparisons.
- Cheapest and most expensive stations.
- Price percentile calculations.
- Time-of-day analysis.
- Price trend detection.
- Simple price predictions.

Tankerkönig API usage is subject to its usage policies. Avoid unnecessarily frequent requests and do not attempt to circumvent API restrictions.

The API has previously experienced temporary availability problems. Error handling must distinguish between invalid API credentials, server errors, network failures, and other API responses.

### 3.2 Brent Crude Oil Data

FuelTracker also collects Brent crude oil prices.

The purpose is to provide broader context for fuel price movements.

Important concepts:

- Brent crude oil is quoted in USD per barrel.
- One barrel equals approximately 159 litres.
- FuelTracker should use metric units for its own presentation.
- Oil prices should be collected periodically (currently intended: once per hour).

Oil prices and pump prices should not be treated as directly equivalent.

Changes in crude oil prices influence fuel prices through refining costs, distribution, taxes, exchange rates, and other factors.

The relationship also has a time delay.

### 3.3 Multiple Oil Price Sources

Different providers can report different Brent prices.

This can happen because of:

- Different update intervals.
- Different market data providers.
- Different quote types.
- Delayed versus real-time data.
- Different timestamps.

A future improvement is to compare multiple sources before storing an aggregated price.

Potential approach:

1. Collect raw observations from each provider.
2. Normalize timestamps, currencies, and units.
3. Validate the observations.
4. Detect outliers.
5. Calculate a consensus value, for example using the median.
6. Store the aggregated result together with its source count and confidence information.

Never assume that three different values are directly comparable without checking what each provider actually reports.

### 3.4 Geopolitical and Energy News

FuelTracker collects news from energy-related RSS feeds.

Examples of relevant subjects:

- Oil production.
- Oil supply disruptions.
- Middle Eastern conflicts.
- OPEC and OPEC+ decisions.
- Sanctions.
- Shipping disruptions.
- Refinery outages.
- Energy market developments.

News articles are stored in the database for historical analysis and potential future AI applications.

The intention is to connect important events to changes in Brent crude oil and fuel prices.

Not every energy-related article is relevant to crude oil prices. For example, electricity generation statistics should not automatically be interpreted as an explanation for rising oil prices.

## 4. Current Features

The following features are already implemented or have been reported as implemented.

### 4.1 Fuel Price Dashboard

- Display current fuel prices.
- Display nearby German filling stations.
- Historical fuel price information.
- Price timelines.
- Overview of fuel price statistics.

### 4.2 Go Now Indicator

The Go Now indicator helps users decide whether it is a good moment to refuel.

The original implementation compared the current price against a 24-hour average.

This was improved to use percentile-based price analysis.

The intended logic also considers:

- Time-of-day bias.
- Historical price distributions.
- Short-term price trends.
- Whether prices are rising or falling.

The indicator should provide useful guidance rather than pretend to predict exact future prices.

A known issue remains: the indicator can sometimes recommend a price that is no longer available at the station.

The recommendation must always be based on valid, current station data.

### 4.3 Statistics

A dedicated statistics page contains fuel price statistics.

Previously implemented statistics include:

- All-time lowest price.
- Lowest price within the last 72 hours.
- Average price.
- Highest price within the last 72 hours.
- Price range and percentage spread.
- Cheapest day of the week.
- Cheapest hour of the day.

Additional statistics can be added as the historical dataset grows.

### 4.4 Station Detail Pages

Individual filling stations have their own detail pages.

These pages should provide more detailed information about individual stations and their historical price movements.

### 4.5 Heatmap

A heatmap is available for visualizing price patterns.

The visual design should avoid making ordinary price differences look unnecessarily alarming.

Color choices should communicate relative differences without suggesting that every higher price is a critical situation.

### 4.6 Oil Price Tracker

A dedicated Brent crude oil tracker is implemented.

It displays oil price information and historical development.

### 4.7 Geopolitics Tracker

An RSS-based news section is implemented.

It collects energy-related news and displays relevant articles.

The longer-term goal is to connect news events with oil price movements.

### 4.8 Simple Prediction Algorithm

**Not implemented.** No prediction code exists in the repository (verified by audit).

A calendar-style presentation was considered for showing predictions.

The advanced geopolitical prediction system is still planned.

### 4.9 User System

User functionality is implemented or in progress.

The intended account system includes:

- Username.
- Email address.
- Password hash.
- Admin status.
- Account creation timestamp.

The existing database has previously contained a user table with the following fields:

```sql
id
username
hashed_password
is_admin
created_at
email
```

An existing password hash uses the bcrypt format.

The project also has a favorites table:

```sql
id
user_id
station_id
added_at
```

Users should be able to:

- Register an account.
- Log in.
- Add filling stations to their favorites.
- Remove favorite stations.
- View their personalized information.

Registration requirements:

- Username.
- Email.
- Password.
- CAPTCHA verification.
- Password strength validation.

Password validation should provide immediate feedback while the user is typing.

The backend must independently validate password requirements. Frontend validation alone is not sufficient.

Passwords must never be stored in plaintext.

Authenticated users should receive an additional navigation tab.

The navigation should also be fixed so that users cannot accidentally scroll through the tabs horizontally.

## 5. Development Environment and Database

**Important distinction between development and production data:**

The AI agent operates in the development environment.

The development database contains data, but it is NOT populated with a continuous production-like dataset.

This means:

- Historical data may be incomplete.
- There may be gaps in timestamps.
- Some periods may contain no observations.
- Oil price history may be limited.
- RSS article history may be incomplete.
- Statistics may differ significantly from production.
- Predictions may be unreliable when tested against development data.

Do not assume that missing records represent periods with no price changes.

Do not assume that development data is representative of the real-world market.

When implementing or testing statistical algorithms:

1. Inspect the available date range.
2. Check observation frequency.
3. Identify missing periods.
4. Check for duplicate observations.
5. Verify whether timestamps are consistent.
6. Handle insufficient data gracefully.

Never fabricate historical observations to make a chart or prediction look complete.

If an algorithm requires more data than is available, it should communicate that limitation.

## 6. Current TODO List

The following list represents the current project roadmap.

### 6.1 Bugs

- [x] Everything above the 7-day timeline was previously broken.
- [x] Mobile compatibility.
- [x] Fix the Go Now indicator recommending a price that is no longer available (uses latest row per open station, max 30 min old).

### 6.2 Improvements

- [x] Base the Go Now indicator on percentiles.
- [x] Security review.
- [ ] UI cleanup while maintaining the existing visual identity.

### 6.3 New Features

- [x] User accounts (in progress).
- [x] Brent crude oil price tracker.
- [x] Individual station detail pages.
- [x] Geopolitics tracker using RSS feeds.
- [x] Simple prediction algorithm based on historical fuel price data (weekday/hour pattern, `GET /api/insights/forecast`, Outlook tab). Implemented Nov 2026; earlier versions of this list marked it done before it existed.
- [ ] Advanced prediction system based on geopolitical and energy-related data (first step: `GET /api/insights/market` shows oil trend, oil→pump lag correlation and keyword-scored news; no price forecast from it yet).
- [x] Personal savings tracker (`/api/savings`, Savings tab; reference = area average ±1h of the refuel).
- [x] Smoothing toggle for charts (client-side moving average, gap-aware).
- [x] Zooming into a specific time period (drag-select; ≤3 days loads 15-minute data).

### 6.4 Planned Feature Details

#### Advanced Prediction System

The long-term goal is to combine multiple data sources:

- Historical fuel prices.
- Brent crude oil prices.
- Oil price trends.
- Geopolitical events.
- Energy-related news.

The system should identify potential relationships between events and price movements.

It should provide contextual market insights rather than claim certainty about future prices.

#### Personal Savings Tracker

A personalized dashboard showing how much money users have saved by choosing cheaper filling stations or better refueling moments.

Example:

```text
Your Fuel Statistics

34 refueling sessions
1,200 litres purchased
€147 saved
```

The savings calculation should use a clearly defined reference price.

For example, the difference between the actual purchase price and a defined average or alternative station price.

Do not claim that a user saved money without a defensible calculation.

#### Chart Smoothing

Add a toggle that allows users to switch between:

- Raw price observations.
- A smoothed price line.

The original data must remain available.

Smoothing should be a visualization feature, not a modification of stored historical observations.

#### Chart Zooming

Allow users to inspect specific periods in greater detail.

Potential functionality:

- Select a date range.
- Zoom into a particular period.
- Inspect individual price observations.
- Return to the full timeline.

## 7. Design Philosophy

FuelTracker should maintain a consistent visual identity.

The platform should feel like a modern data dashboard rather than a generic administration panel.

Important design principles:

- Clean and modern interface.
- Data-focused presentation.
- Consistent typography and spacing.
- Responsive layout.
- Good mobile compatibility.
- Clear charts and visualizations.
- Avoid unnecessary visual complexity.
- Use color meaningfully.
- Avoid excessive red and orange, especially in statistical visualizations.

The existing design is already considered visually appealing.

UI improvements should refine the existing style rather than replace it entirely.

## 8. Development Guidelines for AI Agents

When working on FuelTracker, follow these guidelines.

### 8.1 Inspect Before Changing

Before implementing new functionality:

- Index the repository.
- Inspect the existing directory structure.
- Identify the SvelteKit architecture.
- Inspect existing database schemas and migrations.
- Identify API routes and backend services.
- Understand existing components and styling conventions.
- Identify how scheduled data collection works.

Do not create duplicate implementations when an existing solution can be extended.

### 8.2 Database Integrity

PostgreSQL is the central data store.

Database changes should be:

- Properly structured.
- Consistent with existing naming conventions.
- Migration-friendly.
- Safe for existing production data.

Do not delete or overwrite existing historical data unless explicitly requested.

### 8.3 API Reliability

External APIs can fail.

Implement appropriate handling for:

- HTTP errors.
- Timeouts.
- Invalid responses.
- Missing data.
- Rate limits.
- Authentication errors.
- Temporary upstream outages.

Do not interpret every API failure as an invalid API key.

Distinguish between temporary infrastructure problems and permanent authentication failures.

### 8.4 Statistical Accuracy

FuelTracker relies heavily on historical data.

Statistical calculations must be transparent and reproducible.

Pay particular attention to:

- Time zones.
- Missing observations.
- Outliers.
- Sample sizes.
- Percentile calculations.
- Different observation frequencies.
- Delayed market data.

Avoid presenting predictions or statistical conclusions with more certainty than the data supports.

### 8.5 Security

User functionality must follow basic security practices:

- Secure password hashing.
- Server-side input validation.
- Secure session handling.
- CSRF protection where applicable.
- CAPTCHA verification.
- Rate limiting.
- Authorization checks.
- Protection against SQL injection.
- Never expose secrets or API keys to the frontend.

### 8.6 Keep Implementations Lightweight

FuelTracker runs on self-hosted infrastructure.

Avoid unnecessarily heavy dependencies, services, and machine learning models.

Prefer simple statistical approaches and efficient database queries where possible.

Any future AI or prediction functionality should be suitable for a relatively small home server.

## 8b. Trend Model (implemented Nov 2026)

`backend/app/services/forecast_model.py` (pure Python, no ML dependencies, tests in `backend/tests/`),
served by `GET /api/insights/trend`, shown in the Outlook tab.

- Predicts the change of the daily area-average price 1/2/3/5/7 days ahead.
- Features: weekday, price momentum, weekly drift, distance from the 28-day mean, Brent trend, keyword-scored news pressure.
- Several candidate models (ridge regression) are compared with an expanding-window walk-forward backtest against the baseline "price stays the same". The model is selected on the first half of the backtest and its skill is reported on the second half. If nothing beats the baseline, the API returns the baseline and says so.
- Daily price levels are corrected for missing hours (the noon price jump of ~10 cents would otherwise bias days with gaps).
- Finding on the dev data (207 usable days): no candidate beats the baseline; day-to-day noise is ~1.2 cents. The weekday effect is <0.5 cents, the time-of-day effect ~13 cents (cheapest around 11:00, jump at 12:00). The weekday/hour calendar (`/api/insights/forecast`) uses up to a year of history with a 120-day half-life.
- The machinery is verified on synthetic data (it finds an oil-led signal, does not invent one in a random walk, never uses future data).

Roadmap towards a richer model (in order of expected value):
1. More history of its own: prod data (the model re-evaluates itself; no code change needed).
2. Store Brent from more than one source and at higher resolution (currently ~hourly, but dev has only 21 usable days).
3. Store news with timestamps and a per-article relevance label (today: keyword weights).
4. Store a price only when it changes plus a `last_confirmed_at`, so intraday timing is exact.
5. Only then consider gradient boosting / a small neural net, and only if it beats the ridge model in the same backtest.

> **Update (Nov 2026):** the trend model, Go Now, best-time and Literboard were extended and backtested.
> The current behaviour, thresholds and evidence are described in [prediction-models.md](prediction-models.md);
> the section below is the original 8b summary.

## 8c. Savings references, Literboard stability (Nov 2026)

- Savings can be compared against the tracked-station area average (default), the Dutch national average (CBS open data table 80416ENG, fetched by `services/nl_collector.py` into `nl_fuel_prices`, Euro95 used for E5/E10) or a manual reference price.
- Literboard stability = a station's average daily price swing over 30 days relative to the median station (very stable ≤0.75×, stable ≤0.92×, typical ≤1.08×, volatile ≤1.25×, else very volatile; needs 7 qualifying days). The old raw standard deviation labelled every station "very volatile" because of the shared midday price jump.
- The Literboard now lives on the Statistics tab below the heatmap.

## 9. Long-Term Vision

FuelTracker should evolve from a simple fuel price tracker into a small energy intelligence platform.

The long-term concept is:

```text
Fuel Prices
     +
Oil Markets
     +
Geopolitical Events
     +
Historical Data
     |
     v
Market Analysis
     |
     v
Insights & Predictions
     |
     v
Better Refueling Decisions
```

The platform should eventually be able to answer questions such as:

- Are fuel prices currently unusually high?
- Is Brent crude oil becoming more expensive?
- Are geopolitical events creating supply risks?
- Are fuel prices likely to rise or fall?
- Is it better to refuel now or wait?
- Which stations offer the best prices?
- How much money has a user saved over time?

The ultimate goal is not to build a large or complicated AI model.

It is to collect useful data, understand relationships between different markets, and present meaningful insights in an accessible way.

**FuelTracker: Understand fuel prices, follow the market, and make smarter refueling decisions.**