"""
Optimal route API: C++ algorithm POSTs route here; stored in PostgreSQL (Supabase).
GET returns latest route by user_email or anonymous_id.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import desc

from . import schemas, models
from .database import AsyncSessionLocal
from .auth import get_current_user_optional

router = APIRouter(prefix="/optimal-route", tags=["optimal-route"])


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def _waypoints_to_schema(waypoints: list) -> list[schemas.LatLng]:
    if not waypoints:
        return []
    return [schemas.LatLng(lat=float(p["lat"]), lng=float(p["lng"])) for p in waypoints]


def _route_to_out(r: models.OptimalRoute) -> schemas.OptimalRouteOut:
    return schemas.OptimalRouteOut(
        id=r.id,
        user_email=r.user_email,
        anonymous_id=r.anonymous_id,
        origin=schemas.LatLng(lat=r.origin_lat, lng=r.origin_lng),
        destination=schemas.LatLng(lat=r.dest_lat, lng=r.dest_lng),
        waypoints=_waypoints_to_schema(r.waypoints or []),
        total_distance_km=r.total_distance_km,
        total_time_minutes=r.total_time_minutes,
        created_at=r.created_at,
    )


@router.post("", response_model=schemas.OptimalRouteOut)
async def create_optimal_route(
    body: schemas.OptimalRouteCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Algorithm client (e.g. Python script) submits computed optimal route. Stored in PostgreSQL/Supabase.
    Provide either anonymous_id or user_email to associate the route.
    """
    waypoints_json = [{"lat": p.lat, "lng": p.lng} for p in body.waypoints]
    route = models.OptimalRoute(
        user_email=body.user_email.strip() if body.user_email else None,
        anonymous_id=body.anonymous_id.strip() if body.anonymous_id else None,
        origin_lat=body.origin.lat,
        origin_lng=body.origin.lng,
        dest_lat=body.destination.lat,
        dest_lng=body.destination.lng,
        waypoints=waypoints_json,
        total_distance_km=body.total_distance_km,
        total_time_minutes=body.total_time_minutes,
    )
    db.add(route)
    await db.commit()
    await db.refresh(route)
    return _route_to_out(route)


@router.get("", response_model=schemas.OptimalRouteOut)
async def get_latest_optimal_route(
    current_user: models.User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
    email: str | None = Query(None, description="Filter by user email (or use Bearer for current user)"),
    anonymous_id: str | None = Query(None, description="Filter by anonymous_id when not logged in"),
):
    """
    Get latest optimal route. Use Bearer token (then by current user email), or query anonymous_id=, or email=.
    """
    use_email = None
    if current_user:
        use_email = email.strip() if email else current_user.email
        if email and email.strip() != current_user.email:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="email must match authenticated user")
    elif email:
        use_email = email.strip()
    if use_email:
        q = (
            select(models.OptimalRoute)
            .where(models.OptimalRoute.user_email == use_email)
            .order_by(desc(models.OptimalRoute.created_at))
            .limit(1)
        )
    elif anonymous_id:
        q = (
            select(models.OptimalRoute)
            .where(models.OptimalRoute.anonymous_id == anonymous_id.strip())
            .order_by(desc(models.OptimalRoute.created_at))
            .limit(1)
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Provide Authorization Bearer or query anonymous_id= (or email=)",
        )
    result = await db.execute(q)
    route = result.scalars().first()
    if route is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No optimal route found")
    return _route_to_out(route)
