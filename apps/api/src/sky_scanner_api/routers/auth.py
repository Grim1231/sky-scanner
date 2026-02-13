"""Authentication endpoints - register, login, refresh."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Body, Depends

from sky_scanner_api.dependencies import get_db
from sky_scanner_api.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from sky_scanner_api.services.auth_service import AuthService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["auth"])

DbDep = Annotated["AsyncSession", Depends(get_db)]


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    request: RegisterRequest,
    db: DbDep,
) -> TokenResponse:
    """Register a new user and return tokens."""
    service = AuthService(db)
    user = await service.register(request.email, request.name, request.password)
    return service._create_token_response(str(user.id))


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: DbDep,
) -> TokenResponse:
    """Authenticate and return tokens."""
    service = AuthService(db)
    return await service.login(request.email, request.password)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    refresh_token: Annotated[str, Body(embed=True)],
    db: DbDep,
) -> TokenResponse:
    """Exchange a refresh token for a new token pair."""
    service = AuthService(db)
    return await service.refresh_token(refresh_token)
