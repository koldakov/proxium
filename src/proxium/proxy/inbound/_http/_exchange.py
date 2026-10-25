from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from proxium.proxy._exchange import Exchange
from proxium.proxy._types import Request

from ._body import RequestBody, RequestStream
from ._response import ResponseStream, ResponseTimeout

if TYPE_CHECKING:
    from proxium.proxy._stream import Stream
    from proxium.proxy._types import ProxyError

    from ._head import RequestHead


@dataclass(frozen=True, slots=True, kw_only=True)
class ForwardRequest(Request):
    """A forwarded request, parsed once by `handshake`: `head` as the target gets it, the `payload` it encodes to."""

    head: RequestHead = field(repr=False)
    # Follows the body as the client sends it: one per request, never equal to another.
    body: RequestBody = field(repr=False, compare=False)


class ForwardExchange(Exchange):
    """A forwarded request: the client's reads end with the request, see `RequestStream`, the target's response heads
    get the proxy's fields, see `ResponseStream`. Once the relay ends without a final response head, tells why.
    """

    def __init__(  # noqa: PLR0913
        self,
        client: Stream,
        target: Stream,
        request: ForwardRequest,
        proxy_status: str,
        /,
        *,
        max_head_size: int,
        max_interim_heads: int,
        max_dropped: int,
    ) -> None:
        self._body: RequestBody = request.body
        self._response: ResponseStream = ResponseStream(
            target,
            proxy_status,
            client_version=request.head.version,
            request_method=request.head.method,
            max_head_size=max_head_size,
            max_interim_heads=max_interim_heads,
        )
        # The client's writes are the response the relay passes on: a head counts once written, not once read.
        client_stream = RequestStream(
            client,
            self._body,
            on_write=self._response.sent,
            response_ended=self._response.wait_ended,
            max_dropped=max_dropped,
        )
        super().__init__(client_stream, self._response)

    def check_ended(self, *, expired: bool, error: ProxyError | None = None) -> None:
        """The BadResponse or BadRequest the relay ended on, or `error`, e.g. a grant's over a quota. On its idle
        timeout `RequestTimeout` if the client hasn't sent its whole request, `ResponseTimeout` if the target hasn't
        answered it.
        """
        # The client has the target's answer.
        if self._response.final:
            return
        self._response.check_read()
        self._body.check_followed()
        # Not a byte of a response went out: the client can still be told why.
        if error is not None:
            raise error
        # Ended otherwise, e.g. a side reset: without an answer, as a tunnel does.
        if not expired:
            return
        self._body.check_complete(continued=self._response.continued)
        raise ResponseTimeout("The target sent no response head in time.")
