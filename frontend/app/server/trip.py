"""
Trip API for Unity: store and retrieve origin (lat/lng), destination (lat/lng), departure (hour, minute).
Logged in: user_email from JWT. Anonymous: anonymous_id from body/query.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import desc

from . import schemas, models
from .database import AsyncSessionLocal
from .auth import get_current_user_optional

router = APIRouter(prefix="/trip", tags=["trip"])


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def _trip_to_out(t: models.Trip) -> schemas.TripOut:
    return schemas.TripOut(
        id=t.id,
        user_email=t.user_email,
        anonymous_id=t.anonymous_id,
        origin=schemas.LatLng(lat=t.origin_lat, lng=t.origin_lng),
        destination=schemas.LatLng(lat=t.dest_lat, lng=t.dest_lng),
        departure=schemas.DepartureTime(hour=t.departure_hour, minute=t.departure_minute),
        created_at=t.created_at,
    )


@router.post("", response_model=schemas.TripOut)
async def create_trip(
    body: schemas.TripCreate,
    current_user: models.User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Save a trip. Logged in: use email from JWT. Anonymous: require anonymous_id in body.
    """
    if current_user is not None:
        user_email, anonymous_id = current_user.email, None
    else:
        if not body.anonymous_id or not body.anonymous_id.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="anonymous_id required when not logged in",
            )
        user_email, anonymous_id = None, body.anonymous_id.strip()

    trip = models.Trip(
        user_email=user_email,
        anonymous_id=anonymous_id,
        origin_lat=body.origin.lat,
        origin_lng=body.origin.lng,
        dest_lat=body.destination.lat,
        dest_lng=body.destination.lng,
        departure_hour=body.departure.hour,
        departure_minute=body.departure.minute,
    )
    db.add(trip)
    await db.commit()
    await db.refresh(trip)
    return _trip_to_out(trip)


@router.get("", response_model=schemas.TripOut)
async def get_latest_trip(
    current_user: models.User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
    email: str | None = Query(None, description="For Unity: filter by email (must match JWT if provided)"),
    anonymous_id: str | None = Query(None, description="For Unity: get latest trip by anonymous_id when no auth"),
):
    """
    Get latest trip. Either Bearer token (then by user email) or query anonymous_id= (no auth).
    """
    if current_user is not None:
        use_email = email if email else current_user.email
        if email and email != current_user.email:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="email must match authenticated user")
        q = (
            select(models.Trip)
            .where(models.Trip.user_email == use_email)
            .order_by(desc(models.Trip.created_at))
            .limit(1)
        )
    elif anonymous_id:
        q = (
            select(models.Trip)
            .where(models.Trip.anonymous_id == anonymous_id.strip())
            .order_by(desc(models.Trip.created_at))
            .limit(1)
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Provide Authorization Bearer or query anonymous_id=",
        )
    result = await db.execute(q)
    trip = result.scalars().first()
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No trip found")
    return _trip_to_out(trip)
