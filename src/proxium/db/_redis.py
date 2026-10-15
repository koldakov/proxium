from redis.asyncio import Redis

from proxium.core import redis_settings


class RedisManager:
    """Owns the Redis client. One per process: use `redis_manager`, close it on shutdown."""

    def __init__(
        self,
        url: str,
        /,
        *,
        key_prefix: str = redis_settings.key_prefix,
        max_connections: int = redis_settings.pool_max_connections,
        password: str | None = None,
    ) -> None:
        self.key_prefix: str = key_prefix
        self.client: Redis = Redis.from_url(url, password=password, max_connections=max_connections)

    def key(self, name: str, /) -> str:
        """The key of `name` in Redis: every key goes through here, so the prefix keeps installations apart."""
        return f"{self.key_prefix}{name}"

    async def close(self) -> None:
        """Close the pooled connections. Safe to call twice, the client connects again on the next command."""
        await self.client.aclose()


# Connects lazily, on the first command inside the running loop.
redis_manager: RedisManager = RedisManager(
    str(redis_settings.url),
    password=None if redis_settings.password is None else redis_settings.password.get_secret_value(),
)
