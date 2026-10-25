from typing import TYPE_CHECKING, Final

import h11

from proxium.proxy._stream import WrappedStream
from proxium.proxy.inbound._base import BadRequest

from ._head import CRLF, HEAD_END, HTTPVersion

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from proxium.proxy._stream import Stream

    from ._head import RequestHead


class RequestTimeout(BadRequest):
    """The client sent no complete request while the relay waited, up to its idle timeout."""


# Start of the head `h11` frames the body by: it needs a request line and Host, the target gets the client's own.
FRAMING_HEAD_START: Final[str] = f"POST / HTTP/1.1{CRLF}Host: proxium"
CHUNKED: Final[str] = "chunked"
CONTINUE: Final[str] = "100-continue"


def _framing_head(head: RequestHead, /) -> bytes:
    """A head with just the fields that frame the body of `head` (RFC 9112, 6.3). BadRequest if they can't."""
    lengths = [f"Content-Length: {value}" for name, value in head.headers if name.lower() == "content-length"]
    if not any(name.lower() == "transfer-encoding" for name, _ in head.headers):
        return CRLF.join([FRAMING_HEAD_START, *lengths]).encode("latin-1") + HEAD_END
    # The target and the proxy would find different ends of the body, a way to smuggle in a request.
    if head.version == HTTPVersion.HTTP_1_0:
        raise BadRequest("Transfer-Encoding in an HTTP/1.0 request.")
    # Transfer-Encoding overrides Content-Length for the proxy, a target may still go by it: an error (RFC 9112, 6.3).
    if lengths:
        raise BadRequest("Both Transfer-Encoding and Content-Length in the request.")
    codings = head.members("transfer-encoding")
    # An empty field too: the target may count it as present or not.
    if not codings or codings[-1] != CHUNKED or CHUNKED in codings[:-1]:
        raise BadRequest("Transfer-Encoding of the request must end with chunked, applied once.")
    return CRLF.join([FRAMING_HEAD_START, f"Transfer-Encoding: {CHUNKED}"]).encode("latin-1") + HEAD_END


def _content_length(event: h11.Event | type[h11.NEED_DATA] | type[h11.PAUSED], /) -> int | None:
    """The length of the body the framing head's `event` tells, None for a chunked body."""
    # The head is whole: its event comes first.
    if not isinstance(event, h11.Request):
        raise TypeError(f"Expected the request head, got {event!r}.")
    if any(name == b"transfer-encoding" for name, _ in event.headers):
        return None
    # One field at most: the parser merges a repeated length and fails on conflicting ones.
    return next((int(value) for name, value in event.headers if name == b"content-length"), 0)


class RequestBody:
    """Follows the body of a forwarded request as the client sends it: where it ends and whether all of it came.

    BadRequest on creation if the head doesn't tell where the body ends.
    """

    def __init__(self, head: RequestHead, /) -> None:
        self._parser: h11.Connection = h11.Connection(h11.SERVER)
        # The client waits for 100 Continue before the body (RFC 9110, 10.1.1), unless it's HTTP/1.0: then it's ignored.
        self._expects_continue: bool = head.version != HTTPVersion.HTTP_1_0 and CONTINUE in head.members("expect")
        # A body the parser couldn't follow, e.g. a malformed chunk: told to the client, see `check_followed`.
        self._error: BadRequest | None = None
        self._parser.receive_data(_framing_head(head))
        # The parser checks the framing fields, only chunks go through it after: a Content-Length body is counted down,
        # its bytes aren't copied into events. None for a chunked body.
        self._remaining: int | None = _content_length(self._next_event())
        self._complete: bool = self._remaining == 0

    def feed(self, data: bytes, /) -> int:
        """Follow `data`, sent after what was fed before. How many of its bytes are the request's, the rest is after it.

        BadRequest if the body can't be followed: nothing more of it may go on, the target would find another end.
        """
        if self._error is not None:
            raise self._error
        if self._complete:
            return 0
        if self._remaining is not None:
            taken = min(len(data), self._remaining)
            self._remaining -= taken
            self._complete = not self._remaining
            return taken
        self._parser.receive_data(data)
        try:
            self._advance()
        except BadRequest as error:
            self._error = error
            raise
        if not self._complete:
            return len(data)
        # What the parser hasn't taken is after the end of the body, all of it in `data`: before, the body went on.
        trailing, _ = self._parser.trailing_data
        return len(data) - len(trailing)

    @property
    def complete(self) -> bool:
        """Whether all of the body came."""
        return self._complete

    def check_followed(self) -> None:
        """Raise the BadRequest `feed` raised, if any."""
        if self._error is not None:
            raise self._error

    def check_complete(self, *, continued: bool) -> None:
        """`RequestTimeout` if not all of the body came.

        `continued`: the client got 100 Continue. Before it, a client that sent `Expect: 100-continue` may wait with
        the body: nothing is raised then, it isn't at fault.
        """
        if self._expects_continue and not continued:
            return
        if not self._complete:
            raise RequestTimeout("The client sent no complete request.")

    def _next_event(self) -> h11.Event | type[h11.NEED_DATA] | type[h11.PAUSED]:
        try:
            return self._parser.next_event()
        except h11.RemoteProtocolError as error:
            raise BadRequest(f"Can't find the end of the request body: {error}") from error

    def _advance(self) -> None:
        """Take the events of what was fed, up to the end of the body: the parser's buffer stays small."""
        while not self._complete:
            event = self._next_event()
            if event is h11.NEED_DATA:
                return
            self._complete = isinstance(event, h11.EndOfMessage)


class RequestStream(WrappedStream):
    """The client of a forwarded request: its reads end with the request, `body` tells where.

    The target gets one request per connection, see `RequestHead.to_origin`: what the client sends after it, e.g. a
    pipelined request with its own `Proxy-Authorization`, mustn't reach the target. Up to `max_dropped` bytes of it are
    read on and dropped: the read ends once the client closes, so the target hears of it. Past them it isn't read, the
    buffers hold the client back until `response_ended` returns: dropped, it passes the grants by, a client could send
    without limits for as long as the response goes. The connection reads the rest off before closing, so the client's
    close doesn't reset the response away (RFC 9112, 9.6).
    `on_write` is called after each write: the relay writes only the target's response here, e.g. to tell a head sent.
    """

    def __init__(
        self,
        client: Stream,
        body: RequestBody,
        /,
        *,
        on_write: Callable[[], None],
        response_ended: Callable[[], Awaitable[None]],
        max_dropped: int,
    ) -> None:
        super().__init__(client)
        self._body: RequestBody = body
        self._on_write: Callable[[], None] = on_write
        self._response_ended: Callable[[], Awaitable[None]] = response_ended
        self._max_dropped: int = max_dropped
        self._dropped: int = 0

    async def read(self, n: int | None = None, /) -> bytes:
        while not self._body.complete:
            data = await self._stream.read(n)
            if not data:
                return b""
            # BadRequest on a body that can't be followed: ends the relay, the client is told.
            if taken := self._body.feed(data):
                self._dropped += len(data) - taken
                return data[:taken]
        while self._dropped < self._max_dropped:
            data = await self._stream.read(self._max_dropped - self._dropped)
            if not data:
                return b""
            self._dropped += len(data)
        await self._response_ended()
        return b""

    def write(self, data: bytes, /) -> None:
        super().write(data)
        self._on_write()
