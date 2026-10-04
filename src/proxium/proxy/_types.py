from __future__ import annotations

import time
from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv6Address
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Mapping


class ProxyError(Exception):
    """Base for errors that an inbound reports to the client in its own protocol."""


# An IP address or a host name resolved when the socket is opened. Validating the name is up to the caller.
type Host = IPv4Address | IPv6Address | str


@dataclass(frozen=True, slots=True)
class Address:
    host: str
    port: int

    def __str__(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{host}:{self.port}"


class Credentials:
    """What a client presents to prove who it is."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class BasicCredentials(Credentials):
    username: str
    password: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class BearerCredentials(Credentials):
    token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class Identity:
    """Who uses the proxy, as decided by an authenticator."""

    subject: str
    claims: Mapping[str, Any] = field(default_factory=dict)


ANONYMOUS: Final[Identity] = Identity(subject="anonymous")


@dataclass(frozen=True, slots=True)
class Request:
    """Outcome of an inbound handshake: who wants to go where."""

    protocol: str
    target: Address
    identity: Identity
    # Sent to the target before relaying, e.g. a rewritten plain HTTP request head.
    payload: bytes = field(default=b"", repr=False)


@dataclass(slots=True)
class Session:
    """A single client connection, from accept to close."""

    client: Address | None
    # Where the client came in: the listener address as configured, e.g. 0.0.0.0, and the actual one of the socket.
    listener: Address
    local: Address | None
    # The client came over TLS.
    encrypted: bool = False
    request: Request | None = None
    error: Exception | None = None
    bytes_sent: int = 0
    bytes_received: int = 0
    started_at: float = field(default_factory=time.monotonic)
