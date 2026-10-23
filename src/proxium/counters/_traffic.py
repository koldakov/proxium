from __future__ import annotations

import itertools
import json
import logging
import secrets
from collections import defaultdict
from datetime import date
from typing import TYPE_CHECKING, Final

from pydantic import NonNegativeInt, TypeAdapter, ValidationError
from redis.exceptions import RedisError, ResponseError

from proxium.core import proxy_settings
from proxium.db import redis_manager
from proxium.observers import SharedTraffic, TrafficShare, TrafficShareUnavailable
from proxium.proxy import Usage

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from redis.asyncio.client import Pipeline

logger = logging.getLogger(__name__)

# The field of an owner's hash that changes on every write of its bytes. Processes are hex: never this name.
_VERSION_FIELD: Final[str] = "version"
# Of how the hashes are kept: a release that changes it changes this too. Processes of different formats, e.g. old and
# new during a restart without downtime, then don't see each other's bytes instead of failing on them.
_FORMAT: Final[str] = "v1"
# A process's field: bytes sent and received per UTC day. Raises `ValidationError` on anything else, e.g. garbage.
_FIELD_ADAPTER: Final[TypeAdapter[dict[date, tuple[NonNegativeInt, NonNegativeInt]]]] = TypeAdapter(
    dict[date, tuple[NonNegativeInt, NonNegativeInt]],
)


class UnsupportedRedisError(Exception):
    """Redis can't expire hash fields, which quotas need: Redis 7.4 or newer."""


class RedisTrafficShare(TrafficShare):
    """In Redis: a hash per owner, a field per process with its unwritten bytes as JSON, up to `chunk_size` owners per
    round trip. Fields are leased for `lease` seconds and renewed on every publish of the owner: a crashed process's
    bytes stop counting within `lease`, until then they may count twice, on the strict side. Once a process has no
    bytes of an owner, its field goes. The version is leased the same, renewed with the bytes of any process: once no
    process publishes any, it expires, and readers read the database once more.
    """

    def __init__(
        self,
        *,
        lease: float = proxy_settings.connection_lease,
        chunk_size: int = 1000,
    ) -> None:
        self._lease: float = lease
        self._lease_ms: int = max(1, round(lease * 1000))
        self._chunk_size: int = chunk_size
        # The field of this process: unique across the processes sharing Redis.
        self._process_id: str = secrets.token_hex(8)
        self._versions: itertools.count[int] = itertools.count()
        # Owners with a field of this process in Redis: once they have no bytes, it's deleted.
        self._published: set[str] = set()
        # Processes whose unreadable bytes were logged: once each, not every second.
        self._unreadable: set[str] = set()
        # Redis refusing HPEXPIRE on a publish was logged: once, not every second.
        self._unsupported_logged: bool = False

    @property
    def lease(self) -> float:
        return self._lease

    def _get_redis_key(self, owner: str, /) -> str:
        return redis_manager.key(f"quota:traffic:{_FORMAT}:{owner}")

    @staticmethod
    def _encode(days: Mapping[date, Usage], /) -> str:
        return json.dumps({day.isoformat(): [usage.sent, usage.received] for day, usage in days.items()})

    @staticmethod
    def _is_unknown_command(error: ResponseError, /) -> bool:
        """Whether Redis doesn't know a command: an old Redis. Others may pass, e.g. READONLY of a replica after a
        failover. Not by the start: a pipeline prefixes the error with the command's number.
        """
        return "unknown command" in str(error)

    async def check_support(self) -> None:
        """Raise `UnsupportedRedisError` if Redis can't expire hash fields, `TrafficShareUnavailable` if it doesn't
        answer or refuses it otherwise. By the command, not the version: forks tell versions of their own. On a key of
        no owner, which doesn't exist: nothing changes.
        """
        try:
            await redis_manager.client.hpexpire(self._get_redis_key("support"), self._lease_ms, _VERSION_FIELD)
        except ResponseError as err:
            if not self._is_unknown_command(err):
                raise TrafficShareUnavailable() from err
            raise UnsupportedRedisError(
                f"Redis refused HPEXPIRE, which quotas need, Redis 7.4 or newer is required: {err}",
            ) from err
        except RedisError as err:
            raise TrafficShareUnavailable() from err

    async def _ping(self) -> None:
        try:
            await redis_manager.client.ping()
        except RedisError as err:
            raise TrafficShareUnavailable() from err

    def _queue_owner(
        self,
        pipeline: Pipeline,
        owner: str,
        unwritten: Mapping[str, Mapping[date, Usage]],
        written: Collection[str],
        version: str,
        /,
    ) -> None:
        """Queue the commands of one owner's publish."""
        fields: dict[str, str] = {}
        if owner in unwritten:
            fields[self._process_id] = self._encode(unwritten[owner])
        if owner in written:
            fields[_VERSION_FIELD] = version
        # HSET then HPEXPIRE, not HSETEX: Redis 7.4 has no HSETEX. The transaction keeps them together.
        if fields:
            pipeline.hset(self._get_redis_key(owner), mapping=fields)
        # The version renewed with the bytes: it expires once no process publishes any of the owner, else every reader
        # would take the expiry for a write and read the sums again.
        leased = [*fields]
        if owner in unwritten and owner not in written:
            leased.append(_VERSION_FIELD)
        if leased:
            pipeline.hpexpire(self._get_redis_key(owner), self._lease_ms, *leased)
        if owner not in unwritten and owner in self._published:
            pipeline.hdel(self._get_redis_key(owner), self._process_id)

    async def publish(self, unwritten: Mapping[str, Mapping[date, Usage]], /, *, written: Collection[str]) -> None:
        written_owners = set(written)
        owners = list(unwritten.keys() | written_owners | self._published)
        if not owners:
            # Nothing to write, but whether Redis answers still tells if it's back.
            await self._ping()
            return

        # Unique across processes and publishes: a reader never takes a new version for the one it read.
        version = f"{self._process_id}:{next(self._versions)}"
        for chunk in itertools.batched(owners, self._chunk_size, strict=False):
            # A transaction: readers see the version and the bytes of an owner change together.
            pipeline = redis_manager.client.pipeline(transaction=True)
            for owner in chunk:
                self._queue_owner(pipeline, owner, unwritten, written_owners, version)
            # Added before: a publish cancelled once Redis took it would leave the field to expire, never deleted.
            # Removed after: deleted only once Redis took it.
            self._published.update(owner for owner in chunk if owner in unwritten)
            try:
                await pipeline.execute()
            except ResponseError as err:
                # E.g. an older Redis after a failover, or one that didn't answer `check_support` at the start: an
                # outage all the same, but the log says why. Here: the share may be down already, logged no more.
                if self._is_unknown_command(err) and not self._unsupported_logged:
                    self._unsupported_logged = True
                    logger.error("Redis refused HPEXPIRE, which quotas need, Redis 7.4 or newer is required: %s", err)
                raise TrafficShareUnavailable() from err
            except RedisError as err:
                raise TrafficShareUnavailable() from err

            self._published.difference_update(owner for owner in chunk if owner not in unwritten)

    def _decode(self, fields: Mapping[bytes, bytes], /) -> SharedTraffic:
        version: str | None = None
        processes: set[str] = set()
        days: defaultdict[date, list[int]] = defaultdict(lambda: [0, 0])
        for name, value in fields.items():
            # Not strict: a name or a version that isn't UTF-8 is garbage, not a reason to fail the read.
            field = name.decode(errors="backslashreplace")
            if field == _VERSION_FIELD:
                version = value.decode(errors="backslashreplace")
                continue
            if field == self._process_id:
                continue

            # Counted as a process even so: once it goes, readers read the sums again.
            processes.add(field)
            try:
                parsed = _FIELD_ADAPTER.validate_json(value)
            except ValidationError:
                # A bug, not an outage: the others' bytes still count, only these are missed. Logged once per process,
                # not on every read.
                if field not in self._unreadable:
                    self._unreadable.add(field)
                    logger.exception("Skipping unreadable traffic of process %s in Redis", field)
                continue
            for day, (sent, received) in parsed.items():
                counted = days[day]
                counted[0] += sent
                counted[1] += received

        return SharedTraffic(
            version=version,
            processes=frozenset(processes),
            days={day: Usage(sent=sent, received=received) for day, (sent, received) in days.items()},
        )

    async def read(self, owners: Collection[str], /) -> dict[str, SharedTraffic]:
        if not owners:
            # Nothing to read, but whether Redis answers still tells if it's back.
            await self._ping()
            return {}

        shared: dict[str, SharedTraffic] = {}
        for chunk in itertools.batched(owners, self._chunk_size, strict=False):
            pipeline = redis_manager.client.pipeline(transaction=False)
            for owner in chunk:
                pipeline.hgetall(self._get_redis_key(owner))
            try:
                replies = await pipeline.execute()
            except RedisError as err:
                raise TrafficShareUnavailable() from err

            for owner, fields in zip(chunk, replies, strict=True):
                shared[owner] = self._decode(fields)
        return shared
