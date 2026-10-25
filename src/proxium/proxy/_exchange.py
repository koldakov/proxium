from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._stream import Stream
    from ._types import ProxyError


class Exchange:
    """The client and the target as the relay copies between them. An inbound may wrap them, e.g. to rewrite what
    passes, and subclass this to answer the client once the relay ends, see `check_ended`.
    """

    def __init__(self, client: Stream, target: Stream, /) -> None:
        self.client: Stream = client
        self.target: Stream = target

    def check_ended(self, *, expired: bool, error: ProxyError | None = None) -> None:
        """Raise the error to reject the client with once the relay ended, `expired` on its idle timeout, on `error`
        if it ended on one, e.g. a grant cut it.

        Nothing by default: a tunnel's client waits for no answer of the proxy.
        """
