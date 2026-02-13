"""User service - profile, preferences, search history."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from sky_scanner_db.models.search import SearchHistory
from sky_scanner_db.models.user import User, UserPreference

if TYPE_CHECKING:
    from datetime import date
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from sky_scanner_api.schemas.users import UpdatePreferenceRequest


class UserService:
    """Handles user profile, preferences, and search history."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        """Fetch a user by primary key."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> User | None:
        """Fetch a user by email address."""
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_preferences(self, user_id: UUID) -> UserPreference | None:
        """Fetch preferences for a given user."""
        result = await self.db.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def update_preferences(
        self,
        user_id: UUID,
        prefs: UpdatePreferenceRequest,
    ) -> UserPreference:
        """Upsert user preferences."""
        result = await self.db.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        preference = result.scalar_one_or_none()

        update_data = prefs.model_dump(exclude_none=True)

        if preference is None:
            preference = UserPreference(user_id=user_id, **update_data)
            self.db.add(preference)
        else:
            for key, value in update_data.items():
                setattr(preference, key, value)

        await self.db.flush()
        return preference

    async def get_search_history(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SearchHistory], int]:
        """Fetch paginated search history for a user."""
        count_result = await self.db.execute(
            select(func.count())
            .select_from(SearchHistory)
            .where(SearchHistory.user_id == user_id)
        )
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(SearchHistory)
            .where(SearchHistory.user_id == user_id)
            .order_by(SearchHistory.searched_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        items = list(result.scalars().all())
        return items, total

    async def save_search(
        self,
        user_id: UUID,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: date | None,
        passengers: int,
        cabin_class: str,
        results_count: int,
    ) -> SearchHistory:
        """Record a search to the user's history."""
        entry = SearchHistory(
            user_id=user_id,
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            passengers=passengers,
            cabin_class=cabin_class,
            results_count=results_count,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry
