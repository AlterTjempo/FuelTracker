from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import asyncio
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from limiter import limiter
from schema_migrations import apply_schema_migrations

from database import engine, Base, SessionLocal
from routers import stations, prices
from routers import oil_prices
from routers import energy_news
from routers import auth, favorites, analytics, admin, insights, savings
from services.data_collector import DataCollector
from services.oil_collector import OilCollector
from services.news_collector import NewsCollector
from services.market_collector import MarketCollector
from services.nl_collector import NlCollector
from config import settings

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables and start scheduler
    if (
        settings.JWT_SECRET_KEY == "overwritten-in-config-env-change-me"
        or len(settings.JWT_SECRET_KEY) < 32
    ):
        print(
            "WARNING: JWT_SECRET_KEY is the default or shorter than 32 characters. Set a long random value in config.env."
        )
    Base.metadata.create_all(bind=engine)
    apply_schema_migrations(engine)

    # Initialize data collectors
    collector = DataCollector()
    oil_collector = OilCollector()
    news_collector = NewsCollector()
    nl_collector = NlCollector()
    market_collector = MarketCollector()

    # Fetch fuel prices every 15 minutes
    scheduler.add_job(
        collector.fetch_and_store_prices, "interval", minutes=15, id="fetch_prices"
    )

    # Fetch Brent crude oil price every hour
    scheduler.add_job(
        oil_collector.fetch_and_store, "interval", hours=1, id="fetch_oil_price"
    )

    # Fetch energy news every hour
    scheduler.add_job(
        news_collector.fetch_and_store, "interval", hours=1, id="fetch_energy_news"
    )

    # Dutch average pump prices (CBS publishes weekly); refresh twice a day
    scheduler.add_job(
        nl_collector.fetch_and_store, "interval", hours=12, id="fetch_nl_prices"
    )

    # Refined products, Brent (USD) and EUR/USD: hourly
    scheduler.add_job(
        market_collector.fetch_and_store, "interval", hours=1, id="fetch_market_prices"
    )

    # Keep the (slow, ~10 s) trend results warm; first run shortly after start-up
    scheduler.add_job(
        insights.warm_trend_cache,
        "interval",
        minutes=20,
        id="warm_trend_cache",
        next_run_time=datetime.now(timezone.utc) + timedelta(minutes=20),
    )

    # Start scheduler
    scheduler.start()

    # Run initial fetches in the background so the API accepts requests
    # immediately instead of refusing connections while collectors run.
    async def initial_fetch():
        for job in (
            collector.fetch_and_store_prices,
            oil_collector.fetch_and_store,
            news_collector.fetch_and_store,
            lambda: nl_collector.fetch_and_store(days=1000),
            market_collector.backfill,
            market_collector.fetch_and_store,
        ):
            try:
                await job()
            except Exception as exc:
                print(f"Initial fetch failed: {type(exc).__name__}")

    async def initial_warmup():
        await initial_fetch()
        # compute the slow trend results once data is in, so the first visitor never waits
        try:
            await asyncio.to_thread(insights.warm_trend_cache)
        except Exception as exc:
            print(f"Initial trend warm-up failed: {type(exc).__name__}")

    initial_task = asyncio.create_task(initial_warmup())

    yield

    # Shutdown: Stop scheduler
    initial_task.cancel()
    scheduler.shutdown()


app = FastAPI(
    title="FuelTracker API",
    description="Track and analyze fuel prices from Tankerkonig",
    version="1.0.0",
    lifespan=lifespan,
    # Don't expose docs in production unless explicitly enabled
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
)

# Expose the scheduler to the admin overview (read-only: job names and next runs)
app.state.scheduler = scheduler

# Attach rate limiter to the app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Compress JSON responses (history/heatmap payloads compress ~10x)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS middleware — restrict origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins,
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "DELETE",
    ],  # Auth, favorites, savings need POST/DELETE
    allow_headers=["*"],
)

# Include routers
app.include_router(stations.router, prefix="/api/stations", tags=["stations"])
app.include_router(prices.router, prefix="/api/prices", tags=["prices"])
app.include_router(oil_prices.router, prefix="/api/oil-prices", tags=["oil-prices"])
app.include_router(energy_news.router, prefix="/api/energy-news", tags=["energy-news"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(favorites.router, prefix="/api/favorites", tags=["favorites"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(insights.router, prefix="/api/insights", tags=["insights"])
app.include_router(savings.router, prefix="/api/savings", tags=["savings"])


# Responses that contain personal data must never be stored by browsers or proxies.
_NO_STORE_PREFIXES = (
    "/api/auth",
    "/api/admin/system",
    "/api/admin/users",
    "/api/admin/traffic",
    "/api/savings",
    "/api/favorites",
)


@app.middleware("http")
async def private_responses_not_cached(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(_NO_STORE_PREFIXES):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
async def root():
    return {"message": "FuelTracker API", "status": "running"}


@app.get("/api/health")
def api_health():
    """Uptime-monitor endpoint reachable through the website itself (nginx proxies /api).

    Also checks the database, so a monitor notices when the API is up but cannot reach it.
    """
    from sqlalchemy import text

    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "healthy", "database": "ok"}


@app.get("/api/health/data")
def api_health_data(strict: bool = False):
    """Is fresh data still arriving? 200 if every collector is recent, 503 otherwise.

    For an uptime monitor (e.g. Uptime Kuma): a collector that fails silently, such as the
    news feed, turns this red instead of going unnoticed. Details are in the JSON body.
    """
    from datetime import datetime, timezone

    from sqlalchemy import func

    from models import EnergyNews, FuelPrice, MarketPrice, OilPrice
    from services.admin_stats import age_seconds, freshness_status

    now = datetime.now(timezone.utc)
    # (label, latest timestamp query, ok within seconds, error after seconds)
    checks = {
        "fuel_prices": (FuelPrice.timestamp, 2 * 3600, 6 * 3600),
        "oil_prices": (OilPrice.timestamp, 6 * 3600, 24 * 3600),
        "market_prices": (MarketPrice.timestamp, 6 * 3600, 48 * 3600),
        "energy_news": (EnergyNews.fetched_at, 12 * 3600, 48 * 3600),
    }
    db = SessionLocal()
    try:
        report = {}
        for name, (column, ok_within, error_after) in checks.items():
            latest = db.query(func.max(column)).scalar()
            age = age_seconds(latest, now)
            report[name] = {
                "status": freshness_status(age, ok_within, error_after),
                "age_minutes": None if age is None else round(age / 60),
            }
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    finally:
        db.close()
    bad = [n for n, r in report.items() if r["status"] == "error"]
    # strict=true: also fail while a collector is only "warn" (late, but not yet an error)
    if strict:
        bad = [n for n, r in report.items() if r["status"] != "ok"]
    if bad:
        raise HTTPException(
            status_code=503, detail={"stale": bad, "collectors": report}
        )
    ok_count = sum(1 for r in report.values() if r["status"] == "ok")
    return {
        "status": "healthy",
        "ok_count": ok_count,  # lets a monitor assert ok_count == total (no collector even "warn")
        "total": len(report),
        "collectors": report,
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
