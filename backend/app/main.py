from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import engine, Base
from routers import stations, prices
from routers import oil_prices
from services.data_collector import DataCollector
from services.oil_collector import OilCollector
from config import settings

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables and start scheduler
    Base.metadata.create_all(bind=engine)

    # Initialize data collectors
    collector = DataCollector()
    oil_collector = OilCollector()

    # Fetch fuel prices every 15 minutes
    scheduler.add_job(
        collector.fetch_and_store_prices, "interval", minutes=15, id="fetch_prices"
    )

    # Fetch Brent crude oil price every hour
    scheduler.add_job(
        oil_collector.fetch_and_store, "interval", hours=1, id="fetch_oil_price"
    )

    # Start scheduler
    scheduler.start()

    # Run initial fetches
    await collector.fetch_and_store_prices()
    await oil_collector.fetch_and_store()

    yield

    # Shutdown: Stop scheduler
    scheduler.shutdown()


app = FastAPI(
    title="FuelTracker API",
    description="Track and analyze fuel prices from Tankerkonig",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for Svelte frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(stations.router, prefix="/api/stations", tags=["stations"])
app.include_router(prices.router, prefix="/api/prices", tags=["prices"])
app.include_router(oil_prices.router, prefix="/api/oil-prices", tags=["oil-prices"])


@app.get("/")
async def root():
    return {"message": "FuelTracker API", "status": "running", "docs": "/docs"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
