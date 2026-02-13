"""User profile, preferences, and search history endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query

from sky_scanner_api.dependencies import (
    get_db,
    require_current_user,
    user_id_from_token,
)
from sky_scanner_api.schemas.users import (
    SearchHistoryResponse,
    UpdatePreferenceRequest,
    UserPreferenceResponse,
    UserResponse,
)
from sky_scanner_api.services.user_service import UserService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/users", tags=["users"])

DbDep = Annotated["AsyncSession", Depends(get_db)]
CurrentUser = Annotated[dict, Depends(require_current_user)]


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: CurrentUser,
    db: DbDep,
) -> UserResponse:
    """Return the authenticated user's profile."""
    uid = user_id_from_token(current_user)
    service = UserService(db)
    user = await service.get_user_by_id(uid)  # type: ignore[arg-type]
    if user is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return UserResponse.model_validate(user)


@router.get("/me/preferences", response_model=UserPreferenceResponse | None)
async def get_preferences(
    current_user: CurrentUser,
    db: DbDep,
) -> UserPreferenceResponse | None:
    """Return the authenticated user's flight preferences."""
    uid = user_id_from_token(current_user)
    service = UserService(db)
    pref = await service.get_preferences(uid)  # type: ignore[arg-type]
    if pref is None:
        return None
    return UserPreferenceResponse.model_validate(pref)


@router.put("/me/preferences", response_model=UserPreferenceResponse)
async def update_preferences(
    request: UpdatePreferenceRequest,
    current_user: CurrentUser,
    db: DbDep,
) -> UserPreferenceResponse:
    """Create or update the authenticated user's preferences."""
    uid = user_id_from_token(current_user)
    service = UserService(db)
    pref = await service.update_preferences(uid, request)  # type: ignore[arg-type]
    return UserPreferenceResponse.model_validate(pref)


@router.get("/me/history", response_model=SearchHistoryResponse)
async def get_history(
    current_user: CurrentUser,
    db: DbDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SearchHistoryResponse:
    """Return paginated search history for the authenticated user."""
    uid = user_id_from_token(current_user)
    service = UserService(db)
    history, total = await service.get_search_history(uid, page, page_size)  # type: ignore[arg-type]
    return SearchHistoryResponse(history=history, total=total)
