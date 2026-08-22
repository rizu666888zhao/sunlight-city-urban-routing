from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
import os
from dotenv import load_dotenv
from pathlib import Path

# Load the server/.env explicitly (so running uvicorn from repo root works)
dotenv_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=dotenv_path)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Copy server/.env.example to server/.env and configure it.")

# On Vercel/serverless (or Supabase), use NullPool + connection timeout to avoid hangs/Errno 99
_engine_kw = {"echo": False, "future": True}
if os.getenv("VERCEL") or "supabase.co" in (DATABASE_URL or ""):
    _engine_kw["poolclass"] = NullPool
    # Timeout so serverless doesn't hang; asyncpg passes this to connect()
    _engine_kw["connect_args"] = {"timeout": 10}

engine = create_async_engine(DATABASE_URL, **_engine_kw)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()
