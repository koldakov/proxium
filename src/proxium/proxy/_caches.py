from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cachetools import TLRUCache

if TYPE_CHECKING:
    from collections.abc import Callable


class CacheMiss(Exception):
    """No value under the key: never set or expired."""


class Cache[V](ABC):
    """Where cached wrappers keep values between connections, e.g. in process memory or Redis.

    Keys are bytes, so any store takes them as is. A store outside the process also needs the values serialized:
    that's up to the implementation.
    """

    @abstractmethod
    async def get(self, key: bytes, /) -> V:
        """The value under `key` or raise `CacheMiss`."""

    @abstractmethod
    async def set(self, key: bytes, value: V, /, *, ttl: float) -> None:
        """Keep `value` under `key` for `ttl` seconds."""

    @abstractmethod
    async def clear(self) -> None:
        """Drop every value, e.g. when a shorter TTL must not wait out the longer one they were kept with."""


@dataclass(frozen=True, slots=True)
class _Entry[V]:
    value: V
    ttl: float


def _get_expiry(key: bytes, entry: _Entry[object], now: float, /) -> float:
    return now + entry.ttl


def _get_unit_size(value: object, /) -> int:
    return 1


class MemoryCache[V](Cache[V]):
    """In process memory, nothing is shared with other processes. Holds values of `getsizeof` up to `maxsize`
    in total, the least recently used go first. One per value by default, so `maxsize` counts values.
    """

    def _get_entry_size(self, entry: _Entry[V], /) -> int:
        return self._getsizeof(entry.value)

    def __init__(
        self,
        *,
        maxsize: int = 10_000,
        getsizeof: Callable[[V], int] = _get_unit_size,
    ) -> None:
        self._getsizeof: Callable[[V], int] = getsizeof
        self._entries: TLRUCache[bytes, _Entry[V]] = TLRUCache(
            maxsize=maxsize,
            ttu=_get_expiry,
            getsizeof=self._get_entry_size,
        )

    async def get(self, key: bytes, /) -> V:
        try:
            entry = self._entries[key]
        except KeyError as err:
            raise CacheMiss() from err

        return entry.value

    async def set(self, key: bytes, value: V, /, *, ttl: float) -> None:
        self._entries[key] = _Entry(value, ttl)

    async def clear(self) -> None:
        self._entries.clear()
