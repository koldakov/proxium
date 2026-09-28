from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Self

from fastapi import FastAPI
from fastapi_pagination import add_pagination

from proxium.db import session_manager
from proxium.utils import metadata

from .routes import api_router

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class ProxiumAPI(FastAPI):
    """FastAPI with the Proxium routers and the database pool closed on shutdown."""

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

    def _setup_routers(self) -> None:
        self.include_router(api_router)

    def _setup_pagination(self) -> None:
        # Resolves `page`/`size` for routes returning `Page[...]`, `apaginate` picks them up.
        add_pagination(self)

    def setup(self) -> None:
        # FastAPI calls it from `__init__`, after the docs routes are added.
        super().setup()

        self._setup_routers()
        self._setup_pagination()


proxium_api: ProxiumAPI = ProxiumAPI()
