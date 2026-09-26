from __future__ import annotations

import asyncio
import functools
import logging
from typing import TYPE_CHECKING

from ._connection import Connection
from ._stream import Stream
from ._types import Address, Session

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ._profiles import Listener, Profile

logger = logging.getLogger(__name__)


class ListenError(Exception):
    """A listener address can't be opened: it's taken, not local, doesn't resolve or has two profiles."""


class ProxyServer:
    """Opens and closes listeners, hands every accepted connection to a `Connection` with the listener's profile."""

    def __init__(self) -> None:
        self._servers: dict[Address, asyncio.Server] = {}
        self._profiles: dict[Address, Profile] = {}
        self._connections: set[asyncio.Task[None]] = set()

    async def update(self, listeners: Sequence[Listener], /) -> None:
        """Apply a new set of listeners, all or nothing.

        If any address can't be opened, the ones opened here are closed again and the old set stays as is.
        New connections get the new profiles, open ones keep theirs. Removed ports stop accepting.
        """
        profiles: dict[Address, Profile] = {}
        for listener in listeners:
            for port in listener.ports:
                address = Address(str(listener.host), port)
                if profiles.setdefault(address, listener.profile) is not listener.profile:
                    raise ListenError(f"{address} is claimed by two different profiles.")
        removed = self._servers.keys() - profiles.keys()
        added = profiles.keys() - self._servers.keys()

        previous = self._profiles
        # New sockets accept right away, so their profiles must be known before they open.
        self._profiles = previous | profiles
        opened: dict[Address, asyncio.Server] = {}
        for address in added:
            try:
                opened[address] = await self._listen(address)
            except ListenError:
                for server in opened.values():
                    server.close()
                self._profiles = previous
                raise

        self._servers |= opened
        for address in removed:
            self._servers.pop(address).close()
        self._profiles = profiles
        for address in sorted(added, key=str):
            logger.debug("Listening on %s", address)
        for address in sorted(removed, key=str):
            logger.debug("Stopped listening on %s", address)
        logger.info("Listening on %d addresses: %d added, %d removed", len(self._servers), len(added), len(removed))

    async def shutdown(self, *, timeout: float) -> None:
        """Stop accepting, give open connections `timeout` seconds to finish, then cut them."""
        for server in self._servers.values():
            server.close()
        self._servers.clear()

        if not self._connections:
            return
        logger.info("Waiting for %d connections to finish", len(self._connections))
        _, pending = await asyncio.wait(self._connections, timeout=timeout)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    async def _listen(self, address: Address, /) -> asyncio.Server:
        try:
            return await asyncio.start_server(
                functools.partial(self._accept, address),
                address.host,
                address.port,
            )
        except OSError as error:
            raise ListenError(f"Can't listen on {address}: {error}") from error

    def _accept(
        self,
        address: Address,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        # Keeps a reference to every connection task, so shutdown can wait for them.
        task = asyncio.create_task(self._handle(address, Stream(reader, writer)))
        self._connections.add(task)
        task.add_done_callback(self._connections.discard)

    async def _handle(self, address: Address, client: Stream, /) -> None:
        try:
            profile = self._profiles[address]
        except KeyError:
            # The listener was removed right after accepting.
            await client.close()
            return

        await Connection(profile, client, Session(client=client.peer, listener=address)).run()
