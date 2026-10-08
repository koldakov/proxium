from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ._types import ProxyError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from ._policies import Grant
    from ._stream import Stream
    from ._types import Session


class Relay:
    """Copies bytes both ways until both sides finish, one fails, or nothing moves for `idle_timeout`.

    Every chunk passes the `grants` first: they may hold it back to slow the tunnel down, or cut the tunnel.
    """

    def __init__(
        self,
        client: Stream,
        target: Stream,
        session: Session,
        /,
        *,
        idle_timeout: float,
        grants: Sequence[Grant] = (),
    ) -> None:
        self._client: Stream = client
        self._target: Stream = target
        self._session: Session = session
        self._idle_timeout: float = idle_timeout
        self._grants: tuple[Grant, ...] = tuple(grants)
        # Directions whose data the grants hold back right now.
        self._held: int = 0
        # Set by `run` for its duration, see `timeout`.
        self._timeout: asyncio.Timeout | None = None
        # Relay is created inside a running loop, so it can be looked up once.
        self._loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()

    @property
    def timeout(self) -> asyncio.Timeout:
        """The idle timeout of the running tunnel."""
        if self._timeout is None:
            raise RuntimeError("The relay isn't running.")
        return self._timeout

    async def run(self) -> None:
        try:
            await self._pipe_both_ways()
        except* OSError as group:
            # Resets and idle timeouts are a normal way for a tunnel to end, kept to show how it ended.
            self._session.error = group.exceptions[0]
        except* ProxyError as group:
            # A grant cut the tunnel, e.g. over a quota: the reason ends up in the session, as a refusal's does.
            self._session.error = group.exceptions[0]

    async def _check_sent(self, n: int, /) -> None:
        for grant in self._grants:
            await grant.on_sent(n)

    async def _check_received(self, n: int, /) -> None:
        for grant in self._grants:
            await grant.on_received(n)

    async def _hold(self, check: Callable[[int], Awaitable[None]], n: int, /) -> None:
        """Let the grants check `n` bytes. Waiting for them isn't idleness: the idle clock stops meanwhile."""
        self._held += 1
        self._touch()
        try:
            await check(n)
        finally:
            self._held -= 1
        self._touch()

    async def _pipe_both_ways(self) -> None:
        async with asyncio.timeout(self._idle_timeout) as timeout, asyncio.TaskGroup() as group:
            self._timeout = timeout
            group.create_task(self._pipe(self._client, self._target, self._check_sent, self._on_sent))
            group.create_task(self._pipe(self._target, self._client, self._check_received, self._on_received))

    async def _pipe(
        self,
        source: Stream,
        sink: Stream,
        check: Callable[[int], Awaitable[None]],
        on_data: Callable[[int], None],
        /,
    ) -> None:
        while data := await source.read():
            await self._hold(check, len(data))
            sink.write(data)
            await sink.drain()
            on_data(len(data))
        sink.write_eof()

    def _on_sent(self, n: int, /) -> None:
        self._session.bytes_sent += n
        self._touch()

    def _on_received(self, n: int, /) -> None:
        self._session.bytes_received += n
        self._touch()

    def _touch(self) -> None:
        # No deadline while the grants hold data back: it restarts when they let go.
        when = None if self._held else self._loop.time() + self._idle_timeout
        self.timeout.reschedule(when)
