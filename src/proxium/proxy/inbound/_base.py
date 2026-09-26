from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from proxium.proxy._types import ProxyError, Request

if TYPE_CHECKING:
    from proxium.proxy._auth import Authenticate
    from proxium.proxy._stream import Stream


class BadRequest(ProxyError):
    pass


class Inbound(ABC):
    """Client-facing protocol, e.g. HTTP or SOCKS5. Several inbounds share one port.

    One instance serves all connections at once: keep no per-connection state on it,
    otherwise concurrent connections overwrite each other's data.
    """

    @abstractmethod
    def detect(self, head: bytes, /) -> bool:
        """Whether the connection speaks this protocol, judging by its first byte."""

    @abstractmethod
    async def handshake(self, stream: Stream, authenticate: Authenticate, /) -> Request:
        """Read the request and authenticate the client by calling `authenticate` with its credentials.

        Authentication is left to the inbound because some protocols (SOCKS5) do it mid-handshake.
        """

    @abstractmethod
    async def accept(self, stream: Stream, request: Request, /) -> None:
        """Tell the client the target is connected."""

    @abstractmethod
    async def reject(self, stream: Stream, error: ProxyError, /) -> None:
        """Tell the client why the request failed."""
