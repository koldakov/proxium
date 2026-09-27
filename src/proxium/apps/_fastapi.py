from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Self

from fastapi import FastAPI

from proxium.db import session_manager
from proxium.utils import metadata

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class ProxiumAPI(FastAPI):
    """Plain FastAPI that closes the database pool on shutdown. Everything else is FastAPI defaults."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("title", metadata["name"])
        kwargs.setdefault("version", metadata["version"])
        kwargs.setdefault("description", metadata["summary"])
        kwargs.setdefault("lifespan", self._lifespan)
        super().__init__(**kwargs)

    @asynccontextmanager
    async def _lifespan(self, _: Self, /) -> AsyncIterator[None]:
        yield
        await session_manager.close()


proxium_api: ProxiumAPI = ProxiumAPI()
