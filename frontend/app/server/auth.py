from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from . import schemas, models
from .database import AsyncSessionLocal

load_dotenv()

# Use pbkdf2_sha256 to avoid bcrypt backend issues on some systems and avoid 72-byte limits
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
SECRET_KEY = os.getenv("SECRET_KEY", "secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

router = APIRouter(prefix="/auth", tags=["auth"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@router.post("/signup", response_model=schemas.UserOut)
async def signup(user_in: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    # bcrypt has a maximum password length of 72 bytes; validate and return friendly error
    pw_bytes = user_in.password.encode("utf-8")
    if len(pw_bytes) > 72:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password too long (max 72 bytes). Please use a shorter password.")
    if len(user_in.password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password too short (min 8 characters).")
    try:
        hashed = get_password_hash(user_in.password)
    except ValueError as e:
        msg = str(e)
        if 'longer than 72' in msg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password too long (max 72 bytes). Please use a shorter password.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    user = models.User(email=user_in.email, hashed_password=hashed)
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    return user

@router.post("/login", response_model=schemas.Token)
async def login(user_in: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    try:
        q = select(models.User).where(models.User.email == user_in.email)
        result = await db.execute(q)
        user = result.scalars().first()
    except Exception as e:
        import traceback
        traceback.print_exc()  # so Vercel logs show the real error
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable. Please try again.",
        ) from e
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    try:
        ok = verify_password(user_in.password, user.hashed_password)
    except ValueError as e:
        msg = str(e)
        if 'longer than 72' in msg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password too long (max 72 bytes). Please use a shorter password.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access_token = create_access_token({"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}
from fastapi.security import OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    q = select(models.User).where(models.User.email == email)
    result = await db.execute(q)
    user = result.scalars().first()
    if user is None:
        raise credentials_exception
    return user


async def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db),
) -> models.User | None:
    """Return current user if valid Bearer token; else None (for anonymous trip)."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
    except JWTError:
        return None
    q = select(models.User).where(models.User.email == email)
    result = await db.execute(q)
    return result.scalars().first()


@router.get("/me", response_model=schemas.UserOut)
async def me(current_user: models.User = Depends(get_current_user)):
    return schemas.UserOut(id=current_user.id, email=current_user.email, created_at=current_user.created_at)
