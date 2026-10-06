from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from proxium.proxy import Address, Authenticator, Identity, Meter, Request, Session, Unmetered, Usage

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from faker import Faker

    from proxium.proxy import Credentials


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
