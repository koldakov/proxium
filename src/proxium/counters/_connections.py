from __future__ import annotations

import asyncio
import contextlib
import itertools
import logging
import secrets
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Final

from redis.exceptions import RedisError

from proxium.core import proxy_settings
from proxium.db import redis_manager
from proxium.proxy import ConnectionCounter, ConnectionCountUnavailable, ConnectionLimitExceeded, Grant

if TYPE_CHECKING:
    from collections.abc import Hashable

    from redis.commands.core import AsyncScript

logger = logging.getLogger(__name__)

# KEYS[1]: the set of one limit key. ARGV: the limit, the connection, the lease in ms. Returns 1 if admitted.
# Scores are lease expiries in Redis time: the clocks of instances don't matter. The key lives as long as its
# longest lease, so a key nobody renews goes away.
_ADMIT: Final[str] = """
local now = redis.call('TIME')
local ms = tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ms)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1]) then
    return 0
end
redis.call('ZADD', KEYS[1], ms + tonumber(ARGV[3]), ARGV[2])
local last = redis.call('ZRANGE', KEYS[1], -1, -1, 'WITHSCORES')
redis.call('PEXPIREAT', KEYS[1], last[2])
return 1
"""

# KEYS[1]: the set of one limit key. ARGV: the lease in ms, then the connections to renew.
# Adds the missing ones too: admitted while Redis was down, or expired in an outage longer than a lease. One released
# while this runs may come back, it stops counting within a lease.
_RENEW: Final[str] = """
local now = redis.call('TIME')
local expiry = tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000) + tonumber(ARGV[1])
for i = 2, #ARGV do
    redis.call('ZADD', KEYS[1], 'GT', expiry, ARGV[i])
end
local last = redis.call('ZRANGE', KEYS[1], -1, -1, 'WITHSCORES')
if last[2] then
    redis.call('PEXPIREAT', KEYS[1], last[2])
end
"""


class RedisConnectionLeases:
    """Connections this process counts in Redis, each leased for `lease` seconds, up to `chunk_size` keys per round
    trip. Renewed so often that `spare_renewals` in a row may fail before a lease of an open connection expires:
    every third of `lease` by default. A crashed process renews nothing: its connections stop counting within
    `lease`.

    If Redis fails, it's left alone and checked every `probe_interval` seconds. Meanwhile connections are counted in
    this process alone for `outage_timeout` seconds, then new ones are refused, open ones go on. Once Redis answers,
    all open connections go there, those admitted meanwhile too.

    One per process, shared by its `RedisConnectionCounter`s. Call `start` in the running loop before serving and
    `close` after the server shut down.
    """

    def __init__(
        self,
        *,
        lease: float = proxy_settings.connection_lease,
        outage_timeout: float = proxy_settings.redis_outage_timeout,
        spare_renewals: int = 2,
        probe_interval: float = 1.0,
        chunk_size: int = 1000,
    ) -> None:
        if spare_renewals < 0:
            raise ValueError("Spare renewals can't be negative.")

        # The renewal on time plus the spare ones fit in a lease.
        self._renew_interval: float = lease / (spare_renewals + 1)
        self._outage_timeout: float = outage_timeout
        self._probe_interval: float = probe_interval
        self._lease_ms: int = max(1, round(lease * 1000))
        self._chunk_size: int = chunk_size
        # Connections are `{instance}:{n}`: unique across the instances sharing Redis.
        self._instance_id: str = secrets.token_hex(8)
        self._numbers: itertools.count[int] = itertools.count()
        # Open connections per Redis key: only keys with some stay, memory is bounded by them.
        self._open: defaultdict[str, set[str]] = defaultdict(set)
        self._admit_script: AsyncScript = redis_manager.client.register_script(_ADMIT)
        self._renew_script: AsyncScript = redis_manager.client.register_script(_RENEW)
        # When Redis failed, by `time.monotonic`. None while it answers.
        self._down_since: float | None = None
        self._closing: asyncio.Event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        """Stop renewing. Connections still open stop counting within a lease."""
        self._closing.set()
        if self._task is None:
            return

        # Cut a renewal in progress: nothing to keep, and a hanging Redis mustn't hold the shutdown.
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    def _mark_down(self, error: RedisError, /) -> None:
        if self._down_since is None:
            self._down_since = time.monotonic()
            logger.error(
                "Redis failed, connection limits are counted in this process alone for %s s: %s",
                self._outage_timeout,
                error,
            )

    def _admit_locally(self, key: str, /, *, limit: int) -> None:
        if self._down_since is not None and time.monotonic() - self._down_since > self._outage_timeout:
            raise ConnectionCountUnavailable()
        if len(self._open.get(key, ())) >= limit:
            raise ConnectionLimitExceeded()

    async def admit(self, key: str, /, *, limit: int) -> str:
        """Count a connection under `key` and return it. Raise `ConnectionLimitExceeded` if `limit` are open already,
        `ConnectionCountUnavailable` if Redis is down for longer than the outage timeout.
        """
        connection = f"{self._instance_id}:{next(self._numbers)}"
        # While Redis is down, it isn't asked: every connection would wait for its timeout.
        if self._down_since is None:
            try:
                admitted = await self._admit_script(keys=[key], args=[limit, connection, self._lease_ms])
            except RedisError as err:
                self._mark_down(err)
            else:
                if not admitted:
                    raise ConnectionLimitExceeded()

        if self._down_since is not None:
            self._admit_locally(key, limit=limit)

        # Cancelled before this, the connection isn't renewed: it stops counting within a lease.
        self._open[key].add(connection)
        return connection

    async def release(self, key: str, connection: str, /) -> None:
        """Stop counting `connection`. While Redis is down it stops within a lease: it's no longer renewed."""
        connections = self._open[key]
        connections.discard(connection)
        if not connections:
            del self._open[key]

        if self._down_since is not None:
            return

        try:
            await redis_manager.client.zrem(key, connection)
        except RedisError as err:
            self._mark_down(err)

    async def _renew(self) -> None:
        """Renew the leases of open connections. Raise `RedisError` if Redis fails."""
        # Copied first: connections open and close while the pipelines run.
        open_connections = [(key, tuple(connections)) for key, connections in self._open.items()]
        if not open_connections:
            # Nothing to renew, but whether Redis answers still tells if it's back.
            await redis_manager.client.ping()
            return

        for chunk in itertools.batched(open_connections, self._chunk_size, strict=False):
            pipeline = redis_manager.client.pipeline(transaction=False)
            for key, connections in chunk:
                await self._renew_script(keys=[key], args=[self._lease_ms, *connections], client=pipeline)
            await pipeline.execute()

    async def _sync(self) -> None:
        try:
            await self._renew()
        except RedisError as err:
            self._mark_down(err)
            return

        if self._down_since is not None:
            logger.info("Redis is back, connection limits are shared again")
            self._down_since = None

    async def _run(self) -> None:
        while not self._closing.is_set():
            interval = self._renew_interval if self._down_since is None else self._probe_interval
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._closing.wait(), interval)
            if self._closing.is_set():
                return

            # A bug mustn't end the loop: leases would expire, and limits stop counting without a word.
            try:
                await self._sync()
            except Exception:
                logger.exception("Can't renew connection leases, retrying in %s s", interval)


class _RedisConnectionGrant(Grant):
    def __init__(self, leases: RedisConnectionLeases, key: str, connection: str, /) -> None:
        self._leases: RedisConnectionLeases = leases
        self._key: str = key
        self._connection: str = connection

    async def release(self) -> None:
        await self._leases.release(self._key, self._connection)


class RedisConnectionCounter(ConnectionCounter):
    """In Redis: the instances sharing it count each other's connections, in one round trip per new connection.

    Keys of the limit live under `name`, e.g. its id: a limit edited under the same name keeps counting the
    connections open under it. Leases of open connections are renewed by `leases`.
    """

    def __init__(self, name: str, /, *, leases: RedisConnectionLeases) -> None:
        self._name: str = name
        self._leases: RedisConnectionLeases = leases

    def _get_redis_key(self, key: Hashable, /) -> str:
        # None, e.g. of the global scope, as empty: no other key of a scope is.
        return redis_manager.key(f"limit:connections:{self._name}:{'' if key is None else key}")

    async def acquire(self, key: Hashable, /, *, limit: int) -> Grant:
        redis_key = self._get_redis_key(key)
        connection = await self._leases.admit(redis_key, limit=limit)
        return _RedisConnectionGrant(self._leases, redis_key, connection)
