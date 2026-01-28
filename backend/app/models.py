from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime

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
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    prices = relationship("FuelPrice", back_populates="station")

    __table_args__ = (Index("idx_station_location", "latitude", "longitude"),)


class FuelPrice(Base):
    __tablename__ = "fuel_prices"

    id = Column(String, primary_key=True)  # Will be generated as UUID
    station_id = Column(String, ForeignKey("stations.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

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
