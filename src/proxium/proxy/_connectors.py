from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ._stream import Stream
from ._types import ProxyError

if TYPE_CHECKING:
    from ._types import Request, Session


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
    def __init__(
        self,
        *,
        timeout: float = 10,
    ) -> None:
        self._timeout: float = timeout

    async def connect(self, request: Request, session: Session, /) -> Stream:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(request.target.host, request.target.port),
                timeout=self._timeout,
            )
        except TimeoutError as error:
            raise TargetTimeout(str(request.target)) from error
        except OSError as error:
            raise TargetUnreachable(str(request.target)) from error
        return Stream(reader, writer)
