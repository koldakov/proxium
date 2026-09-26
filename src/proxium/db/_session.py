from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from proxium.core import database_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class SessionClosedError(RuntimeError):
    pass


class SessionManager:
    """Owns the engine and hands out sessions. One per process: use `session_manager`, close it on shutdown.

    Query parameters never reach logs and errors, even with `echo`: they may hold plain passwords and tokens.
    """

    def __init__(  # noqa: PLR0913
        self,
        url: str,
        /,
        *,
        echo: bool = database_settings.echo,
        pool_size: int = database_settings.pool_size,
        max_overflow: int = database_settings.pool_max_overflow,
        pool_timeout: float = database_settings.pool_timeout,
        pool_recycle: int = database_settings.pool_recycle,
        expire_on_commit: bool = False,
    ) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url,
            echo=echo,
            hide_parameters=True,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
        )
        self._session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine,
            expire_on_commit=expire_on_commit,
        )
        self._is_closed: bool = False

    async def close(self) -> None:
        """Close all pooled connections. Safe to call twice."""
        if self._is_closed:
            return
        self._is_closed = True
        await self.engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """A session that is closed on exit. An uncommitted transaction is rolled back, cancellation included."""
        if self._is_closed:
            raise SessionClosedError("SessionManager is closed.")

        async with self._session_maker() as session:
            yield session


# Connects lazily, on the first session inside the running loop.
session_manager: SessionManager = SessionManager(str(database_settings.url))
