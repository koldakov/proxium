from __future__ import annotations

from ipaddress import ip_address
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from proxium.db import OutgoingMode
from proxium.proxy import (
    SYSTEM_SOURCE,
    ListenerSourceSelector,
    SourceSelector,
    SourceUnavailable,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from proxium.proxy import IPAddress, Request, Session

# Identity claims the authenticators put and the selectors read. Plain strings, so an identity can be cached as is.
OUTGOING_MODE_CLAIM: Final[str] = "outgoing_mode"
OUTGOING_IP_CLAIM: Final[str] = "outgoing_ip"


def outgoing_claims(mode: OutgoingMode, /, *, ip: IPAddress | None = None) -> dict[str, Any]:
    """Claims for an identity that goes out the way its account or trusted network says.

    `ip` is the one picked from the pool for this connection, without it a `pool` identity can't go out.
    """
    claims: dict[str, Any] = {OUTGOING_MODE_CLAIM: mode.value}
    if ip is not None:
        claims[OUTGOING_IP_CLAIM] = str(ip)
    return claims


class PoolSourceSelector(SourceSelector):
    """The pool IP in the identity claims. The authenticator picks it at random from the pool, per connection."""

    def select(self, request: Request, session: Session, /) -> IPAddress | None:
        try:
            ip = request.identity.claims[OUTGOING_IP_CLAIM]
        except KeyError as err:
            raise SourceUnavailable(f"{request.identity.subject} has an empty outgoing IP pool.") from err

        return ip_address(ip)


# Every mode, as the admin describes it.
DEFAULT_SELECTORS: Final[Mapping[OutgoingMode, SourceSelector]] = MappingProxyType(
    {
        OutgoingMode.SYSTEM: SYSTEM_SOURCE,
        OutgoingMode.LISTENER: ListenerSourceSelector(),
        OutgoingMode.POOL: PoolSourceSelector(),
    },
)


class OutgoingSourceSelector(SourceSelector):
    """Picks the selector by the outgoing mode in the identity claims, as set on the account or trusted network.

    An identity without the mode, e.g. anonymous, is refused rather than sent out through a guess.
    """

    def __init__(
        self,
        selectors: Mapping[OutgoingMode, SourceSelector] = DEFAULT_SELECTORS,
        /,
    ) -> None:
        self._selectors: dict[OutgoingMode, SourceSelector] = dict(selectors)

    def select(self, request: Request, session: Session, /) -> IPAddress | None:
        try:
            mode = OutgoingMode(request.identity.claims[OUTGOING_MODE_CLAIM])
        except (KeyError, ValueError) as err:
            raise SourceUnavailable(f"{request.identity.subject} has no outgoing mode.") from err

        try:
            selector = self._selectors[mode]
        except KeyError as err:
            raise SourceUnavailable(f"No source selector for the {mode} outgoing mode.") from err

        return selector.select(request, session)
