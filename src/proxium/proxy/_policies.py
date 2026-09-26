from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ._types import ProxyError

if TYPE_CHECKING:
    from ._types import Request, Session


class Forbidden(ProxyError):
    pass


class Policy(ABC):
    """Decides whether an authenticated request may go through.

    One instance serves all connections at once: keep no per-connection state on it,
    otherwise concurrent connections overwrite each other's data.
    """

    @abstractmethod
    async def check(self, request: Request, session: Session, /) -> None:
        """Raise `Forbidden` to deny the request. `session` has the client and listener addresses."""
