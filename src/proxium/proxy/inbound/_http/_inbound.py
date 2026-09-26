import asyncio
import base64
import binascii
from abc import ABC, abstractmethod
from enum import StrEnum
from http import HTTPMethod, HTTPStatus
from http.client import HTTP_PORT
from typing import TYPE_CHECKING, ClassVar, Final
from urllib.parse import urlsplit

from proxium.proxy._auth import AuthenticationRequired
from proxium.proxy._connectors import (
    TargetTimeout,
    TargetUnreachable,
)
from proxium.proxy._policies import Forbidden
from proxium.proxy._types import (
    Address,
    BasicCredentials,
    BearerCredentials,
    Credentials,
    ProxyError,
    Request,
)
from proxium.proxy.inbound._base import (
    BadRequest,
    Inbound,
)

from ._head import (
    HEAD_END,
    RequestHead,
    ResponseHead,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from proxium.proxy._auth import Authenticate
    from proxium.proxy._stream import Stream


class HttpProtocol(StrEnum):
    CONNECT = "http-connect"
    FORWARD = "http"


class UnsupportedMethod(BadRequest):
    pass


# Each error gets the status of its closest class here. Pass your own to `HttpInbound` for new errors.
DEFAULT_STATUSES: Final[Mapping[type[ProxyError], HTTPStatus]] = {
    BadRequest: HTTPStatus.BAD_REQUEST,
    UnsupportedMethod: HTTPStatus.NOT_IMPLEMENTED,
    AuthenticationRequired: HTTPStatus.PROXY_AUTHENTICATION_REQUIRED,
    Forbidden: HTTPStatus.FORBIDDEN,
    TargetUnreachable: HTTPStatus.BAD_GATEWAY,
    TargetTimeout: HTTPStatus.GATEWAY_TIMEOUT,
    ProxyError: HTTPStatus.INTERNAL_SERVER_ERROR,
}


class AuthScheme(ABC):
    """An authorization scheme, e.g. `Basic`. Add a subclass and pass it to `HttpInbound` to support another one.

    One instance serves all connections at once: keep no per-connection state on it,
    otherwise concurrent connections overwrite each other's data.
    """

    # Matched case-insensitively against the header.
    name: ClassVar[str]

    @abstractmethod
    def parse(self, param: str, /) -> Credentials:
        """Credentials from the header value after the scheme name. Raise `BadRequest` if it's malformed."""

    def challenge(self, realm: str, /) -> str:
        """`Proxy-Authenticate` value that asks the client for this scheme."""
        return f'{self.name.capitalize()} realm="{realm}"'


class BasicScheme(AuthScheme):
    """`Basic base64(username:password)`, RFC 7617."""

    name = "basic"

    def parse(self, param: str, /) -> Credentials:
        try:
            raw = base64.b64decode(param, validate=True)
        except binascii.Error as error:
            raise BadRequest("Basic credentials are not valid base64.") from error
        try:
            decoded = raw.decode()
        except UnicodeDecodeError as error:
            raise BadRequest("Basic credentials are not valid UTF-8.") from error
        username, _, password = decoded.partition(":")
        return BasicCredentials(username, password)


class BearerScheme(AuthScheme):
    """`Bearer token`, RFC 6750."""

    name = "bearer"

    def parse(self, param: str, /) -> Credentials:
        return BearerCredentials(param)


DEFAULT_AUTH_SCHEMES: Final[tuple[AuthScheme, ...]] = (
    BasicScheme(),
    BearerScheme(),
)


class HttpAuth:
    """How HTTP clients authenticate: accepted schemes, the header with credentials and the one with challenges.

    One instance serves all connections at once: keep no per-connection state on it,
    otherwise concurrent connections overwrite each other's data.
    """

    def __init__(
        self,
        *,
        schemes: Sequence[AuthScheme] = DEFAULT_AUTH_SCHEMES,
        header: str = "Proxy-Authorization",
        challenge_header: str = "Proxy-Authenticate",
        realm: str = "proxium",
    ) -> None:
        self._schemes: dict[str, AuthScheme] = {scheme.name.lower(): scheme for scheme in schemes}
        # Where clients put `<scheme> <credentials>`. Never forwarded to the target, whatever it's called.
        self._header: str = header
        # Sent with 407. Standard clients (browsers, curl) only understand the default one.
        self._challenge_header: str = challenge_header
        self._realm: str = realm

    @property
    def header(self) -> str:
        return self._header

    def credentials(self, head: RequestHead, /) -> Credentials | None:
        """Parse the auth header with the scheme it names, None if the client sent none."""
        value = head.get(self._header)
        if value is None:
            return None

        name, _, param = value.partition(" ")
        try:
            scheme = self._schemes[name.lower()]
        except KeyError:
            # No name in the message: a header without a scheme puts the bare secret there, and errors get logged.
            raise BadRequest("Unsupported authorization scheme.") from None

        return scheme.parse(param.strip())

    def challenges(self) -> list[tuple[str, str]]:
        """Headers that ask the client for credentials, one per accepted scheme."""
        return [(self._challenge_header, scheme.challenge(self._realm)) for scheme in self._schemes.values()]


DEFAULT_HTTP_AUTH: Final[HttpAuth] = HttpAuth()


def _parse_authority(authority: str, /) -> Address:
    """Parse a CONNECT target, e.g. `example.com:443` or `[::1]:443`."""
    try:
        parts = urlsplit(f"//{authority}")
    except ValueError as error:
        raise BadRequest(f"Malformed authority {authority!r}.") from error
    try:
        port = parts.port
    except ValueError as error:
        raise BadRequest(f"Invalid port in authority {authority!r}.") from error
    host = parts.hostname
    if not host or port is None:
        raise BadRequest(f"Authority {authority!r} needs a host and a port.")
    return Address(host, port)


def _parse_absolute_uri(uri: str, /) -> Address:
    """Parse a forward proxy target, e.g. `http://example.com/path`."""
    try:
        parts = urlsplit(uri)
    except ValueError as error:
        raise BadRequest(f"Malformed URI {uri!r}.") from error
    try:
        port = parts.port
    except ValueError as error:
        raise BadRequest(f"Invalid port in URI {uri!r}.") from error

    host = parts.hostname
    if parts.scheme != "http" or not host:
        raise BadRequest("Only absolute http:// URIs can be forwarded.")
    # No port in an http:// URI means the scheme's default (RFC 9110, 4.2.1).
    return Address(host, HTTP_PORT if port is None else port)


class HttpInbound(Inbound):
    """HTTP proxy: CONNECT tunnels and plain HTTP forwarding with absolute URIs."""

    def __init__(
        self,
        *,
        max_head_size: int = 16 * 1024,
        reject_nonstandard_methods: bool = False,
        auth: HttpAuth = DEFAULT_HTTP_AUTH,
        statuses: Mapping[type[ProxyError], HTTPStatus] = DEFAULT_STATUSES,
    ) -> None:
        self._max_head_size: int = max_head_size
        # Off by default: a proxy normally leaves methods to the target.
        self._reject_nonstandard_methods: bool = reject_nonstandard_methods
        self._auth: HttpAuth = auth
        self._statuses: dict[type[ProxyError], HTTPStatus] = dict(statuses)

    def detect(self, head: bytes, /) -> bool:
        # Every HTTP method starts with an uppercase letter.
        return head.isupper()

    async def handshake(self, stream: Stream, authenticate: Authenticate, /) -> Request:
        try:
            raw = await stream.readuntil(HEAD_END, limit=self._max_head_size)
        except asyncio.LimitOverrunError as error:
            raise BadRequest("Request head is too large.") from error

        head = RequestHead.from_bytes(raw)
        if self._reject_nonstandard_methods and head.method not in HTTPMethod:
            raise UnsupportedMethod(f"Unsupported method {head.method!r}.")

        # Cheap checks go before authentication, which may call an external service.
        if head.method == HTTPMethod.CONNECT:
            protocol = HttpProtocol.CONNECT
            target = _parse_authority(head.target)
            payload = b""
        else:
            protocol = HttpProtocol.FORWARD
            target = _parse_absolute_uri(head.target)
            payload = head.to_origin(drop=[self._auth.header]).encode()
        identity = await authenticate(self._auth.credentials(head))
        return Request(
            protocol=protocol,
            target=target,
            identity=identity,
            payload=payload,
        )

    async def accept(self, stream: Stream, request: Request, /) -> None:
        if request.protocol == HttpProtocol.CONNECT:
            stream.write(ResponseHead(status=HTTPStatus.OK, reason="Connection established").encode())
            await stream.drain()

    async def reject(self, stream: Stream, error: ProxyError, /) -> None:
        headers = [("Content-Length", "0"), ("Connection", "close")]
        if isinstance(error, AuthenticationRequired):
            headers += self._auth.challenges()
        stream.write(ResponseHead(status=self._status_for(error), headers=tuple(headers)).encode())
        await stream.drain()

    def _status_for(self, error: ProxyError, /) -> HTTPStatus:
        """Status of the closest error class in the table, 500 if none matches."""
        return next(
            (self._statuses[cls] for cls in type(error).__mro__ if cls in self._statuses),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )
