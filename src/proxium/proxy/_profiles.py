from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ._authenticators import Authenticator
    from ._connectors import Connector
    from ._observers import Observer
    from ._policies import Policy
    from ._types import Host
    from .inbound import Inbound


@dataclass(frozen=True, slots=True)
class Timeouts:
    handshake: float = 10.0
    idle: float = 300.0


@dataclass(frozen=True, slots=True)
class Profile:
    """How connections are handled: which protocols, auth, rules and way out."""

    inbounds: Sequence[Inbound]
    authenticator: Authenticator
    connector: Connector
    policies: Sequence[Policy] = ()
    observers: Sequence[Observer] = ()
    timeouts: Timeouts = field(default_factory=Timeouts)


@dataclass(frozen=True, slots=True)
class Listener:
    """Where to accept connections and with which profile. A host name listens on every address it resolves to."""

    host: Host
    ports: Sequence[int]
    profile: Profile
