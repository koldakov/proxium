from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Final

from ._types import ANONYMOUS, Credentials, Identity, ProxyError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from ._types import Session

# What an inbound calls with the client's credentials: an authenticator with the session already bound.
type Authenticate = Callable[[Credentials | None], Awaitable[Identity]]


class AuthenticationRequired(ProxyError):
    pass


class CredentialsExpired(AuthenticationRequired):
    """The credentials are right but expired. Raise only after checking the secret, or it reveals the account exists."""


class CredentialsRevoked(AuthenticationRequired):
    """The credentials are right but revoked. Raise only after checking the secret, or it reveals the account exists."""


class Authenticator(ABC):
    """Turns client credentials into an identity. Where they are checked is up to the implementation.

    One instance serves all connections at once: keep no per-connection state on it,
    otherwise concurrent connections overwrite each other's data.
    """

    @abstractmethod
    async def authenticate(self, credentials: Credentials | None, session: Session, /) -> Identity:
        """Return the identity or raise `AuthenticationRequired`: `CredentialsRevoked`, `CredentialsExpired` if so.

        `session` tells who connects and where, e.g. to let in whitelisted client IPs without credentials.
        """


class AnonymousAuthenticator(Authenticator):
    """Lets everyone in. Only for local development."""

    async def authenticate(self, credentials: Credentials | None, session: Session, /) -> Identity:
        return ANONYMOUS


class DenyAllAuthenticator(Authenticator):
    """Lets no one in, e.g. clients without credentials when only accounts may connect."""

    async def authenticate(self, credentials: Credentials | None, session: Session, /) -> Identity:
        raise AuthenticationRequired()


_DENY_ALL_AUTHENTICATOR: Final[DenyAllAuthenticator] = DenyAllAuthenticator()


class DispatchAuthenticator(Authenticator):
    """Picks an authenticator by the credentials type, e.g. one for `BasicCredentials`, another for `BearerCredentials`.

    Credentials of a type not in `authenticators` are refused. Clients without credentials go to `without_credentials`,
    refused by default. Pass e.g. one that lets in trusted networks.
    """

    def __init__(
        self,
        authenticators: Mapping[type[Credentials], Authenticator],
        /,
        *,
        without_credentials: Authenticator = _DENY_ALL_AUTHENTICATOR,
    ) -> None:
        self._authenticators: dict[type[Credentials], Authenticator] = dict(authenticators)
        self._without_credentials: Authenticator = without_credentials

    async def authenticate(self, credentials: Credentials | None, session: Session, /) -> Identity:
        if credentials is None:
            return await self._without_credentials.authenticate(None, session)

        try:
            authenticator = self._authenticators[type(credentials)]
        except KeyError as err:
            raise AuthenticationRequired() from err

        return await authenticator.authenticate(credentials, session)
