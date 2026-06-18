from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from datetime import datetime, timezone
import uuid

from database import Base


class Station(Base):
    __tablename__ = "stations"

    id = Column(String, primary_key=True)  # Tankerkonig station UUID
    name = Column(String, nullable=False)
    brand = Column(String)
    street = Column(String)
    house_number = Column(String)
    post_code = Column(String)
    city = Column(String)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    is_open = Column(Boolean, default=True)
    first_seen = Column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_updated = Column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    prices = relationship("FuelPrice", back_populates="station")

    __table_args__ = (Index("idx_station_location", "latitude", "longitude"),)


class FuelPrice(Base):
    __tablename__ = "fuel_prices"

    id = Column(String, primary_key=True)  # Will be generated as UUID
    station_id = Column(String, ForeignKey("stations.id"), nullable=False)
    timestamp = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Fuel types (in EUR)
    e5 = Column(Float, nullable=True)
    e10 = Column(Float, nullable=True)
    diesel = Column(Float, nullable=True)

    # Relationships
    station = relationship("Station", back_populates="prices")

    __table_args__ = (
        Index("idx_price_timestamp", "timestamp"),
        Index("idx_price_station_timestamp", "station_id", "timestamp"),
    )


class OilPrice(Base):
    __tablename__ = "oil_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    price_usd_per_barrel = Column(Float, nullable=False)
    price_eur_per_barrel = Column(Float, nullable=False)
    price_eur_per_liter = Column(Float, nullable=False)

    __table_args__ = (Index("idx_oil_price_timestamp", "timestamp"),)


class EnergyNews(Base):
    __tablename__ = "energy_news"

    link = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    source = Column(String, nullable=False)
    published_at = Column(TIMESTAMP(timezone=True), nullable=True)
    summary = Column(String, nullable=True)
    fetched_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (Index("idx_energy_news_published_at", "published_at"),)


class User(Base):
    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    favorites = relationship("FavoriteStation", back_populates="user", cascade="all, delete-orphan")


class FavoriteStation(Base):
    __tablename__ = "favorite_stations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    station_id = Column(String, ForeignKey("stations.id"), nullable=False)
    added_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="favorites")
    station = relationship("Station")

    __table_args__ = (
        Index("idx_favorite_user_station", "user_id", "station_id", unique=True),
    )


class VisitorLocationCache(Base):
    __tablename__ = "visitor_location_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ip_hash = Column(String, unique=True, nullable=False, index=True)
    country = Column(String, nullable=True)
    region = Column(String, nullable=True)
    city = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    resolved_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_location_cache_coordinates", "latitude", "longitude"),
    )


class TrafficEvent(Base):
    __tablename__ = "traffic_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    page = Column(String, nullable=False, index=True)
    path = Column(String, nullable=False)
    source = Column(String, nullable=False, default="direct", index=True)
    country = Column(String, nullable=True)
    region = Column(String, nullable=True)
    city = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    visited_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_traffic_event_visited_at", "visited_at"),
        Index("idx_traffic_event_page_source", "page", "source"),
    )
