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

    # CORS Settings — default to restrictive; override in config.env
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    # Enable /docs, /redoc and /openapi.json (off by default; true for development only)
    ENABLE_DOCS: bool = False

    # Look up visitor locations via the third-party service ipapi.co. This sends visitor
    # IP addresses to that service, so it is off by default (the admin map stays empty).
    ENABLE_IP_GEOLOCATION: bool = False

    # JWT Authentication
    JWT_SECRET_KEY: str = "overwritten-in-config-env-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # reCAPTCHA v2 (optional - leave empty to disable)
    RECAPTCHA_SECRET_KEY: Optional[str] = None

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
