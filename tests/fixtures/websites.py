from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

    from faker import Faker


@dataclass(frozen=True, slots=True)
class Website:
    """A site a client reaches through the proxy: every request to `url` gets `body`."""

    url: str
    body: str


def _create_answer(body: bytes, /) -> bytes:
    return b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%b" % (len(body), body)


async def _start_website(body: bytes, /) -> asyncio.Server:
    """A fake, not an HTTP server: reads the head, answers `body` and closes, whatever was asked."""
    answer = _create_answer(body)

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(answer)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    return await asyncio.start_server(handle, "127.0.0.1", 0)


@pytest.fixture
def website(faker: Faker, loop_runner: asyncio.Runner) -> Iterator[Website]:
    """On loopback: the proxy reaches it only if the settings allow, see `running_proxy`."""
    body = faker.sentence()
    server = loop_runner.run(_start_website(body.encode()))
    host, port = server.sockets[0].getsockname()

    yield Website(url=f"http://{host}:{port}/", body=body)

    server.close()
    loop_runner.run(server.wait_closed())
