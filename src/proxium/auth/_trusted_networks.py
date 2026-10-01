from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import TYPE_CHECKING

from sqlalchemy import func, literal, select
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.exc import NoResultFound

from proxium.db import (
    OutgoingIPModel,
    OutgoingMode,
    TrustedNetworkModel,
    TrustedNetworkOutgoingIPModel,
    session_manager,
)
from proxium.proxy import AuthenticationRequired, Authenticator, Identity
from proxium.selectors import outgoing_claims

if TYPE_CHECKING:
    from sqlalchemy import Result, Row, ScalarSelect, Select

    from proxium.proxy import Credentials, Session


class TrustedNetworkAuthenticationError(Exception):
    """Why a trusted network check failed. Local: `authenticate` turns it into `AuthenticationRequired`."""


class UnexpectedCredentialsError(TrustedNetworkAuthenticationError):
    """The client sent credentials: this authenticator can't check them, so it doesn't let them through."""


class UnknownClientError(TrustedNetworkAuthenticationError):
    """The client address is unknown or not an IP, so it can't be in a network."""


class UntrustedNetworkError(TrustedNetworkAuthenticationError):
    """No active trusted network contains the client address."""


class TrustedNetworkAuthenticator(Authenticator):
    """Lets in clients without credentials from active `TrustedNetworkModel` networks, refuses the rest.

    Looked up on every connection, so changes apply to new connections at once. Open ones are never cut.
    """

    def _get_client_ip(self, proxy_session: Session, /) -> IPv4Address | IPv6Address:
        if proxy_session.client is None:
            raise UnknownClientError()

        # A link-local IPv6 peer comes with a zone, e.g. `fe80::1%eth0`, the database knows no zones.
        host = proxy_session.client.host.partition("%")[0]
        try:
            ip = ip_address(host)
        except ValueError as err:
            raise UnknownClientError() from err

        # A dual-stack socket shows IPv4 clients as ::ffff:10.0.0.1, networks are stored as IPv4.
        if isinstance(ip, IPv6Address):
            return ip.ipv4_mapped or ip
        return ip

    @property
    def _get_pool_ip_statement(self) -> ScalarSelect[IPv4Address | IPv6Address]:
        # A random IP of the pool, picked in the database so the pool is never loaded. NULL unless the pool is in use.
        return (
            select(OutgoingIPModel.ip)
            .join(
                TrustedNetworkOutgoingIPModel,
                TrustedNetworkOutgoingIPModel.outgoing_ip_id == OutgoingIPModel.id,
            )
            .where(
                TrustedNetworkOutgoingIPModel.trusted_network_id == TrustedNetworkModel.id,
                TrustedNetworkModel.outgoing_mode == OutgoingMode.POOL,
            )
            .order_by(func.random())
            .limit(1)
            .correlate(TrustedNetworkModel)
            .scalar_subquery()
        )

    def _get_network_statement(
        self,
        ip: IPv4Address | IPv6Address,
        /,
    ) -> Select[tuple[TrustedNetworkModel, IPv4Address | IPv6Address | None]]:
        # The narrowest network first: the identity names the most specific one. The pool IP in the same query.
        return (
            select(TrustedNetworkModel, self._get_pool_ip_statement)
            .where(
                TrustedNetworkModel.is_active.is_(True),
                TrustedNetworkModel.network.op(">>=")(literal(ip, INET())),
            )
            .order_by(func.masklen(TrustedNetworkModel.network).desc())
            .limit(1)
        )

    async def _get_network(
        self,
        ip: IPv4Address | IPv6Address,
        /,
    ) -> Row[tuple[TrustedNetworkModel, IPv4Address | IPv6Address | None]]:
        """The network and a random IP of its pool, None unless it goes out through the pool."""
        async with session_manager.session() as session:
            result: Result[tuple[TrustedNetworkModel, IPv4Address | IPv6Address | None]] = await session.execute(
                self._get_network_statement(ip),
            )

        try:
            return result.one()
        except NoResultFound as err:
            raise UntrustedNetworkError() from err

    def _check_no_credentials(self, credentials: Credentials | None, /) -> None:
        # Registered for a credentials kind by mistake, it would let in any password from a trusted network.
        if credentials is not None:
            raise UnexpectedCredentialsError()

    async def authenticate(self, credentials: Credentials | None, proxy_session: Session, /) -> Identity:
        try:
            self._check_no_credentials(credentials)
        except UnexpectedCredentialsError as err:
            raise AuthenticationRequired() from err

        try:
            ip = self._get_client_ip(proxy_session)
        except UnknownClientError as err:
            raise AuthenticationRequired() from err

        try:
            row = await self._get_network(ip)
        except UntrustedNetworkError as err:
            raise AuthenticationRequired() from err
        network, pool_ip = row

        return Identity(
            subject=f"network:{network.network}",
            claims={
                "trusted_network_id": network.id,
                **outgoing_claims(network.outgoing_mode, ip=pool_ip),
            },
        )
