"""
Authentication API routes.
POST /auth/register   - create new user
POST /auth/login      - get JWT token
GET  /auth/me         - current user profile
"""
import logging
from datetime import timedelta

from fastapi import APIRouter, HTTPException, status, Depends, Request
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError

from core.database import AuditLog, User, Workspace, get_db
from core.deps import CurrentUser, DBSession
from core.security import create_access_token, get_password_hash, verify_password
from core.config import settings
from models.schemas import TokenResponse, UserLogin, UserRegister, UserResponse

import time
from typing import Dict, Tuple

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)

# Simple in-memory rate limiter: IP -> (attempt_count, window_reset_time)
_rate_limits: Dict[str, Tuple[int, float]] = {}

def check_rate_limit(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    count, reset_time = _rate_limits.get(client_ip, (0, now + 60))
    if now > reset_time:
        count = 0
        reset_time = now + 60
        
    if count >= 5:
        raise HTTPException(status_code=429, detail="Too many attempts, please try again later.")
        
    _rate_limits[client_ip] = (count + 1, reset_time)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(check_rate_limit)])
async def register(payload: UserRegister, db: DBSession):
    """Register a new user account."""
    try:
        # Clean optional fields so blank strings do not count as duplicate values.
        email = payload.email.strip() if payload.email else None
        if email == "":
            email = None

        # Check username uniqueness
        existing = await db.execute(select(User).where(User.username == payload.username))
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail="Username already taken")

        if email:
            existing_email = await db.execute(select(User).where(User.email == email))
            if existing_email.scalars().first():
                raise HTTPException(status_code=400, detail="Email already taken")

        user = User(
            username=payload.username,
            email=email,
            full_name=payload.full_name,
            hashed_password=get_password_hash(payload.password),
            role="user",
        )
        db.add(user)
        try:
            await db.commit()
        except IntegrityError as e:
            await db.rollback()
            if 'users.username' in str(e) or 'username' in str(e).lower():
                raise HTTPException(status_code=400, detail="Username already taken") from e
            if 'users.email' in str(e) or 'email' in str(e).lower():
                raise HTTPException(status_code=400, detail="Email already taken") from e
            raise HTTPException(status_code=400, detail="Unable to create account") from e

        await db.refresh(user)

        # Auto-create default workspace for user
        default_ws = Workspace(
            name="General Workspace",
            workspace_type="business",
            description="Default business workspace",
            owner_id=user.id,
        )
        db.add(default_ws)

        # Audit log
        db.add(AuditLog(user_id=user.id, action="register", resource="user", details={"username": "[REDACTED]"}))
        try:
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.exception("Finalizing user registration failed for username=[REDACTED]")
            raise HTTPException(status_code=500, detail="Unable to finalize account creation") from exc

        logger.info("New user registered: [REDACTED] with default workspace created")
        return user
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Registration failed for username=[REDACTED]")
        raise HTTPException(status_code=500, detail="Unable to create account") from exc


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(check_rate_limit)])
async def login(payload: UserLogin, db: DBSession):
    """Login and receive a JWT access token."""
    try:
        result = await db.execute(
            select(User).where(
                or_(User.username == payload.username, User.email == payload.username)
            )
        )
        user = result.scalars().first()

        if not user or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is disabled")

        token = create_access_token(
            data={"sub": str(user.id)},
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )

        db.add(AuditLog(user_id=user.id, action="login", resource="user"))
        try:
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.exception("Login audit commit failed for username=[REDACTED]")
            raise HTTPException(status_code=500, detail="Unable to complete login") from exc

        return TokenResponse(
            access_token=token,
            user_id=user.id,
            username=user.username,
            role=user.role,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Login failed for username=[REDACTED]")
        raise HTTPException(status_code=500, detail="Unable to complete login") from exc


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser):
    """Return the currently authenticated user's profile."""
    return current_user

@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(current_user: CurrentUser, db: DBSession):
    """Delete the currently authenticated user's profile and all their data."""
    try:
        await db.delete(current_user)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("Failed to delete account for user_id=[REDACTED]")
        raise HTTPException(status_code=500, detail="Unable to delete account") from exc
