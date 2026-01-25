from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://fuel:fuel@db:5432/fuelprices"
    TANKERKONIG_API_KEY: str
    TANKERKONIG_BASE_URL: str = "https://creativecommons.tankerkoenig.de/json"
    
    # Location settings from config.env
    LATITUDE: float = 52.52
    LONGITUDE: float = 13.405
    RANGE: float = 10.0  # km
    
    class Config:
        env_file = "../config.env"


settings = Settings()
