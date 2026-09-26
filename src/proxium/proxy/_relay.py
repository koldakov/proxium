from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from ._stream import Stream
    from ._types import Session


class Relay:
    """Copies bytes both ways until both sides finish, one fails, or nothing moves for `idle_timeout`."""

    def __init__(
        self,
        client: Stream,
        target: Stream,
        session: Session,
        /,
        *,
        idle_timeout: float,
    ) -> None:
        self._client: Stream = client
        self._target: Stream = target
        self._session: Session = session
        self._idle_timeout: float = idle_timeout
        self._timeout: asyncio.Timeout | None = None
        # Relay is created inside a running loop, so it can be looked up once.
        self._loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()

    async def run(self) -> None:
        try:
            await self._pipe_both_ways()
        except* OSError:
            # Resets and idle timeouts are a normal way for a tunnel to end.
            pass

    async def _pipe_both_ways(self) -> None:
        async with asyncio.timeout(self._idle_timeout) as self._timeout, asyncio.TaskGroup() as group:
            group.create_task(self._pipe(self._client, self._target, self._on_sent))
            group.create_task(self._pipe(self._target, self._client, self._on_received))

    async def _pipe(
        self,
        source: Stream,
        sink: Stream,
        on_data: Callable[[int], None],
        /,
    ) -> None:
        while data := await source.read():
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
        if self._timeout is not None:
            self._timeout.reschedule(self._loop.time() + self._idle_timeout)
