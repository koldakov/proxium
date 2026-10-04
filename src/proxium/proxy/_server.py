from __future__ import annotations

import asyncio
import logging
import socket
from typing import TYPE_CHECKING, Any, ClassVar

from ._connection import Connection
from ._types import Address, Session

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ._profiles import Listener, Profile

logger = logging.getLogger(__name__)


class ListenError(Exception):
    """A listener address can't be opened: it's taken, not local, doesn't resolve or has two profiles."""


class ProxyServer:
    """Opens and closes listeners, hands every accepted connection to a `Connection` with the listener's profile.

    Accepts on its own sockets instead of `asyncio.start_server`: a connection must reach `Connection` untouched,
    since a TLS handshake needs the bytes a stream would have already read.
    """

    backlog: ClassVar[int] = 100
    # Seconds to wait after a failed accept, e.g. out of file descriptors, instead of failing again at once.
    accept_retry_delay: ClassVar[float] = 1.0

    def __init__(self) -> None:
        # Accept loops of every address, one per socket it resolves to.
        self._servers: dict[Address, list[asyncio.Task[None]]] = {}
        self._profiles: dict[Address, Profile] = {}
        self._connections: set[asyncio.Task[None]] = set()

    @staticmethod
    def _stop(tasks: list[asyncio.Task[None]], /) -> None:
        for task in tasks:
            task.cancel()

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
        opened: dict[Address, list[asyncio.Task[None]]] = {}
        for address in added:
            try:
                opened[address] = await self._listen(address)
            except ListenError:
                for tasks in opened.values():
                    self._stop(tasks)
                self._profiles = previous
                raise

        self._servers |= opened
        for address in removed:
            self._stop(self._servers.pop(address))
        self._profiles = profiles
        for address in sorted(added, key=str):
            logger.debug("Listening on %s", address)
        for address in sorted(removed, key=str):
            logger.debug("Stopped listening on %s", address)
        logger.info("Listening on %d addresses: %d added, %d removed", len(self._servers), len(added), len(removed))

    async def shutdown(self, *, timeout: float) -> None:
        """Stop accepting, give open connections `timeout` seconds to finish, then cut them."""
        for tasks in self._servers.values():
            self._stop(tasks)
        self._servers.clear()

        if not self._connections:
            return
        logger.info("Waiting for %d connections to finish", len(self._connections))
        _, pending = await asyncio.wait(self._connections, timeout=timeout)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    @classmethod
    def _bind(cls, sock: socket.socket, sockaddr: Any, /) -> None:
        # Restarts don't wait for old connections in TIME_WAIT to free the port.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if sock.family == socket.AF_INET6:
            # [::] takes IPv6 only, so 0.0.0.0 on the same port can be listened on too.
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        sock.bind(sockaddr)
        sock.listen(cls.backlog)
        sock.setblocking(False)

    @classmethod
    def _open_socket(cls, family: int, kind: int, proto: int, sockaddr: Any, /) -> socket.socket:
        sock = socket.socket(family, kind, proto)
        try:
            cls._bind(sock, sockaddr)
        except OSError:
            sock.close()
            raise
        return sock

    def _spawn(self, address: Address, client: socket.socket, peer: Any, /) -> None:
        client.setblocking(False)
        # Keeps a reference to every connection task, so shutdown can wait for them.
        task = asyncio.create_task(self._handle(address, client, peer))
        self._connections.add(task)
        task.add_done_callback(self._connections.discard)

    async def _accept_forever(self, address: Address, sock: socket.socket, /) -> None:
        loop = asyncio.get_running_loop()
        while True:
            try:
                client, peer = await loop.sock_accept(sock)
            except ConnectionError:
                # The client gave up before it was accepted.
                continue
            except OSError as error:
                logger.error("Can't accept on %s, retrying in %ss: %s", address, self.accept_retry_delay, error)
                await asyncio.sleep(self.accept_retry_delay)
                continue
            self._spawn(address, client, peer)

    def _start_accepting(self, address: Address, sock: socket.socket, /) -> asyncio.Task[None]:
        task = asyncio.create_task(self._accept_forever(address, sock))
        # Closed once nothing waits on it, even if the task is cancelled before it starts.
        task.add_done_callback(lambda _: sock.close())
        return task

    async def _listen(self, address: Address, /) -> list[asyncio.Task[None]]:
        """Open a socket for every address the host resolves to and start accepting on them."""
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(address.host, address.port, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE)
        except OSError as error:
            raise ListenError(f"Can't listen on {address}: {error}") from error

        sockets: list[socket.socket] = []
        # A host may resolve to the same address twice.
        for family, kind, proto, _, sockaddr in dict.fromkeys(infos):
            try:
                sockets.append(self._open_socket(family, kind, proto, sockaddr))
            except OSError as error:
                for sock in sockets:
                    sock.close()
                raise ListenError(f"Can't listen on {address}: {error}") from error
        return [self._start_accepting(address, sock) for sock in sockets]

    @staticmethod
    def _local(sock: socket.socket, /) -> Address | None:
        """This side's address, None if the socket was gone before it could be read."""
        try:
            host, port, *_ = sock.getsockname()
        except OSError:
            return None
        return Address(host, port)

    async def _handle(self, address: Address, client: socket.socket, peer: Any, /) -> None:
        try:
            profile = self._profiles[address]
        except KeyError:
            # The listener was removed right after accepting.
            client.close()
            return

        host, port, *_ = peer
        session = Session(
            client=Address(host, port),
            listener=address,
            local=self._local(client),
        )
        await Connection(profile, client, session).run()
