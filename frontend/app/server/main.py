from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import os
from .auth import router as auth_router
from .trip import router as trip_router
from .optimal_route import router as optimal_route_router
from .database import engine, Base
import asyncio

app = FastAPI(title="Sunshine City API")

# CORS: always include localhost for local dev; add ALLOWED_ORIGINS for production (e.g. Vercel frontend URL)
_local_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
_env_origins = [o.strip() for o in (os.getenv("ALLOWED_ORIGINS") or "").strip().split(",") if o.strip()]
_origins = list(dict.fromkeys(_local_origins + _env_origins))  # dedupe, local first
_origin_regex = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"  # allow any port for localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StripApiPathMiddleware(BaseHTTPMiddleware):
    """On Vercel, the app is mounted at /api; strip /api so routes like /auth/login work."""
    async def dispatch(self, request: Request, call_next):
        path = request.scope.get("path", "")
        if path.startswith("/api"):
            request.scope["path"] = path[4:] or "/"
        return await call_next(request)


app.add_middleware(StripApiPathMiddleware)

app.include_router(auth_router)
app.include_router(trip_router)
app.include_router(optimal_route_router)

@app.on_event("startup")
async def startup_event():
    # Create DB tables if not exist. On Vercel/Supabase tables exist; if connection fails, skip (app still runs).
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        pass  # e.g. serverless cold start, no DB, or tables already exist; auth routes will use DB on first request

@app.get("/")
async def root():
    return {"status": "ok"}
