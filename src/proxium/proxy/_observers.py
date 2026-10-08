import asyncio
import logging
from typing import TYPE_CHECKING, Final

from ._types import ProxyError

if TYPE_CHECKING:
    from ._types import Session

logger = logging.getLogger(__name__)

# Normal ways for a connection to end: refusals, resets, timeouts, a client gone mid-handshake.
EXPECTED_ERRORS: Final[tuple[type[Exception], ...]] = (ProxyError, OSError, asyncio.IncompleteReadError)


class Observer:
    """Session lifecycle hooks, e.g. for traffic accounting or metrics. Override what you need.

    One instance serves all connections at once: keep no per-connection state on it,
    otherwise concurrent connections overwrite each other's data.
    """

    async def on_open(self, session: Session, /) -> None:
        """The tunnel is established and relaying starts."""

    async def on_close(self, session: Session, /) -> None:
        """The client connection is closed. Called for every connection, even failed ones."""


class LoggingObserver(Observer):
    @staticmethod
    def _error_level(error: Exception, /) -> int:
        """INFO for a normal end, ERROR for a bug: the connection logs its traceback separately."""
        return logging.INFO if isinstance(error, EXPECTED_ERRORS) else logging.ERROR

    async def on_close(self, session: Session, /) -> None:
        if session.request is None:
            level = logging.INFO if session.error is None else self._error_level(session.error)
            logger.log(level, "%s rejected: %r", session.client, session.error)
            return

        logger.info(
            "%s %s -> %s sent=%d received=%d encrypted=%s",
            session.client,
            session.request.identity.subject,
            session.request.target,
            session.bytes_sent,
            session.bytes_received,
            session.encrypted,
        )
        # After the request was accepted, e.g. a policy cut the tunnel, a side reset it or it idled out.
        if session.error is not None:
            logger.log(
                self._error_level(session.error),
                "%s %s ended: %r",
                session.client,
                session.request.identity.subject,
                session.error,
            )
