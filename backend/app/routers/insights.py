"""Outlook endpoints: weekday/hour forecast and oil/news market context.

Everything here is derived from stored observations only. Nothing is
interpolated; when there is not enough data the endpoints say so instead of
guessing. These are statistical *patterns*, not price guarantees.
"""

import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from cache import cached, refresh
from database import SessionLocal
from database import get_db
from limiter import limiter
from services.forecast_model import build_trend_forecast
from models import EnergyNews, FuelPrice, MarketPrice, OilPrice

router = APIRouter()

TZ_NAME = "Europe/Berlin"
TZ = ZoneInfo(TZ_NAME)
WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

FUEL_COLUMNS = {"e5": FuelPrice.e5, "e10": FuelPrice.e10, "diesel": FuelPrice.diesel}

LOOKBACK_DAYS = 365  # use up to a year of history
HALF_LIFE_DAYS = 120  # a day's weight halves every 120 days (recent weeks count more)
MIN_HOURS_PER_DAY = 18  # a day needs this many well-covered hours to be used
MIN_SAMPLES_PER_WEEKDAY = 3  # ~3 weeks of data before we show a pattern
CACHE_SECONDS = 300


def _mean(xs):
    return sum(xs) / len(xs)


def _std(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = _mean(xs), _mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def _wstats(pairs):
    """Recency-weighted mean and standard error of [(age_days, value), ...]."""
    ws = [0.5 ** (age / HALF_LIFE_DAYS) for age, _ in pairs]
    total = sum(ws)
    m = sum(w * v for w, (_, v) in zip(ws, pairs)) / total
    var = sum(w * (v - m) ** 2 for w, (_, v) in zip(ws, pairs)) / total
    n_eff = total**2 / sum(w * w for w in ws)
    se = math.sqrt(var / max(1.0, n_eff - 1)) if n_eff > 1 else 0.0
    return m, se


def _hourly_series(db: Session, column, since: datetime):
    """Average price per Berlin-local hour (plus the number of rows behind it)."""
    local_hour = func.date_trunc("hour", func.timezone(TZ_NAME, FuelPrice.timestamp))
    rows = (
        db.query(local_hour.label("h"), func.avg(column), func.count())
        .filter(FuelPrice.timestamp >= since, column.isnot(None))
        .group_by(local_hour)
        .order_by(local_hour)
        .all()
    )
    return [(r[0], float(r[1]), int(r[2])) for r in rows]


def _build_daily(hourly):
    """Group well-covered hours by local date. Returns {date: {hour: price}}."""
    if not hourly:
        return {}
    counts = sorted(n for _, _, n in hourly)
    median_n = counts[len(counts) // 2]
    min_n = max(3, median_n * 0.4)  # drop hours with clearly partial coverage
    days = defaultdict(dict)
    for h, price, n in hourly:
        if n >= min_n:
            days[h.date()][h.hour] = price
    return {d: hrs for d, hrs in days.items() if len(hrs) >= MIN_HOURS_PER_DAY}


def _daily_levels(days: dict) -> dict:
    """Daily price level that is robust to missing hours.

    Prices jump ~10 cents around noon, so a plain average over whichever hours
    happen to be present swings by about a cent depending on which hours are
    missing. We learn the typical hour-of-day shape from (nearly) complete days
    and average the shape-corrected hourly prices instead.
    """
    complete = [h for h in days.values() if len(h) >= 22]
    if not complete:
        return {d: _mean(list(h.values())) for d, h in days.items()}
    shape_samples = defaultdict(list)
    for hrs in complete:
        m = _mean(list(hrs.values()))
        for hour, price in hrs.items():
            shape_samples[hour].append(price - m)
    shape = {hour: _mean(v) for hour, v in shape_samples.items()}
    return {
        d: _mean([price - shape.get(hour, 0.0) for hour, price in hrs.items()])
        for d, hrs in days.items()
    }


def _compute_forecast(db: Session, fuel_type: str):
    column = FUEL_COLUMNS[fuel_type]
    now = datetime.now(timezone.utc)
    hourly = _hourly_series(db, column, now - timedelta(days=LOOKBACK_DAYS))
    days = _build_daily(hourly)
    today = now.astimezone(TZ).date()

    result = {
        "fuel_type": fuel_type,
        "insufficient_data": True,
        "days_used": len(days),
        "first_day": min(days).isoformat() if days else None,
        "last_day": max(days).isoformat() if days else None,
        "min_samples_per_weekday": MIN_SAMPLES_PER_WEEKDAY,
        "confidence": None,
        "forecast": [],
        "recent_trend_cents_per_day": None,
        "disclaimer": (
            "Based on repeating weekday/hour patterns in past prices. "
            "This is not a price guarantee."
        ),
    }
    if not days:
        return result

    daily_mean = _daily_levels(days)

    # Day-of-week effect = daily mean minus the local weekly baseline, which
    # removes slow level changes (e.g. oil-driven moves) from the weekday signal.
    dow_dev = defaultdict(list)
    for d, m in daily_mean.items():
        window = [
            daily_mean[d + timedelta(days=k)]
            for k in range(-3, 4)
            if (d + timedelta(days=k)) in daily_mean
        ]
        if len(window) >= 5:
            dow_dev[d.weekday()].append(((today - d).days, m - _mean(window)))

    # Hour-of-day effect per weekday: hourly price minus that day's mean.
    hour_dev = defaultdict(lambda: defaultdict(list))
    for d, hrs in days.items():
        dm = daily_mean[d]
        for hour, price in hrs.items():
            hour_dev[d.weekday()][hour].append(((today - d).days, price - dm))

    if any(len(dow_dev[w]) < MIN_SAMPLES_PER_WEEKDAY for w in range(7)):
        result["samples_per_weekday"] = [len(dow_dev[w]) for w in range(7)]
        return result

    # Recent direction: slope of the last 7 usable daily means (needs >= 5).
    recent = sorted(d for d in daily_mean if (today - d).days <= 10)[-7:]
    if len(recent) >= 5:
        xs = [(d - recent[0]).days for d in recent]
        ys = [daily_mean[d] for d in recent]
        mx, my = _mean(xs), _mean(ys)
        denom = sum((x - mx) ** 2 for x in xs)
        if denom > 0:
            slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
            result["recent_trend_cents_per_day"] = round(slope * 100, 2)

    min_samples = min(len(dow_dev[w]) for w in range(7))
    result["samples_per_weekday"] = [len(dow_dev[w]) for w in range(7)]
    result["confidence"] = (
        "low" if min_samples < 5 else "medium" if min_samples < 9 else "high"
    )

    forecast = []
    for i in range(7):
        d = today + timedelta(days=i)
        w = d.weekday()
        devs = dow_dev[w]
        mean_dev, se_dev = _wstats(devs)
        offset = mean_dev * 100  # cents vs. weekly average
        se = se_dev * 100
        hours = {
            h: _wstats(v)[0]
            for h, v in hour_dev[w].items()
            if len(v) >= MIN_SAMPLES_PER_WEEKDAY
        }
        best_hour = min(hours, key=hours.get) if hours else None
        worst_hour = max(hours, key=hours.get) if hours else None
        forecast.append(
            {
                "date": d.isoformat(),
                "weekday": WEEKDAYS[w],
                "offset_cents": round(offset, 2),
                "uncertainty_cents": round(se, 2),
                "samples": len(devs),
                # Typical cents vs. the day's mean for every hour with enough samples
                # (lets the UI pick the best *remaining* hour for today).
                "hour_offsets_cents": {
                    str(h): round(v * 100, 2) for h, v in sorted(hours.items())
                },
                "best_hour": best_hour,
                "worst_hour": worst_hour,
                "hour_spread_cents": (
                    round((hours[worst_hour] - hours[best_hour]) * 100, 2)
                    if hours
                    else None
                ),
            }
        )

    # Rank + label. A day only counts as cheaper/pricier when its offset is
    # clearly larger than the noise in our estimate.
    order = sorted(range(7), key=lambda i: forecast[i]["offset_cents"])
    for rank, i in enumerate(order, start=1):
        f = forecast[i]
        f["rank"] = rank
        margin = max(0.3, f["uncertainty_cents"])
        f["label"] = (
            "cheaper"
            if f["offset_cents"] < -margin
            else "pricier" if f["offset_cents"] > margin else "average"
        )

    result["insufficient_data"] = False
    result["forecast"] = forecast
    # How much does each dimension matter? (lets the UI say "pick the hour, not the day")
    result["weekday_spread_cents"] = round(
        max(f["offset_cents"] for f in forecast)
        - min(f["offset_cents"] for f in forecast),
        2,
    )
    spreads = [
        f["hour_spread_cents"] for f in forecast if f["hour_spread_cents"] is not None
    ]
    result["hour_spread_cents"] = round(_mean(spreads), 2) if spreads else None
    return result


@router.get("/forecast")
@limiter.limit("30/minute")
def get_forecast(
    request: Request,
    fuel_type: str = Query("e5", pattern="^(e5|e10|diesel)$"),
    db: Session = Depends(get_db),
):
    """Weekday/hour price pattern for the coming 7 days (Europe/Berlin time).

    Uses up to a year of history, with recent weeks weighted more.
    """
    return cached(
        ("forecast", fuel_type), CACHE_SECONDS, lambda: _compute_forecast(db, fuel_type)
    )


# --- Market context: oil + news -------------------------------------------

# keyword -> weight. Matched on word boundaries in title + summary.
NEWS_KEYWORDS = {
    "opec": 3,
    "opec+": 3,
    "production cut": 3,
    "output cut": 3,
    "supply disruption": 3,
    "strait of hormuz": 3,
    "hormuz": 3,
    "red sea": 2,
    "sanction": 2,
    "sanctions": 2,
    "embargo": 2,
    "refinery outage": 3,
    "refinery": 1,
    "pipeline": 1,
    "tanker": 1,
    "crude": 1,
    "brent": 2,
    "oil price": 2,
    "oil prices": 2,
    "inventory": 1,
    "stockpile": 1,
    "russia": 1,
    "iran": 1,
    "saudi": 1,
    "libya": 1,
    "ceasefire": 1,
    "attack": 1,
    "outage": 2,
    "shutdown": 1,
    "hurricane": 1,
}
_KEYWORD_RES = [
    (kw, w, re.compile(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", re.I))
    for kw, w in NEWS_KEYWORDS.items()
]


def _score_article(title: str, summary: str | None):
    text = f"{title} {summary or ''}"
    matched, score = [], 0
    for kw, w, rx in _KEYWORD_RES:
        if rx.search(text):
            matched.append(kw)
            score += w
    return score, matched


def _daily_oil(db: Session, since: datetime):
    day = func.date(func.timezone(TZ_NAME, OilPrice.timestamp))
    rows = (
        db.query(day, func.avg(OilPrice.price_eur_per_liter), func.count())
        .filter(OilPrice.timestamp >= since)
        .group_by(day)
        .all()
    )
    return {r[0]: float(r[1]) for r in rows if r[2] >= 3}


def _compute_market(db: Session, fuel_type: str):
    column = FUEL_COLUMNS[fuel_type]
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=LOOKBACK_DAYS)
    today = now.astimezone(TZ).date()

    fuel_daily = _daily_levels(_build_daily(_hourly_series(db, column, since)))
    oil_daily = _daily_oil(db, since)

    # Lag relationship on day-over-day *changes* (levels would correlate
    # spuriously through shared trends). Oil leads fuel by `lag` days.
    def change(series, d):
        prev = d - timedelta(days=1)
        return series[d] - series[prev] if d in series and prev in series else None

    lag_stats = []
    for lag in range(0, 11):
        xs, ys = [], []
        for d in fuel_daily:
            fc = change(fuel_daily, d)
            oc = change(oil_daily, d - timedelta(days=lag))
            if fc is not None and oc is not None:
                xs.append(oc)
                ys.append(fc)
        r = _pearson(xs, ys)
        if r is not None:
            lag_stats.append(
                {"lag_days": lag, "correlation": round(r, 3), "pairs": len(xs)}
            )

    usable = [s for s in lag_stats if s["pairs"] >= 20]
    best = max(usable, key=lambda s: abs(s["correlation"])) if usable else None
    reliable = bool(best and abs(best["correlation"]) >= 0.3)

    def level_change(series, days=7):
        """Latest vs. ~`days` earlier using the nearest available daily means."""
        if not series:
            return None
        latest_d = max(series)
        if (today - latest_d).days > 3:
            return None
        for k in range(days - 1, days + 2):
            ref = latest_d - timedelta(days=k)
            if ref in series:
                old = series[ref]
                return {
                    "from": ref.isoformat(),
                    "to": latest_d.isoformat(),
                    "change": series[latest_d] - old,
                    "change_pct": (series[latest_d] / old - 1) * 100 if old else None,
                }
        return None

    oil_chg = level_change(oil_daily)
    fuel_chg = level_change(fuel_daily)

    oil_signal = None
    if oil_chg and oil_chg["change_pct"] is not None:
        pct = oil_chg["change_pct"]
        oil_signal = "rising" if pct > 2 else "falling" if pct < -2 else "flat"

    outlook = "no_clear_signal"
    if reliable and oil_signal in ("rising", "falling") and best["correlation"] > 0:
        outlook = "upward_pressure" if oil_signal == "rising" else "downward_pressure"

    # News: last 72h, keyword-scored; unrelated energy stories score 0 and are dropped.
    articles = (
        db.query(EnergyNews)
        .filter(EnergyNews.published_at >= now - timedelta(hours=72))
        .order_by(EnergyNews.published_at.desc())
        .limit(300)
        .all()
    )
    scored = []
    for a in articles:
        score, matched = _score_article(a.title, a.summary)
        if score >= 2:
            scored.append((score, a, matched))
    scored.sort(key=lambda t: (t[0], t[1].published_at), reverse=True)

    return {
        "fuel_type": fuel_type,
        "oil_days": len(oil_daily),
        "fuel_days": len(fuel_daily),
        "oil_7d": oil_chg,
        "fuel_7d": fuel_chg,
        "oil_signal": oil_signal,
        "lag_relationship": {
            "reliable": reliable,
            "best": best,
            "note": (
                "Based on day-over-day changes. A weak correlation means oil moves "
                "did not reliably precede pump-price moves in the data we have."
            ),
        },
        "outlook": outlook,
        "news": [
            {
                "title": a.title,
                "source": a.source,
                "link": a.link,
                "published_at": a.published_at,
                "score": score,
                "keywords": matched,
            }
            for score, a, matched in scored[:5]
        ],
        "news_candidates_72h": len(articles),
        "disclaimer": "Context only: correlation is not causation and this is not a price prediction.",
    }


@router.get("/market")
@limiter.limit("30/minute")
def get_market_context(
    request: Request,
    fuel_type: str = Query("e5", pattern="^(e5|e10|diesel)$"),
    db: Session = Depends(get_db),
):
    """Brent trend, oil→pump lag relationship and keyword-relevant news."""
    return cached(
        ("market", fuel_type), CACHE_SECONDS, lambda: _compute_market(db, fuel_type)
    )


# --- Trend model ---------------------------------------------------------------

TREND_LOOKBACK_DAYS = 730
TREND_CACHE_SECONDS = 1800


def _daily_news_scores(db: Session, since: datetime) -> dict:
    """Keyword-weighted news pressure per local day (days without articles are absent)."""
    rows = (
        db.query(EnergyNews.published_at, EnergyNews.title, EnergyNews.summary)
        .filter(EnergyNews.published_at >= since)
        .all()
    )
    out: dict = {}
    for published_at, title, summary in rows:
        day = published_at.astimezone(TZ).date()
        score, _ = _score_article(title, summary)
        out[day] = out.get(day, 0) + score
    return out


def _daily_market(db: Session, since: datetime) -> dict:
    """Daily mean of each market series (gasoil proxy, RBOB, EUR/USD, Brent USD) per Berlin day."""
    day = func.date(func.timezone(TZ_NAME, MarketPrice.timestamp))
    out: dict = defaultdict(dict)
    for series, d, value in (
        db.query(MarketPrice.series, day, func.avg(MarketPrice.value))
        .filter(MarketPrice.timestamp >= since)
        .group_by(MarketPrice.series, day)
        .all()
    ):
        out[series][d] = float(value)
    return dict(out)


def _compute_trend(db: Session, fuel_type: str):
    column = FUEL_COLUMNS[fuel_type]
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=TREND_LOOKBACK_DAYS)
    days = _build_daily(_hourly_series(db, column, since))
    price = _daily_levels(days)
    oil = _daily_oil(db, since)
    news = _daily_news_scores(db, since)
    market = _daily_market(db, since)
    result = build_trend_forecast(
        price,
        oil,
        news,
        now.astimezone(TZ).date(),
        market=market,
        hourly_days=days,
    )
    result["fuel_type"] = fuel_type
    # The exact daily series the model uses, for charting (last 60 days; gaps stay gaps).
    result["history"] = [
        {"date": d.isoformat(), "price": round(price[d], 4)}
        for d in sorted(price)
        if (now.astimezone(TZ).date() - d).days <= 60
    ]
    result["disclaimer"] = (
        "Statistical estimate of the area-average price, validated on past data. "
        "Not a guarantee and not financial advice."
    )
    return result


@router.get("/trend")
@limiter.limit("20/minute")
def get_trend_forecast(
    request: Request,
    fuel_type: str = Query("e5", pattern="^(e5|e10|diesel)$"),
    db: Session = Depends(get_db),
):
    """Day-ahead price trend (1-7 days) from a backtested ridge model."""
    return cached(
        ("trend", fuel_type), TREND_CACHE_SECONDS, lambda: _compute_trend(db, fuel_type)
    )


def warm_trend_cache() -> None:
    """Scheduled job: recompute the trend results so requests never wait ~10 s."""
    for fuel_type in FUEL_COLUMNS:
        db = SessionLocal()
        try:
            refresh(
                ("trend", fuel_type),
                TREND_CACHE_SECONDS,
                lambda: _compute_trend(db, fuel_type),
            )
        except Exception as exc:  # never let a failed warm-up break the scheduler
            print(f"[trend warm-up] {fuel_type}: {type(exc).__name__}")
        finally:
            db.close()
