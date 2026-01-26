from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import engine, Base
from routers import stations, prices
from services.data_collector import DataCollector
from config import settings


scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables and start scheduler
    Base.metadata.create_all(bind=engine)
    
    # Initialize data collector
    collector = DataCollector()
    
    # Fetch data every hour as requested
    scheduler.add_job(
        collector.fetch_and_store_prices,
        'interval',
        hours=1,
        id='fetch_prices'
    )
    
    # Start scheduler
    scheduler.start()
    
    # Run initial fetch
    await collector.fetch_and_store_prices()
    
    yield
    
    # Shutdown: Stop scheduler
    scheduler.shutdown()


app = FastAPI(
    title="FuelTracker API",
    description="Track and analyze fuel prices from Tankerkonig",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for Svelte frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(stations.router, prefix="/api/stations", tags=["stations"])
app.include_router(prices.router, prefix="/api/prices", tags=["prices"])


@app.get("/")
async def root():
    return {
        "message": "FuelTracker API",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
