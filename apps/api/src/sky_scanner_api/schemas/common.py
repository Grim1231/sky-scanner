"""Shared response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class PaginatedResponse[T](BaseModel):
    """Generic paginated list response."""

    items: list[T]
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    """Standard error payload."""

    detail: str
    code: str | None = None
