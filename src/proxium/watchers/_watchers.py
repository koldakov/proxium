from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence


class Watcher(Protocol):
    async def load(self) -> None:
        """Read and apply the current state, raising if it can't: the proxy must not start on guesses."""

    def start(self) -> None:
        """Start following changes in the running loop, after `load`."""

    async def close(self) -> None:
        """Stop following changes. One being applied finishes."""


class Watchers:
    """Watchers run together: loaded in the given order, then started, closed in the given order too."""

    def __init__(self, watchers: Sequence[Watcher], /) -> None:
        self._watchers: tuple[Watcher, ...] = tuple(watchers)

    async def start(self) -> None:
        # All loaded first: none follows changes while another may still fail to start.
        for watcher in self._watchers:
            await watcher.load()
        for watcher in self._watchers:
            watcher.start()

    async def close(self) -> None:
        for watcher in self._watchers:
            await watcher.close()
