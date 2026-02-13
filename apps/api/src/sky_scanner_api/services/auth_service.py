"""Authentication service - registration, login, JWT management."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import bcrypt
import jwt
from fastapi import HTTPException, status
from sqlalchemy import select

from sky_scanner_api.config import settings
from sky_scanner_api.schemas.auth import TokenResponse
from sky_scanner_db.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AuthService:
    """Handles user authentication and JWT token management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register(self, email: str, name: str, password: str) -> User:
        """Register a new user. Raises 409 if email already taken."""
        existing = await self.db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = User(email=email, name=name, password_hash=hashed)
        self.db.add(user)
        await self.db.flush()
        return user

    async def login(self, email: str, password: str) -> TokenResponse:
        """Authenticate user and return token pair."""
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None or user.password_hash is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        return self._create_token_response(str(user.id))

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """Issue new token pair from a valid refresh token."""
        payload = self.verify_token(refresh_token, expected_type="refresh")
        return self._create_token_response(payload["sub"])

    def _create_token_response(self, user_id: str) -> TokenResponse:
        """Build a TokenResponse with access + refresh tokens."""
        return TokenResponse(
            access_token=self.create_access_token(user_id),
            refresh_token=self.create_refresh_token(user_id),
            expires_in=settings.access_token_expire_minutes * 60,
        )

    @staticmethod
    def create_access_token(user_id: str) -> str:
        """Create a short-lived access token."""
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.access_token_expire_minutes,
        )
        return jwt.encode(
            {"sub": user_id, "exp": expire, "type": "access"},
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )

    @staticmethod
    def create_refresh_token(user_id: str) -> str:
        """Create a long-lived refresh token."""
        expire = datetime.now(UTC) + timedelta(
            days=settings.refresh_token_expire_days,
        )
        return jwt.encode(
            {"sub": user_id, "exp": expire, "type": "refresh"},
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )

    @staticmethod
    def verify_token(token: str, expected_type: str = "access") -> dict:
        """Decode and validate a JWT token."""
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
            )
        except jwt.InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            ) from exc

        if payload.get("type") != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )
        return payload
