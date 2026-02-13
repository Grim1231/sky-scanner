"""Flight search router."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends

from sky_scanner_api.dependencies import (
    get_current_user,
    get_db,
    get_redis,
    user_id_from_token,
)
from sky_scanner_api.schemas.search import FlightSearchRequest, FlightSearchResponse
from sky_scanner_api.services.search_service import SearchService

if TYPE_CHECKING:
    import redis.asyncio as redis
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/search", tags=["search"])

DbDep = Annotated["AsyncSession", Depends(get_db)]
RedisDep = Annotated["redis.Redis", Depends(get_redis)]
OptionalUser = Annotated[dict | None, Depends(get_current_user)]


@router.post("/flights", response_model=FlightSearchResponse)
async def search_flights(
    request: FlightSearchRequest,
    db: DbDep,
    redis_conn: RedisDep,
    current_user: OptionalUser,
) -> FlightSearchResponse:
    """Search for flights matching the given criteria."""
    service = SearchService(db, redis_conn)
    return await service.search_flights(
        request,
        user_id=user_id_from_token(current_user),
    )
