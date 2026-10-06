from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
from typing import TYPE_CHECKING, Final

from ._encryption import EncryptionUnavailable
from ._relay import Relay
from ._stream import Stream
from ._types import ProxyError

if TYPE_CHECKING:
    import ssl
    from collections.abc import Awaitable, Callable

    from ._observers import Observer
    from ._policies import Grant
    from ._profiles import Profile
    from ._types import Credentials, Identity, Request, Session
    from .inbound import Inbound

logger = logging.getLogger(__name__)

# First byte of a TLS connection: the record type of its ClientHello.
TLS_HANDSHAKE: Final[bytes] = b"\x16"
# Record type, version, length of the payload.
TLS_RECORD_HEADER_SIZE: Final[int] = 5
# A fatal handshake_failure alert record, so a TLS client sees why it's refused instead of a bare reset.
TLS_HANDSHAKE_FAILURE: Final[bytes] = b"\x15\x03\x03\x00\x02\x02\x28"


class UnknownProtocol(ProxyError):
    pass


class Connection:
    """One client connection through a profile: unwrap TLS, detect the protocol, handshake, check, connect, relay."""

    def __init__(
        self,
        profile: Profile,
        client: socket.socket,
        session: Session,
        /,
    ) -> None:
        self._profile: Profile = profile
        self._client: socket.socket = client
        self._session: Session = session

    async def run(self) -> None:
        """Serve the connection to the end and close it. Never raises: every outcome ends up in `session.error`."""
        try:
            await self._process()
        except (OSError, asyncio.IncompleteReadError) as error:
            # The client went away or was too slow.
            self._session.error = error
        except Exception as error:
            self._session.error = error
            logger.exception("Unexpected error for %s", self._session.client)
        finally:
            await self._notify(lambda observer: observer.on_close(self._session))

    async def _wait_readable(self) -> None:
        loop = asyncio.get_running_loop()
        readable: asyncio.Future[None] = loop.create_future()

        def on_readable() -> None:
            # Off at once: the loop may poll again before this task wakes up.
            loop.remove_reader(self._client)
            readable.set_result(None)

        loop.add_reader(self._client, on_readable)
        try:
            await readable
        finally:
            # Cancelled, e.g. by the handshake deadline, before the socket got readable.
            loop.remove_reader(self._client)

    async def _peek(self) -> bytes:
        """The first byte, left in the socket: the TLS handshake needs the ClientHello whole."""
        await self._wait_readable()
        try:
            head = self._client.recv(1, socket.MSG_PEEK)
        except BlockingIOError:
            # Readiness may be spurious: wait again.
            return await self._peek()
        if not head:
            raise asyncio.IncompleteReadError(head, 1)
        return head

    async def _get_encryption_context(self) -> ssl.SSLContext | None:
        """The TLS context if the client starts with a TLS handshake, None if it speaks in the clear."""
        if await self._peek() != TLS_HANDSHAKE:
            return None
        if self._profile.encryption is None:
            raise EncryptionUnavailable("TLS isn't set up.")
        return await self._profile.encryption.context(self._session)

    @staticmethod
    async def _refuse_encryption(client: Stream, /) -> None:
        """Read the ClientHello record, then send the alert: closing with unread data resets it away."""
        header = await client.readexactly(TLS_RECORD_HEADER_SIZE)
        await client.readexactly(int.from_bytes(header[3:5]))
        client.write(TLS_HANDSHAKE_FAILURE)
        await client.drain()

    async def _serve(self, client: Stream, deadline: float, /) -> None:
        async with asyncio.timeout_at(deadline):
            head = await client.peek(1)
        inbound = next((inbound for inbound in self._profile.inbounds if inbound.detect(head)), None)
        if inbound is None:
            self._session.error = UnknownProtocol()
            return

        # Releases the grants however the connection ends, refused by a later policy included.
        async with contextlib.AsyncExitStack() as releases:
            try:
                request, grants, target = await self._open(inbound, client, deadline, releases)
            except ProxyError as error:
                self._session.error = error
                await inbound.reject(client, error)
                return

            self._session.request = request
            async with target:
                target.write(request.payload)
                self._session.bytes_sent += len(request.payload)
                await inbound.accept(client, request)
                await self._notify(lambda observer: observer.on_open(self._session))
                await Relay(
                    client,
                    target,
                    self._session,
                    idle_timeout=self._profile.timeouts.idle,
                    grants=grants,
                ).run()

    async def _process(self) -> None:
        # One deadline for the whole handshake, TLS and detection included.
        deadline = asyncio.get_running_loop().time() + self._profile.timeouts.handshake
        async with asyncio.timeout_at(deadline):
            try:
                context = await self._get_encryption_context()
            except EncryptionUnavailable as error:
                self._session.error = error
                async with await Stream.accept(self._client) as client:
                    await self._refuse_encryption(client)
                return
            except BaseException:
                # No stream owns the socket yet to close it.
                self._client.close()
                raise
            client = await Stream.accept(self._client, encryption=context)
        self._session.encrypted = context is not None
        async with client:
            await self._serve(client, deadline)

    async def _admit(self, request: Request, releases: contextlib.AsyncExitStack, /) -> list[Grant]:
        """Grants of every policy, each released by `releases`."""
        grants: list[Grant] = []
        for policy in self._profile.policies:
            grant = await policy.admit(request, self._session)
            releases.push_async_callback(grant.release)
            grants.append(grant)
        return grants

    async def _open(
        self,
        inbound: Inbound,
        client: Stream,
        deadline: float,
        releases: contextlib.AsyncExitStack,
        /,
    ) -> tuple[Request, list[Grant], Stream]:
        """Handshake, policies and the outgoing connection: every step that may refuse with a `ProxyError`."""
        async with asyncio.timeout_at(deadline):
            request = await inbound.handshake(client, self._authenticate)
        grants = await self._admit(request, releases)
        return request, grants, await self._profile.connector.connect(request, self._session)

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
