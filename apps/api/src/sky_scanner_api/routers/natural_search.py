"""Natural language search router."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends

from sky_scanner_api.dependencies import (
    get_current_user,
    get_db,
    get_redis,
    user_id_from_token,
)
from sky_scanner_api.schemas.natural_search import (
    NaturalSearchRequest,
    NaturalSearchResponse,
)
from sky_scanner_api.services.natural_search_service import NaturalSearchService

if TYPE_CHECKING:
    import redis.asyncio as redis
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/search", tags=["search"])

DbDep = Annotated["AsyncSession", Depends(get_db)]
RedisDep = Annotated["redis.Redis", Depends(get_redis)]
OptionalUser = Annotated[dict | None, Depends(get_current_user)]


@router.post("/natural", response_model=NaturalSearchResponse)
async def natural_search(
    request: NaturalSearchRequest,
    db: DbDep,
    redis_conn: RedisDep,
    current_user: OptionalUser,
) -> NaturalSearchResponse:
    """Search for flights using a natural language query."""
    service = NaturalSearchService(db, redis_conn)
    result = await service.search(
        request.query,
        user_id=user_id_from_token(current_user),
    )
    return NaturalSearchResponse(**result)
