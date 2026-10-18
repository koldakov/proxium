from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from faker import Faker


@dataclass(frozen=True, slots=True)
class Website:
    """A site a client reaches through the proxy: every request to `url` gets `body`.

    `visitors` are the IPs it was connected from, in order: where the proxy goes out from.
    """

    url: str
    body: str
    visitors: list[str] = field(default_factory=list)


def _create_answer(body: bytes, /) -> bytes:
    return b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%b" % (len(body), body)


async def _start_website(body: bytes, visitors: list[str], /) -> asyncio.Server:
    """A fake, not an HTTP server: reads the head, answers `body` and closes, whatever was asked.

    A tunnel cut before the head, e.g. held open by the client until the proxy shuts down, gets no answer.
    """
    answer = _create_answer(body)

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        visitors.append(writer.get_extra_info("peername")[0])
        try:
            await reader.readuntil(b"\r\n\r\n")
        except asyncio.IncompleteReadError:
            writer.close()
            return
        writer.write(answer)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    return await asyncio.start_server(handle, "127.0.0.1", 0)


@pytest.fixture
def website_factory(loop_runner: asyncio.Runner) -> Iterator[Callable[[str], Website]]:
    """Websites answering the given body, stopped after the test."""
    servers: list[asyncio.Server] = []

    def create(body: str, /) -> Website:
        visitors: list[str] = []
        server = loop_runner.run(_start_website(body.encode(), visitors))
        servers.append(server)
        host, port = server.sockets[0].getsockname()
        return Website(url=f"http://{host}:{port}/", body=body, visitors=visitors)

    yield create

    for server in servers:
        server.close()
        loop_runner.run(server.wait_closed())


@pytest.fixture
def website(faker: Faker, website_factory: Callable[[str], Website]) -> Website:
    """On loopback: the proxy reaches it only if the settings allow, see `running_proxy`."""
    return website_factory(faker.sentence())
