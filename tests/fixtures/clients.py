from __future__ import annotations

import ssl
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Iterator


@pytest.fixture
def client_ssl_context() -> ssl.SSLContext:
    """What a TLS client of the proxy trusts: the system CAs, until a step gives it the proxy's certificate."""
    return ssl.create_default_context()


@pytest.fixture
def tunnels(loop_runner: asyncio.Runner) -> Iterator[list[asyncio.StreamWriter]]:
    """Tunnels the client holds open through the proxy, e.g. to take up a connection limit. Closed after the test."""
    writers: list[asyncio.StreamWriter] = []

    yield writers

    for writer in writers:
        writer.close()
        loop_runner.run(writer.wait_closed())
