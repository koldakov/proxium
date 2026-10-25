import asyncio
import re
from dataclasses import dataclass, replace
from http import HTTPMethod, HTTPStatus
from typing import TYPE_CHECKING, Final, Self

from proxium.proxy._stream import WrappedStream
from proxium.proxy._types import ProxyError

from ._body import CHUNKED
from ._head import CRLF, HEAD_END, Head, HTTPVersion

if TYPE_CHECKING:
    from proxium.proxy._stream import Stream

    from ._head import Headers


class BadResponse(ProxyError):
    """The target's response isn't valid HTTP/1.x."""


class ResponseIncomplete(BadResponse):
    """The target closed or broke the connection before the end of a response head."""


class NoResponse(ResponseIncomplete):
    """The target closed or broke the connection before any of the response."""


class ResponseHeadTooLarge(BadResponse):
    pass


class ResponseTimeout(ProxyError):
    """The target sent no response head while the relay waited, up to its idle timeout."""


# What every head starts with, checked before waiting for its line end.
STATUS_LINE_START: Final[bytes] = b"HTTP/1."
LINE_END: Final[bytes] = CRLF.encode()
# The reason may be empty or, with its space, missing (RFC 9112, 4).
STATUS_LINE: Final[re.Pattern[str]] = re.compile(r"(HTTP/1\.[01]) ([0-9]{3})(?: (.*))?")
# Statuses past it are invalid (RFC 9110, 15).
MAX_STATUS: Final[int] = 599
TOKEN: Final[re.Pattern[str]] = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
# A field value or a reason: visible ASCII, obs-text, SP and HTAB (RFC 9110, 5.5 and RFC 9112, 4).
FIELD_TEXT: Final[re.Pattern[str]] = re.compile(r"[\t\x20-\x7e\x80-\xff]*")
DIGITS: Final[re.Pattern[str]] = re.compile(r"[0-9]+")
OWS: Final[str] = " \t"
# Fields of the target-proxy hop, dropped like those `Connection` lists (RFC 9110, 7.6.1). Proxy-Authenticate and
# Proxy-Authentication-Info are for the proxy, the target's next hop (RFC 9110, 11.7).
RESPONSE_HOP_BY_HOP: Final[frozenset[str]] = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authentication-info",
        "proxy-connection",
        "te",
        "upgrade",
    },
)
# Frame the body, which passes as is: kept whatever `Connection` lists, without them the client would misread it.
FRAMING: Final[frozenset[str]] = frozenset({"content-length", "transfer-encoding"})
# Final statuses without a body, whatever the framing fields say (RFC 9112, 6.3).
BODILESS: Final[frozenset[int]] = frozenset({HTTPStatus.NO_CONTENT, HTTPStatus.NOT_MODIFIED})


def _parse_field(line: str, /) -> tuple[str, str]:
    """A field line of the target's response head as name and value. BadResponse if it isn't valid."""
    # Line folding, or whitespace before the first field: a 502 is one of the answers allowed (RFC 9112, 2.2 and 5.2).
    if line.startswith(tuple(OWS)):
        raise BadResponse("Line folding in the target's response head.")
    name, colon, value = line.partition(":")
    # A proxy removes whitespace before the colon (RFC 9112, 5.1).
    name = name.rstrip(OWS)
    if not colon or TOKEN.fullmatch(name) is None:
        raise BadResponse("Malformed field line in the target's response head.")
    value = value.strip(OWS)
    # NUL and other controls. CR and LF can't be there: the lines end with them.
    if FIELD_TEXT.fullmatch(value) is None:
        raise BadResponse(f"Control characters in {name} of the target's response.")
    return name, value


@dataclass(frozen=True, slots=True, kw_only=True)
class TargetResponseHead(Head):
    """A response head of the target. Unlike `ResponseHead`: any status of 100-599, e.g. 299, the reason as sent."""

    status: int
    reason: str
    version: HTTPVersion

    @property
    def start_line(self) -> str:
        return f"{self.version} {self.status} {self.reason}"

    @property
    def interim(self) -> bool:
        """A 1xx head: the final one comes after it."""
        return HTTPStatus.CONTINUE <= self.status < HTTPStatus.OK

    @classmethod
    def from_bytes(cls, raw: bytes, /) -> Self:
        """Parse a head of CRLF lines, as `ResponseStream` reads it. BadResponse if it isn't valid."""
        status_line, *lines = raw.removesuffix(HEAD_END).decode(cls._default_encoding).split(CRLF)
        match = STATUS_LINE.fullmatch(status_line)
        if match is None:
            raise BadResponse("Malformed status line in the target's response.")
        version, status, reason = match.group(1, 2, 3)
        if not HTTPStatus.CONTINUE <= int(status) <= MAX_STATUS:
            raise BadResponse(f"Status {status} of the target's response is out of range.")
        if reason is None:
            reason = ""
        if FIELD_TEXT.fullmatch(reason) is None:
            raise BadResponse("Control characters in the reason of the target's response.")
        headers = tuple(_parse_field(line) for line in lines)
        return cls(status=int(status), reason=reason, version=HTTPVersion(version), headers=headers)

    def to_client(self, *, proxy_status: str, client_version: HTTPVersion, request_method: str) -> Self:
        """The head as a client of `client_version` gets it in response to `request_method`: the proxy's own version
        (RFC 9110, 2.5), the target-proxy hop's fields dropped, the framing checked, the proxy's `Proxy-Status` member
        last (RFC 9209, 2). BadResponse if the framing is invalid.

        A final head says the connection closes: the proxy forwards one response per connection (RFC 9112, 9.6).
        """
        dropped = (RESPONSE_HOP_BY_HOP | set(self.members("connection"))) - FRAMING
        framed = self._framed_headers(client_version, request_method)
        headers = [(name, value) for name, value in framed if name.lower() not in dropped]
        if not self.interim:
            headers.append(("Connection", "close"))
        headers.append(("Proxy-Status", proxy_status))
        return replace(self, version=HTTPVersion.HTTP_1_1, headers=tuple(headers))

    def _bodiless(self, request_method: str, /) -> bool:
        """No body follows the head, whatever its framing fields say (RFC 9112, 6.3)."""
        return request_method == HTTPMethod.HEAD or self.interim or self.status in BODILESS

    def _framed_headers(self, client_version: HTTPVersion, request_method: str, /) -> Headers:
        """`headers` with the body's end made unambiguous for the client (RFC 9112, 6.3). BadResponse if it can't."""
        if any(name.lower() == "transfer-encoding" for name, _ in self.headers):
            if self.version == HTTPVersion.HTTP_1_0:
                raise BadResponse("Transfer-Encoding in an HTTP/1.0 response.")
            # It overrides Content-Length, which an intermediary removes (RFC 9112, 6.3).
            headers = tuple((name, value) for name, value in self.headers if name.lower() != "content-length")
            # The target got the client's version, see `RequestHead.to_origin`, and mustn't send it then (RFC 9112,
            # 6.1): the body passes as is, the client would read the chunks as the body.
            if client_version == HTTPVersion.HTTP_1_0:
                if not self._bodiless(request_method):
                    raise BadResponse("Transfer-Encoding in a response to an HTTP/1.0 request.")
                # No body to misread: the field just goes, the client doesn't know it.
                return tuple((name, value) for name, value in headers if name.lower() != "transfer-encoding")
            codings = self.members("transfer-encoding")
            # Without chunked last the body ends with the connection, valid for a response. Twice it's invalid.
            if not codings or CHUNKED in codings[:-1]:
                raise BadResponse("Malformed Transfer-Encoding in the target's response.")
            return headers

        values = [value for name, value in self.headers if name.lower() == "content-length"]
        if not values:
            return self.headers
        # A list of one length repeated is valid, sent as one field it's unambiguous (RFC 9110, 8.6).
        lengths = {part.strip(OWS) for value in values for part in value.split(",")}
        length = lengths.pop()
        if lengths or DIGITS.fullmatch(length) is None:
            raise BadResponse("Invalid or conflicting Content-Length in the target's response.")
        others = tuple((name, value) for name, value in self.headers if name.lower() != "content-length")
        return (*others, ("Content-Length", length))


class ResponseStream(WrappedStream):
    """The target of a forwarded request: its response heads go to the client as `TargetResponseHead.to_client` makes
    them, the bytes after the final one as is. A head comes from `read` whole, whatever `n`.

    A head that can't be read raises BadResponse, ending the relay: the exchange tells the client, see `check_read`.
    `client_version`: 1xx heads don't go to an HTTP/1.0 client (RFC 9110, 15.2), it waits for the final one. The relay
    doesn't see the skipped ones: they don't hold off its idle timeout, nor count as traffic.
    `max_interim_heads`: more 1xx heads before the final one are a BadResponse, e.g. a flood of skipped ones.
    The fields the proxy adds count as received traffic, quotas and speed limits included: the client gets them.
    """

    def __init__(  # noqa: PLR0913
        self,
        target: Stream,
        proxy_status: str,
        /,
        *,
        client_version: HTTPVersion,
        request_method: str,
        max_head_size: int,
        max_interim_heads: int,
    ) -> None:
        super().__init__(target)
        self._proxy_status: str = proxy_status
        self._client_version: HTTPVersion = client_version
        self._request_method: str = request_method
        self._max_head_size: int = max_head_size
        self._max_interim_heads: int = max_interim_heads
        self._interim_heads: int = 0
        # The target ended its response: all of it came, see `wait_ended`.
        self._ended: asyncio.Event = asyncio.Event()
        # Some head came, an interim one included: a break after it isn't `NoResponse`.
        self._head_came: bool = False
        # What the heads `read` returned make of the client. Only once the relay writes them there, see `sent`: a grant
        # may cut it in between, e.g. over a quota, and the client is still to be told why.
        self._continue_read: bool = False
        self._final_read: bool = False
        self._continued: bool = False
        self._final: bool = False
        self._error: BadResponse | None = None

    @property
    def continued(self) -> bool:
        """Whether the client got 100 Continue: it may send the body now."""
        return self._continued

    @property
    def final(self) -> bool:
        """Whether the client got the final head: the target's answer."""
        return self._final

    def sent(self) -> None:
        """The relay wrote what `read` returned last to the client: the heads in it are the client's now."""
        self._continued = self._continue_read
        self._final = self._final_read

    def check_read(self) -> None:
        """Raise the BadResponse `read` raised, if any."""
        if self._error is not None:
            raise self._error

    async def wait_ended(self) -> None:
        """Wait until `read` gives the end of the response."""
        await self._ended.wait()

    async def read(self, n: int | None = None, /) -> bytes:
        self.check_read()
        if self._final_read:
            data = await self._stream.read(n)
            if not data:
                self._ended.set()
            return data
        try:
            return await self._read_heads()
        except BadResponse as error:
            self._error = error
            raise

    def _incomplete(self, message: str, /) -> ResponseIncomplete:
        """`NoResponse` before any head came, `ResponseIncomplete` after."""
        return ResponseIncomplete(message) if self._head_came else NoResponse(message)

    async def _check_start(self) -> None:
        """Fail on bytes that can't start a head before waiting for their line end.

        Another protocol's bytes, e.g. a TLS server's alert, may have none: the proxy would wait until the target closes
        or the head is too large, and blame that.
        """
        try:
            start = await self._stream.peek(len(STATUS_LINE_START))
        except asyncio.IncompleteReadError as error:
            if not STATUS_LINE_START.startswith(error.partial):
                raise BadResponse("The target's response isn't HTTP/1.x.") from error
            # A few bytes of a status line aren't a response, as before a reset.
            raise self._incomplete("The target closed the connection before the response.") from error
        # A reset hides what came before it.
        except OSError as error:
            raise self._incomplete("The target's connection broke before the response.") from error
        if start != STATUS_LINE_START:
            raise BadResponse("The target's response isn't HTTP/1.x.")

    async def _read_line(self, limit: int, /) -> bytes:
        """One head line with its CRLF, which must end within `limit` bytes.

        Line by line: a head of bare LF lines fails on its first one, and its body's CRLFs can't pass for its end.
        """
        try:
            line = await self._stream.readuntil(b"\n", limit=limit)
        except asyncio.LimitOverrunError as error:
            raise ResponseHeadTooLarge("The target's response head is too large.") from error
        except asyncio.IncompleteReadError as error:
            raise ResponseIncomplete("The target closed the connection mid-head.") from error
        # A reset. The relay's idle timeout cancels the read instead, it doesn't end up here.
        except OSError as error:
            raise ResponseIncomplete("The target's connection broke mid-head.") from error
        # A lone CR or LF may end a line for the client and not for the proxy (RFC 9112, 2.2).
        if not line.endswith(LINE_END) or b"\r" in line.removesuffix(LINE_END):
            raise BadResponse("Bare CR or LF in the target's response head.")
        return line

    async def _read_head(self) -> TargetResponseHead:
        await self._check_start()
        # Grows in place: a head of many short lines isn't copied whole on each one.
        raw = bytearray()
        while not raw.endswith(HEAD_END):
            raw += await self._read_line(self._max_head_size - len(raw))
        self._head_came = True
        return TargetResponseHead.from_bytes(bytes(raw))

    async def _read_heads(self) -> bytes:
        """The next head for the client, the interim ones it doesn't get skipped."""
        while True:
            head = await self._read_head()
            # Upgrade isn't forwarded, see `RequestHead.to_origin`: the target can't switch (RFC 9110, 15.2.2).
            if head.status == HTTPStatus.SWITCHING_PROTOCOLS:
                raise BadResponse("The target switched protocols unasked.")
            if head.interim:
                self._interim_heads += 1
                if self._interim_heads > self._max_interim_heads:
                    raise BadResponse("Too many interim heads in the target's response.")
                # Before `to_client`: framing the client never sees can't fail the response.
                if self._client_version == HTTPVersion.HTTP_1_0:
                    continue
            forwarded = head.to_client(
                proxy_status=self._proxy_status,
                client_version=self._client_version,
                request_method=self._request_method,
            ).encode()
            if head.interim:
                self._continue_read = self._continue_read or head.status == HTTPStatus.CONTINUE
            else:
                self._final_read = True
            return forwarded
