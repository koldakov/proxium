import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._types import Session

logger = logging.getLogger(__name__)


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
    async def on_close(self, session: Session, /) -> None:
        if session.request is None:
            logger.info("%s rejected: %r", session.client, session.error)
            return

        logger.info(
            "%s %s -> %s sent=%d received=%d",
            session.client,
            session.request.identity.subject,
            session.request.target,
            session.bytes_sent,
            session.bytes_received,
        )
