"""FastAPI application factory."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sky_scanner_api.config import settings

# Propagate DB URL so sky_scanner_db.database picks it up via os.getenv.
os.environ.setdefault("DATABASE_URL", settings.database_url)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sky_scanner_api.cache.redis_client import close_redis, init_redis
from sky_scanner_api.middleware.rate_limit import RateLimitMiddleware
from sky_scanner_api.routers import (
    airlines,
    airports,
    auth,
    prices,
    search,
    users,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage startup / shutdown resources."""
    await init_redis(settings.redis_url)
    yield
    await close_redis()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="Sky Scanner API",
        version="0.1.0",
        lifespan=_lifespan,
    )

    # Middleware (order matters: last added = first executed)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        RateLimitMiddleware,
        redis_url=settings.redis_url,
        requests_per_minute=settings.rate_limit_per_minute,
    )

    # Routers
    _prefix = "/api/v1"
    app.include_router(search.router, prefix=_prefix)
    app.include_router(prices.router, prefix=_prefix)
    app.include_router(airports.router, prefix=_prefix)
    app.include_router(airlines.router, prefix=_prefix)
    app.include_router(auth.router, prefix=_prefix)
    app.include_router(users.router, prefix=_prefix)

    return app


app = create_app()
