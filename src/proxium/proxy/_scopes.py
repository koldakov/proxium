from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Hashable

    from ._types import Request, Session


class Scope(ABC):
    """What a limit is counted over: connections with the same key share it.

    One instance serves all connections at once: keep no per-connection state on it,
    otherwise concurrent connections overwrite each other's data.
    """

    @abstractmethod
    def key(self, request: Request, session: Session, /) -> Hashable:
        pass


class ConnectionScope(Scope):
    """Each connection on its own."""

    def key(self, request: Request, session: Session, /) -> Hashable:
        # Unique while the connection is open, and a limit holds its key no longer.
        return id(session)


class ClientIPScope(Scope):
    """Per client IP: connections from one address share the limit, whoever they authenticate as."""

    def key(self, request: Request, session: Session, /) -> Hashable:
        # Clients of unknown address, if the socket can't tell, share one key.
        return None if session.client is None else session.client.host


class TargetHostScope(Scope):
    """Per target host as the client named it: connections to one site share the limit, e.g. not to flood it."""

    def key(self, request: Request, session: Session, /) -> Hashable:
        return request.target.host.lower()


class IdentityScope(Scope):
    """Per identity: all connections of one account or trusted network share the limit."""

    def key(self, request: Request, session: Session, /) -> Hashable:
        return request.identity.subject


class GlobalScope(Scope):
    """The whole proxy: every connection shares the limit."""

    def key(self, request: Request, session: Session, /) -> Hashable:
        return None
