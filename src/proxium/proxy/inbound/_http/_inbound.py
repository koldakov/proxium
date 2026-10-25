import asyncio
import base64
import binascii
import re
from abc import ABC, abstractmethod
from email.utils import quote
from enum import StrEnum
from http import HTTPMethod, HTTPStatus
from http.client import HTTP_PORT
from typing import TYPE_CHECKING, ClassVar, Final
from urllib.parse import urlsplit

from proxium.proxy._authenticators import AuthenticationRequired, CredentialsExpired, CredentialsRevoked
from proxium.proxy._connectors import (
    ResolveTimeout,
    SourceUnavailable,
    TargetNotResolved,
    TargetRefused,
    TargetTimeout,
    TargetUnreachable,
)
from proxium.proxy._guards import ForbiddenAddress
from proxium.proxy._limits import ConnectionCountUnavailable, ConnectionLimitExceeded
from proxium.proxy._policies import Forbidden
from proxium.proxy._quotas import QuotaExceeded, UsageUnavailable
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

from ._body import RequestBody, RequestTimeout
from ._exchange import ForwardExchange, ForwardRequest
from ._head import (
    HEAD_END,
    RequestHead,
    ResponseHead,
)
from ._response import (
    BadResponse,
    NoResponse,
    ResponseHeadTooLarge,
    ResponseIncomplete,
    ResponseTimeout,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from proxium.proxy._authenticators import Authenticate
    from proxium.proxy._exchange import Exchange
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
    ConnectionLimitExceeded: HTTPStatus.TOO_MANY_REQUESTS,
    QuotaExceeded: HTTPStatus.TOO_MANY_REQUESTS,
    # Limits can't be checked now: worth retrying later, unlike an error of the proxy.
    ConnectionCountUnavailable: HTTPStatus.SERVICE_UNAVAILABLE,
    UsageUnavailable: HTTPStatus.SERVICE_UNAVAILABLE,
    TargetUnreachable: HTTPStatus.BAD_GATEWAY,
    TargetTimeout: HTTPStatus.GATEWAY_TIMEOUT,
    # The proxy's own setup is at fault, not the target.
    SourceUnavailable: HTTPStatus.INTERNAL_SERVER_ERROR,
    BadResponse: HTTPStatus.BAD_GATEWAY,
    ResponseTimeout: HTTPStatus.GATEWAY_TIMEOUT,
    RequestTimeout: HTTPStatus.REQUEST_TIMEOUT,
    ProxyError: HTTPStatus.INTERNAL_SERVER_ERROR,
}

# Reason phrases instead of the standard ones, looked up like statuses. Clients show them, e.g. `curl -v`.
DEFAULT_REASONS: Final[Mapping[type[ProxyError], str]] = {
    CredentialsExpired: "Credentials Expired",
    CredentialsRevoked: "Credentials Revoked",
    ConnectionLimitExceeded: "Too Many Connections",
    QuotaExceeded: "Quota Exceeded",
    ConnectionCountUnavailable: "Limits Unavailable",
    UsageUnavailable: "Limits Unavailable",
}

# Error types of `Proxy-Status` (RFC 9209, 2.3), looked up like statuses. With them a client tells a refusal of the
# proxy from a response of the target with the same status.
DEFAULT_PROXY_STATUS_ERRORS: Final[Mapping[type[ProxyError], str]] = {
    BadRequest: "http_request_error",
    AuthenticationRequired: "http_request_denied",
    Forbidden: "http_request_denied",
    ForbiddenAddress: "destination_ip_prohibited",
    ConnectionLimitExceeded: "http_request_denied",
    QuotaExceeded: "http_request_denied",
    ConnectionCountUnavailable: "proxy_internal_error",
    UsageUnavailable: "proxy_internal_error",
    TargetUnreachable: "destination_unavailable",
    TargetNotResolved: "dns_error",
    TargetRefused: "connection_refused",
    TargetTimeout: "connection_timeout",
    ResolveTimeout: "dns_timeout",
    SourceUnavailable: "proxy_configuration_error",
    BadResponse: "http_protocol_error",
    ResponseIncomplete: "http_response_incomplete",
    NoResponse: "connection_terminated",
    ResponseHeadTooLarge: "http_response_header_section_size",
    ResponseTimeout: "http_response_timeout",
    ProxyError: "proxy_internal_error",
}

# `Retry-After` seconds, looked up like statuses, none for errors not listed. Refusals start after an outage of
# PROXY_REDIS_OUTAGE_TIMEOUT: it's already long, retrying every second would only add load.
DEFAULT_RETRY_AFTERS: Final[Mapping[type[ProxyError], int]] = {
    ConnectionCountUnavailable: 5,
    UsageUnavailable: 5,
}

# `sf-token` and `sf-string` of RFC 8941, 3.3.4 and 3.3.3: what `Proxy-Status` names the proxy with. A token goes
# as is, anything else, e.g. an IP, in quotes.
SF_TOKEN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z*][!#$%&'*+\-.^_`|~:/0-9A-Za-z]*")
SF_STRING_CHARS: Final[re.Pattern[str]] = re.compile(r"[\x20-\x7e]+")


def _serialize_proxy_name(name: str, /) -> str:
    """`name` as `Proxy-Status` carries it: a token as is, else a quoted string. ValueError if it can't be either."""
    if SF_TOKEN.fullmatch(name) is not None:
        return name
    if SF_STRING_CHARS.fullmatch(name) is None:
        raise ValueError(
            f"Proxy name {name!r} can't go in a header: it must be non-empty printable ASCII, no line breaks.",
        )
    # The escapes of `sf-string` are those of a quoted string in email: `\\` and `\"`.
    return f'"{quote(name)}"'


def _closest[T](table: Mapping[type[ProxyError], T], error: ProxyError, /) -> T | None:
    """Value of the closest error class in `table`, None if none matches."""
    return next((table[cls] for cls in type(error).__mro__ if cls in table), None)


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

    def __init__(  # noqa: PLR0913
        self,
        *,
        max_head_size: int = 16 * 1024,
        # Responses often carry more than requests: cookies, CSP and the like.
        max_response_head_size: int = 64 * 1024,
        # 1xx heads before the final one: 100 Continue, 103 Early Hints, a few 102 Processing.
        max_interim_heads: int = 16,
        reject_nonstandard_methods: bool = False,
        auth: HttpAuth = DEFAULT_HTTP_AUTH,
        statuses: Mapping[type[ProxyError], HTTPStatus] = DEFAULT_STATUSES,
        reasons: Mapping[type[ProxyError], str] = DEFAULT_REASONS,
        proxy_status_errors: Mapping[type[ProxyError], str] = DEFAULT_PROXY_STATUS_ERRORS,
        retry_afters: Mapping[type[ProxyError], int] = DEFAULT_RETRY_AFTERS,
        proxy_name: str = "proxium",
    ) -> None:
        self._max_head_size: int = max_head_size
        self._max_response_head_size: int = max_response_head_size
        self._max_interim_heads: int = max_interim_heads
        # Off by default: a proxy normally leaves methods to the target.
        self._reject_nonstandard_methods: bool = reject_nonstandard_methods
        self._auth: HttpAuth = auth
        self._statuses: dict[type[ProxyError], HTTPStatus] = dict(statuses)
        self._reasons: dict[type[ProxyError], str] = dict(reasons)
        self._proxy_status_errors: dict[type[ProxyError], str] = dict(proxy_status_errors)
        self._retry_afters: dict[type[ProxyError], int] = dict(retry_afters)
        # Names the proxy in `Proxy-Status` of every response, forwarded ones too, e.g. a host name. Serialized once.
        self._proxy_name: str = _serialize_proxy_name(proxy_name)

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
            target = _parse_authority(head.target)
            identity = await authenticate(self._auth.credentials(head))
            return Request(
                protocol=HttpProtocol.CONNECT,
                target=target,
                identity=identity,
            )
        target = _parse_absolute_uri(head.target)
        origin_head = head.to_origin(drop=[self._auth.header])
        # Fails on a body whose end can't be found, before connecting.
        body = RequestBody(origin_head)
        identity = await authenticate(self._auth.credentials(head))
        return ForwardRequest(
            protocol=HttpProtocol.FORWARD,
            target=target,
            identity=identity,
            payload=origin_head.encode(),
            head=origin_head,
            body=body,
        )

    async def accept(self, stream: Stream, request: Request, /) -> None:
        if request.protocol == HttpProtocol.CONNECT:
            head = ResponseHead(
                status=HTTPStatus.OK,
                reason="Connection established",
                headers=(("Proxy-Status", self._proxy_name),),
            )
            stream.write(head.encode())
            await stream.drain()

    async def reject(self, stream: Stream, error: ProxyError, /) -> None:
        headers = [("Content-Length", "0"), ("Connection", "close"), ("Proxy-Status", self._proxy_status_for(error))]
        retry_after = _closest(self._retry_afters, error)
        if retry_after is not None:
            headers.append(("Retry-After", str(retry_after)))
        if isinstance(error, AuthenticationRequired):
            headers += self._auth.challenges()
        head = ResponseHead(
            status=self._status_for(error),
            reason=self._reason_for(error),
            headers=tuple(headers),
        )
        stream.write(head.encode())
        await stream.drain()

    def exchange(self, client: Stream, target: Stream, request: Request, /) -> Exchange:
        # A tunnel's bytes aren't HTTP for the proxy, its own 200 already carries `Proxy-Status`. Only `handshake` makes
        # a `ForwardRequest`: any other request is a tunnel, whatever its `protocol`.
        if not isinstance(request, ForwardRequest):
            return super().exchange(client, target, request)
        return ForwardExchange(
            client,
            target,
            request,
            self._proxy_name,
            max_head_size=self._max_response_head_size,
            max_interim_heads=self._max_interim_heads,
            # A pipelined request head or so: a client that sent one still gets seen closing.
            max_dropped=self._max_head_size,
        )

    def _status_for(self, error: ProxyError, /) -> HTTPStatus:
        """Status of the closest error class in the table, 500 if none matches."""
        status = _closest(self._statuses, error)
        return HTTPStatus.INTERNAL_SERVER_ERROR if status is None else status

    def _reason_for(self, error: ProxyError, /) -> str | None:
        """Reason of the closest error class in the table, None for the standard phrase."""
        return _closest(self._reasons, error)

    def _proxy_status_for(self, error: ProxyError, /) -> str:
        """`Proxy-Status` naming the proxy and the error type of the closest class, just the name if none matches."""
        error_type = _closest(self._proxy_status_errors, error)
        return self._proxy_name if error_type is None else f"{self._proxy_name}; error={error_type}"
