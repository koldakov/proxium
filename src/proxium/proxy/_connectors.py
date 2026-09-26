from __future__ import annotations

import asyncio
import socket
from abc import ABC, abstractmethod
from ipaddress import ip_address
from typing import TYPE_CHECKING

from ._guards import DEFAULT_GUARD, ForbiddenAddress
from ._stream import Stream
from ._types import ProxyError

if TYPE_CHECKING:
    from ._guards import AddressGuard, IPAddress
    from ._types import Address, Request, Session


class TargetUnreachable(ProxyError):
    pass


class TargetTimeout(TargetUnreachable):
    pass


class Connector(ABC):
    """Opens the outgoing connection: directly, through an upstream proxy, from a chosen IP, etc.

    One instance serves all connections at once: keep no per-connection state on it,
    otherwise concurrent connections overwrite each other's data.
    """

    @abstractmethod
    async def connect(self, request: Request, session: Session, /) -> Stream:
        """Return a stream to `request.target` or raise `TargetUnreachable`.

        `session` tells where the client came in, e.g. to pick the outgoing IP by the listener port.
        """


class DirectConnector(Connector):
    """Connects straight to the target. Resolves the name itself, so `guard` checks the very addresses it connects to.

    Pass `guard=None` to connect anywhere, loopback and private networks included.
    """

    def __init__(
        self,
        *,
        timeout: float = 10,
        guard: AddressGuard | None = DEFAULT_GUARD,
    ) -> None:
        self._timeout: float = timeout
        self._guard: AddressGuard | None = guard

    async def connect(self, request: Request, session: Session, /) -> Stream:
        target = request.target
        try:
            async with asyncio.timeout(self._timeout):
                ips = await self._resolve(target)
                return await self._open(ips, target)
        except TimeoutError as error:
            raise TargetTimeout(str(target)) from error

    async def _resolve(self, target: Address, /) -> list[IPAddress]:
        """Addresses of the target the guard lets through, in resolver order."""
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(target.host, target.port, type=socket.SOCK_STREAM)
        except OSError as error:
            raise TargetUnreachable(str(target)) from error

        ips = list(dict.fromkeys(ip_address(sockaddr[0]) for *_, sockaddr in infos))
        if self._guard is not None:
            ips = [ip for ip in ips if self._guard.is_allowed(ip)]
        if not ips:
            raise ForbiddenAddress(str(target))
        return ips

    async def _open(self, ips: list[IPAddress], target: Address, /) -> Stream:
        """Connect to the first address that answers."""
        last_error: OSError | None = None
        for ip in ips:
            try:
                reader, writer = await asyncio.open_connection(str(ip), target.port)
            except OSError as error:
                last_error = error
            else:
                return Stream(reader, writer)
        raise TargetUnreachable(str(target)) from last_error
