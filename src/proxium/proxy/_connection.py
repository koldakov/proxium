from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ._relay import Relay
from ._types import ProxyError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ._observers import Observer
    from ._profiles import Profile
    from ._stream import Stream
    from ._types import Credentials, Identity, Request, Session
    from .inbound import Inbound

logger = logging.getLogger(__name__)


class UnknownProtocol(ProxyError):
    pass


class Connection:
    """One client connection through a profile: detect the protocol, handshake, check, connect, relay."""

    def __init__(
        self,
        profile: Profile,
        client: Stream,
        session: Session,
        /,
    ) -> None:
        self._profile: Profile = profile
        self._client: Stream = client
        self._session: Session = session

    async def run(self) -> None:
        """Serve the connection to the end. Never raises: every outcome ends up in `session.error`."""
        try:
            await self._process()
        except (OSError, asyncio.IncompleteReadError) as error:
            # The client went away or was too slow.
            self._session.error = error
        except Exception as error:
            self._session.error = error
            logger.exception("Unexpected error for %s", self._session.client)
        finally:
            await self._client.close()
            await self._notify(lambda observer: observer.on_close(self._session))

    async def _process(self) -> None:
        # One deadline for the whole handshake, detection included.
        deadline = asyncio.get_running_loop().time() + self._profile.timeouts.handshake
        async with asyncio.timeout_at(deadline):
            head = await self._client.peek(1)
        inbound = next((inbound for inbound in self._profile.inbounds if inbound.detect(head)), None)
        if inbound is None:
            self._session.error = UnknownProtocol()
            return

        try:
            request, target = await self._open(inbound, deadline)
        except ProxyError as error:
            self._session.error = error
            await inbound.reject(self._client, error)
            return

        self._session.request = request
        async with target:
            target.write(request.payload)
            self._session.bytes_sent += len(request.payload)
            await inbound.accept(self._client, request)
            await self._notify(lambda observer: observer.on_open(self._session))
            await Relay(self._client, target, self._session, idle_timeout=self._profile.timeouts.idle).run()

    async def _open(self, inbound: Inbound, deadline: float, /) -> tuple[Request, Stream]:
        """Handshake, policy checks and the outgoing connection: every step that may refuse with a `ProxyError`."""
        async with asyncio.timeout_at(deadline):
            request = await inbound.handshake(self._client, self._authenticate)
        for policy in self._profile.policies:
            await policy.check(request, self._session)
        return request, await self._profile.connector.connect(request, self._session)

    async def _authenticate(self, credentials: Credentials | None, /) -> Identity:
        # Binds the session, so inbounds pass credentials only and stay unaware of it.
        return await self._profile.authenticator.authenticate(credentials, self._session)

    async def _notify(self, call: Callable[[Observer], Awaitable[None]], /) -> None:
        """Run a hook on every observer. A failing observer is logged and doesn't break the connection or the rest."""
        for observer in self._profile.observers:
            try:
                await call(observer)
            except Exception:
                logger.exception("Observer %r failed", observer)
