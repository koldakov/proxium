from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from proxium.api import proxium_api

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Iterator


@dataclass(slots=True)
class ApiClient:
    """The API as the admin UI calls it, in process: one logged-in user at a time, by their access token.

    `items` keeps what the steps name, e.g. a created network by its alias, for later paths and bodies.
    """

    http: httpx.AsyncClient
    token: str | None = None
    items: dict[str, dict[str, Any]] = field(default_factory=dict)

    async def send(self, method: str, path: str, /, *, json: Any = None, token: str | None = None) -> httpx.Response:
        """With the logged-in user's token unless `token` is given."""
        token = self.token if token is None else token
        headers = {} if token is None else {"Authorization": f"Bearer {token}"}
        return await self.http.request(method, path, json=json, headers=headers)


@pytest.fixture
def api_client(loop_runner: asyncio.Runner, database: None) -> Iterator[ApiClient]:
    """No lifespan: it would close the database and Redis pools the rest of the run shares."""
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=proxium_api), base_url="http://proxium")

    yield ApiClient(http)

    loop_runner.run(http.aclose())
