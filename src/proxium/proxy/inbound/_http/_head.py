from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, Final, Self
from urllib.parse import urlsplit

from proxium.proxy.inbound._base import BadRequest

if TYPE_CHECKING:
    from collections.abc import Iterable
    from http import HTTPStatus

CRLF: Final[str] = "\r\n"
# Ends the head of every HTTP/1.x message.
HEAD_END: Final[bytes] = b"\r\n\r\n"
# Headers that belong to the client-proxy hop and must not reach the target.
# Transfer-Encoding is kept: the body is relayed as is.
HOP_BY_HOP: Final[frozenset[str]] = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "upgrade",
    },
)

type Headers = tuple[tuple[str, str], ...]


class HTTPVersion(StrEnum):
    HTTP_1_0 = "HTTP/1.0"
    HTTP_1_1 = "HTTP/1.1"


@dataclass(frozen=True, slots=True, kw_only=True)
class Head(ABC):
    """Start line and headers of an HTTP/1.x message."""

    headers: Headers = ()

    _default_encoding: ClassVar[str] = "latin-1"

    @property
    @abstractmethod
    def start_line(self) -> str: ...

    def get(self, name: str, /) -> str | None:
        """The first header with this name, case-insensitive."""
        name = name.lower()
        return next((value for key, value in self.headers if key.lower() == name), None)

    def encode(self) -> bytes:
        lines = [self.start_line, *(f"{name}: {value}" for name, value in self.headers)]
        return CRLF.join(lines).encode(self._default_encoding) + HEAD_END


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestHead(Head):
    # Not an enum: a proxy passes non-standard methods (WebDAV etc.) through.
    method: str
    target: str
    version: HTTPVersion

    @property
    def start_line(self) -> str:
        return f"{self.method} {self.target} {self.version}"

    @classmethod
    def from_bytes(cls, raw: bytes, /) -> Self:
        request_line, *lines = raw.removesuffix(HEAD_END).decode(cls._default_encoding).split(CRLF)
        # A lone CR or LF may end a line for the target and smuggle in a header (RFC 9112, 2.2).
        if any("\r" in line or "\n" in line for line in (request_line, *lines)):
            raise BadRequest("Bare CR or LF in request head.")
        try:
            method, target, version = request_line.split(" ")
        except ValueError as error:
            raise BadRequest("Malformed request line.") from error
        try:
            http_version = HTTPVersion(version)
        except ValueError as error:
            raise BadRequest(f"Unsupported version {version!r}.") from error

        headers = []
        for line in lines:
            name, colon, value = line.partition(":")
            if not colon or not name or name != name.strip():
                raise BadRequest("Malformed header.")
            headers.append((name, value.strip()))
        return cls(method=method, target=target, version=http_version, headers=tuple(headers))

    def to_origin(self, *, drop: Iterable[str] = ()) -> Self:
        """Turn a proxy request into an origin request.

        The target becomes path-only, Host comes from the absolute URI (RFC 9112, 3.2.2),
        hop-by-hop headers and the `drop` ones are dropped.
        """
        parts = urlsplit(self.target)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        host = parts.netloc.rpartition("@")[2]

        listed = {name.strip().lower() for name in (self.get("connection") or "").split(",")}
        dropped = HOP_BY_HOP | listed | {"host"} | {name.lower() for name in drop}
        headers = (
            ("Host", host),
            *((name, value) for name, value in self.headers if name.lower() not in dropped),
            # One request per connection keeps relaying byte-level, without parsing bodies.
            ("Connection", "close"),
        )
        return replace(self, target=path, headers=headers)


@dataclass(frozen=True, slots=True, kw_only=True)
class ResponseHead(Head):
    status: HTTPStatus
    # Overrides the standard phrase, e.g. "Connection established" for CONNECT.
    reason: str | None = None
    version: HTTPVersion = HTTPVersion.HTTP_1_1

    @property
    def start_line(self) -> str:
        return f"{self.version} {self.status.value} {self.reason or self.status.phrase}"
