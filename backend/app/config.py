from pydantic_settings import BaseSettings
from typing import Optional, List
from pathlib import Path


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://fuel:fuel@db:5432/fuelprices"
    TANKERKONIG_API_KEY: str
    TANKERKONIG_BASE_URL: str = "https://creativecommons.tankerkoenig.de/json"

    # Location settings from config.env
    LATITUDE: float = 52.52
    LONGITUDE: float = 13.405
    RANGE: float = 10.0  # km

    # CORS Settings
    ALLOWED_ORIGINS: str = "*"

    @property
    def get_allowed_origins(self) -> List[str]:
        """Parse comma-separated origins into a list"""
        if self.ALLOWED_ORIGINS == "*":
            return ["*"]
        return [
            origin.strip()
            for origin in self.ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]

    class Config:
        env_file = str(Path(__file__).resolve().parent.parent.parent / "config.env")


settings = Settings()
