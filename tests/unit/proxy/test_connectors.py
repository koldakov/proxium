from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import TYPE_CHECKING, Any, Never
from unittest.mock import AsyncMock, patch

import pytest

from proxium.proxy import (
    Address,
    DirectConnector,
    ForbiddenAddress,
    ListenerSourceSelector,
    ResolveTimeout,
    SourceUnavailable,
    TargetNotResolved,
    TargetRefused,
    TargetTimeout,
    TargetUnreachable,
)
from tests.fixtures.proxy import StaticSourceSelector

if TYPE_CHECKING:
    from collections.abc import Callable

    from faker import Faker

    from proxium.proxy import Request, Session


async def _hang(*_args: Any, **_kwargs: Any) -> Never:
    """Stands in for a call that never answers: only a timeout ends it."""
    await asyncio.Event().wait()
    raise AssertionError()


@pytest.fixture
def closed_port() -> int:
    """A loopback port nobody listens on: connections to it are refused at once."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class TestListenerSourceSelector:
    def test_select_raises_source_unavailable_when_local_address_unknown(
        self,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        session.local = None

        # Act & Assert
        with pytest.raises(SourceUnavailable):
            ListenerSourceSelector().select(proxy_request, session)

    def test_select_returns_ipv4_when_local_address_ipv4_mapped(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        # A dual-stack listener: bind() of the outgoing socket wants the IPv4 itself.
        ip = faker.ipv4()
        session.local = Address(f"::ffff:{ip}", faker.port_number())

        # Act
        source = ListenerSourceSelector().select(proxy_request, session)

        # Assert
        assert source == ipaddress.IPv4Address(ip)

    def test_select_returns_ipv6_when_local_address_ipv6(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        ip = faker.ipv6()
        session.local = Address(ip, faker.port_number())

        # Act
        source = ListenerSourceSelector().select(proxy_request, session)

        # Assert
        assert source == ipaddress.IPv6Address(ip)

    def test_select_returns_ipv4_when_local_address_ipv4(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        ip = faker.ipv4()
        session.local = Address(ip, faker.port_number())

        # Act
        source = ListenerSourceSelector().select(proxy_request, session)

        # Assert
        assert source == ipaddress.IPv4Address(ip)


class TestDirectConnector:
    async def test_connect_raises_forbidden_address_when_host_name_resolves_to_loopback(
        self,
        faker: Faker,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        connector = DirectConnector()
        # The guard must check what the name resolves to, not the name: it's refused before any connection.
        proxy_request = proxy_request_factory(target=Address("localhost", faker.port_number()))

        # Act & Assert
        with pytest.raises(ForbiddenAddress):
            await connector.connect(proxy_request, session)

    async def test_connect_raises_resolve_timeout_when_resolver_hangs(
        self,
        faker: Faker,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        connector = DirectConnector(timeout=0.01, guard=None)
        proxy_request = proxy_request_factory(target=Address(faker.hostname(), faker.port_number()))

        # Act & Assert
        with patch.object(asyncio.get_running_loop(), "getaddrinfo", _hang), pytest.raises(ResolveTimeout):
            await connector.connect(proxy_request, session)

    async def test_connect_raises_target_timeout_not_resolve_timeout_when_connection_hangs(
        self,
        faker: Faker,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        connector = DirectConnector(timeout=0.01, guard=None)
        ip = faker.ipv4()
        port = faker.port_number()
        proxy_request = proxy_request_factory(target=Address(ip, port))
        infos = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))]

        # Act
        with (
            patch.object(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=infos)),
            patch("asyncio.open_connection", _hang),
            pytest.raises(TargetTimeout) as error_info,
        ):
            await connector.connect(proxy_request, session)

        # Assert
        assert not isinstance(error_info.value, ResolveTimeout)

    async def test_connect_raises_target_not_resolved_when_name_not_resolved(
        self,
        faker: Faker,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        connector = DirectConnector(guard=None)
        # `.invalid` never resolves (RFC 6761).
        proxy_request = proxy_request_factory(target=Address(f"{faker.word()}.invalid", faker.port_number()))

        # Act & Assert
        with pytest.raises(TargetNotResolved):
            await connector.connect(proxy_request, session)

    async def test_connect_raises_target_unreachable_when_no_address_of_source_family(
        self,
        faker: Faker,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        connector = DirectConnector(guard=None, source=StaticSourceSelector(ipaddress.IPv6Address(faker.ipv6())))
        proxy_request = proxy_request_factory(target=Address(faker.ipv4(), faker.port_number()))

        # Act & Assert
        with pytest.raises(TargetUnreachable, match="no IPv6 address"):
            await connector.connect(proxy_request, session)

    async def test_connect_raises_target_refused_when_connection_refused(
        self,
        closed_port: int,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        connector = DirectConnector(guard=None)
        proxy_request = proxy_request_factory(target=Address("127.0.0.1", closed_port))

        # Act & Assert
        with pytest.raises(TargetRefused):
            await connector.connect(proxy_request, session)

    async def test_connect_raises_source_unavailable_when_source_not_on_host(
        self,
        faker: Faker,
        closed_port: int,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        # TEST-NET-1 (RFC 5737): never an address of this host, bind() fails.
        source = ipaddress.IPv4Address(f"192.0.2.{faker.pyint(min_value=1, max_value=254)}")
        connector = DirectConnector(guard=None, source=StaticSourceSelector(source))
        proxy_request = proxy_request_factory(target=Address("127.0.0.1", closed_port))

        # Act & Assert
        with pytest.raises(SourceUnavailable):
            await connector.connect(proxy_request, session)
