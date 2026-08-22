from sqlalchemy import Column, Integer, String, DateTime, Float, func
from sqlalchemy.dialects.postgresql import JSONB
from .database import Base

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Trip(Base):
    """Stores origin, destination, departure for Unity. Logged in: user_email; anonymous: anonymous_id."""
    __tablename__ = 'trips'

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String(255), index=True, nullable=True)   # when logged in
    anonymous_id = Column(String(255), index=True, nullable=True)  # when not logged in
    origin_lat = Column(Float, nullable=False)
    origin_lng = Column(Float, nullable=False)
    dest_lat = Column(Float, nullable=False)
    dest_lng = Column(Float, nullable=False)
    departure_hour = Column(Integer, nullable=False)   # 0-23
    departure_minute = Column(Integer, nullable=False)  # 0-59
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OptimalRoute(Base):
    """Stores optimal route from algorithm (Python client) for Unity/Web. One row per submission."""
    __tablename__ = "optimal_routes"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String(255), index=True, nullable=True)
    anonymous_id = Column(String(255), index=True, nullable=True)
    origin_lat = Column(Float, nullable=False)
    origin_lng = Column(Float, nullable=False)
    dest_lat = Column(Float, nullable=False)
    dest_lng = Column(Float, nullable=False)
    waypoints = Column(JSONB, nullable=False)  # list of {"lat": float, "lng": float}
    total_distance_km = Column(Float, nullable=True)
    total_time_minutes = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
