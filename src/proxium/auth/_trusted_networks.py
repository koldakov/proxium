from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import TYPE_CHECKING

from sqlalchemy import func, literal, select
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.exc import NoResultFound

from proxium.core import api_settings
from proxium.db import (
    OutgoingIPModel,
    OutgoingMode,
    TrustedNetworkModel,
    TrustedNetworkOutgoingIPModel,
    TrustedNetworkPolicyModel,
    session_manager,
)
from proxium.policies import policy_claims
from proxium.proxy import AuthenticationRequired, Authenticator, Identity
from proxium.selectors import outgoing_claims

if TYPE_CHECKING:
    from datetime import date

    from sqlalchemy import Result, Select

    from proxium.proxy import Credentials, IPAddress, Session


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

    Looked up anew on every call: wrap it in `CachedAuthenticator`. Open connections are never cut.
    """

    def __init__(
        self,
        *,
        pool_max_size: int = api_settings.outgoing_pool_max_size,
        policies_max_size: int = api_settings.policies_max_per_owner,
    ) -> None:
        # The API keeps pools and policies within these, the caps only bound the queries.
        self._pool_max_size: int = pool_max_size
        self._policies_max_size: int = policies_max_size

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

    def _get_pool_statement(self, network: TrustedNetworkModel, /) -> Select[tuple[IPAddress]]:
        return (
            select(OutgoingIPModel.ip)
            .join(
                TrustedNetworkOutgoingIPModel,
                TrustedNetworkOutgoingIPModel.outgoing_ip_id == OutgoingIPModel.id,
            )
            .where(TrustedNetworkOutgoingIPModel.trusted_network_id == network.id)
            .limit(self._pool_max_size)
        )

    async def _get_pool(self, network: TrustedNetworkModel, /) -> list[IPAddress]:
        """The IPs of the network's pool, empty unless it goes out through the pool."""
        if network.outgoing_mode != OutgoingMode.POOL:
            return []

        async with session_manager.session() as session:
            result: Result[tuple[IPAddress]] = await session.execute(self._get_pool_statement(network))

        return list(result.scalars())

    def _get_policies_statement(self, network: TrustedNetworkModel, /) -> Select[tuple[int, date]]:
        return (
            select(TrustedNetworkPolicyModel.policy_id, TrustedNetworkPolicyModel.starts_on)
            .where(TrustedNetworkPolicyModel.trusted_network_id == network.id)
            .order_by(TrustedNetworkPolicyModel.policy_id)
            .limit(self._policies_max_size)
        )

    async def _get_policies(self, network: TrustedNetworkModel, /) -> dict[int, date]:
        """The policies assigned to the network, active or not: the proxy knows which are active.

        By id, the day each assignment's quota periods count from.
        """
        async with session_manager.session() as session:
            result: Result[tuple[int, date]] = await session.execute(self._get_policies_statement(network))

        return dict(result.tuples().all())

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
            network = await self._get_network(ip)
        except UntrustedNetworkError as err:
            raise AuthenticationRequired() from err

        pool = await self._get_pool(network)
        policies = await self._get_policies(network)
        return Identity(
            subject=f"network:{network.network}",
            claims={
                "trusted_network_id": network.id,
                **outgoing_claims(network.outgoing_mode, ips=pool),
                **policy_claims(policies),
            },
        )
