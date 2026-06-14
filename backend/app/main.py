from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from limiter import limiter

from database import engine, Base
from routers import stations, prices
from routers import oil_prices
from routers import energy_news
from routers import auth, favorites
from services.data_collector import DataCollector
from services.oil_collector import OilCollector
from services.news_collector import NewsCollector
from config import settings

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables and start scheduler
    Base.metadata.create_all(bind=engine)

    # Initialize data collectors
    collector = DataCollector()
    oil_collector = OilCollector()
    news_collector = NewsCollector()

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

    # Start scheduler
    scheduler.start()

    # Run initial fetches
    await collector.fetch_and_store_prices()
    await oil_collector.fetch_and_store()
    await news_collector.fetch_and_store()

    yield

    # Shutdown: Stop scheduler
    scheduler.shutdown()


app = FastAPI(
    title="FuelTracker API",
    description="Track and analyze fuel prices from Tankerkonig",
    version="1.0.0",
    lifespan=lifespan,
    # Don't expose docs in production unless explicitly enabled
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
)

# Attach rate limiter to the app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware — restrict origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],  # Auth and favorites need POST/DELETE
    allow_headers=["*"],
)

# Include routers
app.include_router(stations.router, prefix="/api/stations", tags=["stations"])
app.include_router(prices.router, prefix="/api/prices", tags=["prices"])
app.include_router(oil_prices.router, prefix="/api/oil-prices", tags=["oil-prices"])
app.include_router(energy_news.router, prefix="/api/energy-news", tags=["energy-news"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(favorites.router, prefix="/api/favorites", tags=["favorites"])


@app.get("/")
async def root():
    return {"message": "FuelTracker API", "status": "running", "docs": "/docs"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
