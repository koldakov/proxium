from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ._types import ANONYMOUS, Credentials, Identity, ProxyError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ._types import Session

# What an inbound calls with the client's credentials: an authenticator with the session already bound.
type Authenticate = Callable[[Credentials | None], Awaitable[Identity]]


class AuthenticationRequired(ProxyError):
    pass


class Authenticator(ABC):
    """Turns client credentials into an identity. Where they are checked is up to the implementation.

    One instance serves all connections at once: keep no per-connection state on it,
    otherwise concurrent connections overwrite each other's data.
    """

    @abstractmethod
    async def authenticate(self, credentials: Credentials | None, session: Session, /) -> Identity:
        """Return the identity or raise `AuthenticationRequired`.

        `session` tells who connects and where, e.g. to let in whitelisted client IPs without credentials.
        """


class AnonymousAuthenticator(Authenticator):
    """Lets everyone in. Only for local development."""

    async def authenticate(self, credentials: Credentials | None, session: Session, /) -> Identity:
        return ANONYMOUS
