from __future__ import annotations

import asyncio
import socket
from typing import TYPE_CHECKING, Any

import pytest

from proxium.proxy import (
    Address,
    Authenticator,
    Encryption,
    Forbidden,
    Grant,
    Identity,
    Meter,
    Request,
    Session,
    SourceSelector,
    Stream,
    Unmetered,
    Usage,
)

if TYPE_CHECKING:
    import ssl
    from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence

    from faker import Faker

    from proxium.proxy import Credentials, IPAddress


@pytest.fixture
def session_factory(faker: Faker) -> Callable[[], Session]:
    """Sessions of a new client address on every call."""

    def create() -> Session:
        return Session(
            client=Address(faker.ipv4(), faker.port_number()),
            listener=Address(faker.ipv4(), faker.port_number()),
            local=None,
        )

    return create


@pytest.fixture
def session(session_factory: Callable[[], Session]) -> Session:
    return session_factory()


@pytest.fixture
def proxy_request_factory(faker: Faker) -> Callable[..., Request]:
    """Requests of a new identity on every call, with `target` and `claims` if given."""

    def create(*, target: Address | None = None, claims: Mapping[str, Any] | None = None) -> Request:
        return Request(
            protocol=faker.random_element(["http", "socks5"]),
            target=Address(faker.hostname(), faker.port_number()) if target is None else target,
            identity=Identity(subject=faker.uuid4(), claims={} if claims is None else claims),
        )

    return create


@pytest.fixture
def proxy_request(proxy_request_factory: Callable[..., Request]) -> Request:
    return proxy_request_factory()


class FailingOnceAuthenticator(Authenticator):
    """Fails the first check as if the database were down, lets everyone in as `identity` after."""

    def __init__(self, identity: Identity, /) -> None:
        self.identity: Identity = identity
        self._failed: bool = False

    async def authenticate(self, credentials: Credentials | None, session: Session, /) -> Identity:
        if not self._failed:
            self._failed = True
            raise ConnectionError()
        return self.identity


@pytest.fixture
def failing_once_authenticator(faker: Faker) -> FailingOnceAuthenticator:
    return FailingOnceAuthenticator(Identity(subject=faker.uuid4()))


class StaticMeter(Meter):
    """Measures `usage` for every client, changed by the test as it goes."""

    def __init__(self, usage: Usage, /) -> None:
        self.usage: Usage = usage

    async def measure(self, request: Request, session: Session, /) -> Usage:
        return self.usage


@pytest.fixture
def static_meter() -> StaticMeter:
    return StaticMeter(Usage())


class UnmeteringMeter(Meter):
    """Can't measure anyone, as for anonymous clients."""

    async def measure(self, request: Request, session: Session, /) -> Usage:
        raise Unmetered()


@pytest.fixture
def unmetering_meter() -> UnmeteringMeter:
    return UnmeteringMeter()


class ScriptedStream(Stream):
    """Reads give `chunks` one by one, then EOF, or `error` if given. Keeps what is written."""

    def __init__(self, chunks: Sequence[bytes] = (), /, *, error: OSError | None = None) -> None:
        self._chunks: list[bytes] = list(chunks)
        self._error: OSError | None = error
        self.written: bytearray = bytearray()

    async def read(self, n: int | None = None, /) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        if self._error is not None:
            raise self._error
        return b""

    def write(self, data: bytes, /) -> None:
        self.written += data

    async def drain(self) -> None:
        pass

    def write_eof(self) -> None:
        pass


class StalledStream(ScriptedStream):
    """Reads never return, as from a peer that went silent."""

    async def read(self, n: int | None = None, /) -> bytes:
        await asyncio.Event().wait()
        raise AssertionError()


class CuttingGrant(Grant):
    """Cuts the tunnel on the first bytes from the client, as over a quota."""

    def __init__(self) -> None:
        self.error: Forbidden = Forbidden()

    async def on_sent(self, n: int, /) -> None:
        raise self.error


class HoldingGrant(Grant):
    """Holds every chunk from the client back for `delay` seconds, as a speed limit does."""

    def __init__(self, delay: float, /) -> None:
        self._delay: float = delay

    async def on_sent(self, n: int, /) -> None:
        await asyncio.sleep(self._delay)


class ScriptedEncryption(Encryption):
    """Answers with `outcomes` in turn, the last one ever after: returns a context, raises an exception. Counts calls.

    Yields to the loop on every call, as a database lookup would: concurrent connections overlap.
    """

    def __init__(self, outcomes: Sequence[ssl.SSLContext | Exception], /) -> None:
        self._outcomes: tuple[ssl.SSLContext | Exception, ...] = tuple(outcomes)
        self.calls: int = 0

    async def context(self, session: Session, /) -> ssl.SSLContext:
        outcome = self._outcomes[min(self.calls, len(self._outcomes) - 1)]
        self.calls += 1
        await asyncio.sleep(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class StaticSourceSelector(SourceSelector):
    """Always connects from `ip`, as a pool of one would."""

    def __init__(self, ip: IPAddress, /) -> None:
        self._ip: IPAddress = ip

    def select(self, request: Request, session: Session, /) -> IPAddress | None:
        return self._ip


@pytest.fixture
def socket_pair() -> Iterator[tuple[socket.socket, socket.socket]]:
    """Two connected sockets: no network, no ports."""
    ours, peer = socket.socketpair()
    yield ours, peer
    ours.close()
    peer.close()


@pytest.fixture
def peer_socket(socket_pair: tuple[socket.socket, socket.socket]) -> socket.socket:
    """The other end of `stream`, blocking: a timeout keeps a broken test from hanging."""
    peer = socket_pair[1]
    peer.settimeout(1)
    return peer


@pytest.fixture
async def stream(socket_pair: tuple[socket.socket, socket.socket]) -> AsyncIterator[Stream]:
    reader, writer = await asyncio.open_connection(sock=socket_pair[0])
    stream = Stream(reader, writer)
    yield stream
    await stream.close()
