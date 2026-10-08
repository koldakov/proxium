from __future__ import annotations

import asyncio
import errno
import socket
from abc import ABC, abstractmethod
from ipaddress import IPv6Address, ip_address
from typing import TYPE_CHECKING, Final

from ._guards import DEFAULT_GUARD, ForbiddenAddress
from ._stream import Stream
from ._types import ProxyError

if TYPE_CHECKING:
    from ._guards import AddressGuard, IPAddress
    from ._types import Address, Request, Session


# One `getaddrinfo` entry: family, type, proto, canonname and sockaddr, (host, port) for IPv4,
# (host, port, flowinfo, scope_id) for IPv6. (int, bytes) is for raw families, a host name never gives it.
type AddressInfo = tuple[
    socket.AddressFamily,
    socket.SocketKind,
    int,
    str,
    tuple[str, int] | tuple[str, int, int, int] | tuple[int, bytes],
]


class TargetUnreachable(ProxyError):
    pass


class TargetTimeout(TargetUnreachable):
    pass


class SourceUnavailable(TargetUnreachable):
    """No outgoing IP to connect from: none could be picked, or the picked one isn't on this host."""


class SourceSelector(ABC):
    """Picks the IP of this host that a connector connects to the target from.

    One instance serves all connections at once: keep no per-connection state on it,
    otherwise concurrent connections overwrite each other's data.
    """

    @abstractmethod
    def select(self, request: Request, session: Session, /) -> IPAddress | None:
        """The IP to connect from, None to let the OS pick. Raise `SourceUnavailable` if there is none."""


class SystemSourceSelector(SourceSelector):
    """The OS picks, usually the main IP of the server."""

    def select(self, request: Request, session: Session, /) -> IPAddress | None:
        return None


class ListenerSourceSelector(SourceSelector):
    """Out through the IP the client came in: a client of 203.0.113.11:8080 goes out from 203.0.113.11.

    Taken from the socket, not the listener config, so it works on 0.0.0.0 too.
    Loopback listeners get loopback, which reaches no target outside this host.
    """

    def select(self, request: Request, session: Session, /) -> IPAddress | None:
        if session.local is None:
            raise SourceUnavailable("The local address of the client connection is unknown.")

        ip = ip_address(session.local.host)
        # A dual-stack socket shows IPv4 clients as ::ffff:203.0.113.11, bind() wants the IPv4 address.
        if isinstance(ip, IPv6Address):
            return ip.ipv4_mapped or ip
        return ip


SYSTEM_SOURCE: Final[SystemSourceSelector] = SystemSourceSelector()


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
    `source` picks the IP to connect from, only target addresses of its family are tried.
    """

    def __init__(
        self,
        *,
        timeout: float = 10,
        guard: AddressGuard | None = DEFAULT_GUARD,
        source: SourceSelector = SYSTEM_SOURCE,
    ) -> None:
        self._timeout: float = timeout
        self._guard: AddressGuard | None = guard
        self._source: SourceSelector = source

    async def connect(self, request: Request, session: Session, /) -> Stream:
        source = self._source.select(request, session)
        try:
            return await self._connect(request.target, source=source)
        except TimeoutError as error:
            raise TargetTimeout(str(request.target)) from error

    async def _connect(self, target: Address, /, *, source: IPAddress | None = None) -> Stream:
        """Resolve and connect, `timeout` seconds for both together.

        `asyncio.timeout` raises the built-in `TimeoutError` when they run out.
        """
        async with asyncio.timeout(self._timeout):
            ips = await self._resolve(target, source=source)
            return await self._open(ips, target, source=source)

    async def _resolve(self, target: Address, /, *, source: IPAddress | None = None) -> list[IPAddress]:
        """Addresses of the target the guard lets through and `source` can reach, in resolver order."""
        loop = asyncio.get_running_loop()
        try:
            infos: list[AddressInfo] = await loop.getaddrinfo(target.host, target.port, type=socket.SOCK_STREAM)
        except OSError as error:
            raise TargetUnreachable(str(target)) from error

        ips = list(dict.fromkeys(ip_address(sockaddr[0]) for *_, sockaddr in infos))
        if self._guard is not None:
            ips = [ip for ip in ips if self._guard.is_allowed(ip)]

        if not ips:
            raise ForbiddenAddress(str(target))

        # An IPv4 source can't reach an IPv6 target and back.
        if source is not None:
            ips = [ip for ip in ips if ip.version == source.version]
            if not ips:
                raise TargetUnreachable(f"{target} has no IPv{source.version} address to reach from {source}.")
        return ips

    async def _open(self, ips: list[IPAddress], target: Address, /, *, source: IPAddress | None = None) -> Stream:
        """Connect to the first address that answers, from `source` if given."""
        local_addr = None if source is None else (str(source), 0)
        last_error: OSError | None = None
        for ip in ips:
            try:
                reader, writer = await asyncio.open_connection(str(ip), target.port, local_addr=local_addr)
            except OSError as error:
                # The same for every target address: the IP isn't on this host, or it's loopback and can't go out.
                if error.errno == errno.EADDRNOTAVAIL:
                    raise SourceUnavailable(
                        f"Can't connect from {source}: not on this host or loopback. "
                        "In Docker, the host's IPs are seen only with --network host.",
                    ) from error
                last_error = error
            else:
                return Stream(reader, writer)
        raise TargetUnreachable(str(target)) from last_error
