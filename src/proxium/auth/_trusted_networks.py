from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import TYPE_CHECKING

from sqlalchemy import func, literal, select
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.exc import NoResultFound

from proxium.db import TrustedNetworkModel, session_manager
from proxium.proxy import AuthenticationRequired, Authenticator, Identity

if TYPE_CHECKING:
    from sqlalchemy import Result, Select

    from proxium.proxy import Credentials, Session


class TrustedNetworkAuthenticationError(Exception):
    """Why a trusted network check failed. Local: `authenticate` turns it into `AuthenticationRequired`."""


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

    def _get_network_statement(self, ip: IPv4Address | IPv6Address, /) -> Select[tuple[TrustedNetworkModel]]:
        # The narrowest network first: the identity names the most specific one.
        return (
            select(TrustedNetworkModel)
            .where(
                TrustedNetworkModel.is_active.is_(True),
                TrustedNetworkModel.network.op(">>=")(literal(ip, INET())),
            )
            .order_by(func.masklen(TrustedNetworkModel.network).desc())
            .limit(1)
        )

    async def _get_network(self, ip: IPv4Address | IPv6Address, /) -> TrustedNetworkModel:
        async with session_manager.session() as session:
            result: Result[tuple[TrustedNetworkModel]] = await session.execute(self._get_network_statement(ip))

        try:
            return result.scalars().one()
        except NoResultFound as err:
            raise UntrustedNetworkError() from err

    async def authenticate(self, credentials: Credentials | None, proxy_session: Session, /) -> Identity:
        try:
            ip = self._get_client_ip(proxy_session)
        except UnknownClientError as err:
            raise AuthenticationRequired() from err

        try:
            network = await self._get_network(ip)
        except UntrustedNetworkError as err:
            raise AuthenticationRequired() from err

        return Identity(
            subject=f"network:{network.network}",
            claims={"trusted_network_id": network.id},
        )
