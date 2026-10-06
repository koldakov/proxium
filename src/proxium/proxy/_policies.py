from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Final

from ._types import ProxyError

if TYPE_CHECKING:
    from ._types import Request, Session


class Forbidden(ProxyError):
    pass


class Grant:
    """What a policy allowed one connection, from the check to the close. Override what you need.

    Byte hooks run before the bytes go on: raise a `ProxyError`, e.g. `Forbidden`, to cut the tunnel, wait to slow
    it down.
    """

    async def on_sent(self, n: int, /) -> None:
        """`n` bytes from the client are about to go to the target."""

    async def on_received(self, n: int, /) -> None:
        """`n` bytes from the target are about to go to the client."""

    async def release(self) -> None:
        """The connection is done. Called once for every grant, even if the target was never reached."""


# For policies that only check the request: nothing to watch or release.
EMPTY_GRANT: Final[Grant] = Grant()


class Policy(ABC):
    """Decides whether an authenticated request may go through, and on what terms.

    One instance serves all connections at once: keep state shared by connections on it, e.g. counters per account,
    and state of one connection on its grant.
    """

    @abstractmethod
    async def admit(self, request: Request, session: Session, /) -> Grant:
        """Raise `Forbidden` to deny the request. `session` has the client and listener addresses."""
