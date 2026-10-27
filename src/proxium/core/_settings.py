from typing import Annotated, Any, Final, Self
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from pydantic import (
    AnyUrl,
    EmailStr,
    Field,
    PostgresDsn,
    SecretStr,
    StringConstraints,
    UrlConstraints,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from ._listen_address import ListenAddress
from ._log_level import LogLevel

# Seconds between syncs of unwritten traffic for quotas between proxy instances, see `SharedTrafficTotals`. Here, next
# to the check of PROXY_CONNECTION_LEASE against it: one value for both.
TRAFFIC_SYNC_INTERVAL: Final[float] = 1.0


def _fix_postgres_url(url: str, /, *, scheme: str = "postgresql+asyncpg") -> str:
    return urlparse(url)._replace(scheme=scheme).geturl()


class ProxySettings(BaseSettings):
    listen: Annotated[
        list[ListenAddress],
        NoDecode,
        Field(
            default_factory=lambda: ListenAddress.parse_list("127.0.0.1:8080"),
        ),
    ]
    graceful_timeout: Annotated[
        float,
        Field(
            ge=0,
        ),
    ] = 30.0
    # Lets a new proxy listen on the same ports before the old one stops: restarts without downtime.
    reuse_port: bool = True
    # Connections waiting to be accepted per socket, beyond them a burst is dropped or stalls.
    # The kernel caps it at net.core.somaxconn.
    backlog: Annotated[
        int,
        Field(
            ge=1,
        ),
    ] = 1024
    log_level: LogLevel = LogLevel.INFO
    # Seconds between lookups of the settings edited in the admin: how soon new connections get the changes.
    settings_poll_interval: Annotated[
        float,
        Field(
            gt=0,
        ),
    ] = 5.0
    # Seconds between reports of this instance to the database, for the admin. Three missed in a row, it's unknown.
    heartbeat_interval: Annotated[
        float,
        Field(
            gt=0,
        ),
    ] = 30.0
    # Seconds an open connection stays counted in Redis without being renewed, renewed every third of it.
    # A crashed instance's connections stop counting after it, its unwritten traffic toward quotas too. That one is
    # renewed every TRAFFIC_SYNC_INTERVAL. At least three renewals and one slow Redis command, see `Settings`.
    connection_lease: Annotated[
        float,
        Field(
            gt=0,
        ),
    ] = 30.0
    # Seconds connection limits and quotas are counted in this process alone while Redis is down, then connections
    # under them are refused until it's back. At least REDIS_SOCKET_CONNECT_TIMEOUT + REDIS_SOCKET_TIMEOUT.
    redis_outage_timeout: Annotated[
        float,
        Field(
            gt=0,
        ),
    ] = 30.0
    # Seconds of a speed limit's rate an instance takes from Redis at once: each may go over the limit by one batch,
    # one round trip per batch while bytes flow.
    speed_batch: Annotated[
        float,
        Field(
            gt=0,
        ),
    ] = 0.1
    # Names the instance in `Proxy-Status` of HTTP responses. Printable ASCII: it goes in a header,
    # `HttpInbound` quotes it if needed. It checks the same itself, this one fails at settings load with the env name.
    name: Annotated[
        str,
        Field(
            pattern=r"^[\x20-\x7e]+$",
        ),
    ] = "proxium"

    model_config = SettingsConfigDict(
        env_prefix="proxy_",
    )

    # Plain: the parser does all the checks, pydantic doesn't need to know `ListenAddress` internals.
    @field_validator(
        "listen",
        mode="plain",
    )
    @classmethod
    def _parse_listen(cls, value: Any) -> list[ListenAddress]:
        if isinstance(value, str):
            return ListenAddress.parse_list(value)
        if isinstance(value, list) and all(isinstance(item, ListenAddress) for item in value):
            return value
        # ValueError, not TypeError: pydantic turns only the former into a ValidationError.
        raise ValueError(f"Expected a string like 127.0.0.1:8080, got {value!r}.")


proxy_settings = ProxySettings()


class DatabaseSettings(BaseSettings):
    """One set for every process: the proxy and the admin each get a pool of this size."""

    url: PostgresDsn
    echo: bool = False
    pool_size: Annotated[
        int,
        Field(
            ge=1,
        ),
    ] = 5
    # Connections opened on top of `pool_size` under load, closed once returned.
    pool_max_overflow: Annotated[
        int,
        Field(
            ge=0,
        ),
    ] = 10
    # Seconds to wait for a free connection before giving up.
    pool_timeout: Annotated[
        float,
        Field(
            gt=0,
        ),
    ] = 30.0
    # Seconds after which a connection is replaced, -1 keeps it forever.
    pool_recycle: Annotated[
        int,
        Field(
            ge=-1,
        ),
    ] = -1

    model_config = SettingsConfigDict(
        env_prefix="database_",
    )

    @field_validator(
        "url",
        mode="before",
    )
    @classmethod
    def _fix_url(cls, value: Any) -> Any:
        if isinstance(value, str):
            return _fix_postgres_url(value)
        return value


database_settings = DatabaseSettings()


class RedisSettings(BaseSettings):
    """Shared state of the instances, e.g. the migration lock. One for every process.

    The password is apart from the URL: easier to pass from a secret, e.g. in Kubernetes.
    """

    # unix:// too: the bundled Redis of the Docker image listens on a socket only, like its PostgreSQL.
    url: Annotated[
        AnyUrl,
        UrlConstraints(
            allowed_schemes=["redis", "rediss", "unix"],
        ),
    ]
    password: SecretStr | None = None
    # Starts every key: several installations can share one Redis.
    key_prefix: Annotated[
        str,
        Field(
            min_length=1,
        ),
    ] = "proxium:"
    # Connections of each process at most: a command beyond them fails, it doesn't wait.
    pool_max_connections: Annotated[
        int,
        Field(
            ge=1,
        ),
    ] = 100
    # Seconds to connect: an unreachable Redis fails after this instead of hanging.
    socket_connect_timeout: Annotated[
        float,
        Field(
            gt=0,
        ),
    ] = 2.0
    # Seconds to wait for an answer to a command: a Redis that hangs fails like one that's down.
    socket_timeout: Annotated[
        float,
        Field(
            gt=0,
        ),
    ] = 2.0

    model_config = SettingsConfigDict(
        env_prefix="redis_",
        # Errors would show the input, passwords included.
        hide_input_in_errors=True,
    )

    @model_validator(mode="after")
    def _check_password(self) -> Self:
        # Two passwords: which one wins would be a guess.
        if self.url.password is not None and self.password is not None:
            raise ValueError("The password is both in REDIS_URL and REDIS_PASSWORD, keep one.")
        return self


redis_settings = RedisSettings()


class EncryptionSettings(BaseSettings):
    """One for every process: the API encrypts secrets kept in the database, the proxy decrypts them."""

    # A Fernet key. Changing it makes stored secrets, e.g. private keys of TLS certificates, unreadable.
    key: SecretStr
    # Previous keys, comma-separated: they still decrypt, while `rotateencryptionkey` moves secrets to `key`.
    old_keys: Annotated[
        list[SecretStr],
        NoDecode,
        Field(
            default_factory=list,
        ),
    ]

    model_config = SettingsConfigDict(
        env_prefix="encryption_",
    )

    @staticmethod
    def _check_fernet_key(value: SecretStr, /) -> SecretStr:
        try:
            Fernet(value.get_secret_value())
        except ValueError:
            raise ValueError(
                "Not a Fernet key, generate one with "
                '`python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`.',
            ) from None
        return value

    @field_validator(
        "old_keys",
        mode="before",
    )
    @classmethod
    def _split_old_keys(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [key.strip() for key in value.split(",") if key.strip()]
        return value

    @field_validator(
        "key",
        mode="after",
    )
    @classmethod
    def _check_key(cls, value: SecretStr) -> SecretStr:
        return cls._check_fernet_key(value)

    @field_validator(
        "old_keys",
        mode="after",
    )
    @classmethod
    def _check_old_keys(cls, value: list[SecretStr]) -> list[SecretStr]:
        return [cls._check_fernet_key(key) for key in value]


encryption_settings = EncryptionSettings()


class ApiSettings(BaseSettings):
    # Signs user JWTs. Changing it logs everyone out. HS256 needs at least 32 bytes.
    secret_key: Annotated[
        SecretStr,
        Field(
            min_length=32,
        ),
    ]
    # Browser origins allowed to call the API, e.g. the frontend dev server.
    cors_origins: Annotated[
        list[str],
        NoDecode,
        Field(
            default_factory=list,
        ),
    ]
    # IPs in one outgoing IP pool at most, a /24 by default.
    outgoing_pool_max_size: Annotated[
        int,
        Field(
            ge=1,
        ),
    ] = 256
    # Policies assigned to one account or trusted network at most.
    # Up to 100, the largest page: the admin UI shows them all on one.
    policies_max_per_owner: Annotated[
        int,
        Field(
            ge=1,
            le=100,
        ),
    ] = 32
    # Global policies at most, turned off ones too: each applies to every connection of every client.
    # Up to 100, as per owner: an account's quotas, its own and global, then fit in one answer.
    global_policies_max: Annotated[
        int,
        Field(
            ge=1,
            le=100,
        ),
    ] = 32

    model_config = SettingsConfigDict(
        env_prefix="api_",
    )

    @field_validator(
        "cors_origins",
        mode="before",
    )
    @classmethod
    def _split_cors_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


api_settings = ApiSettings()


class SuperuserSettings(BaseSettings):
    """`proxium-manage createsuperuser` input. A flag wins over its variable.

    Validated on assignment too: the command checks flags and prompts against the same limits.
    """

    email: (
        Annotated[
            EmailStr,
            Field(
                max_length=255,
            ),
        ]
        | None
    ) = None
    # Read only with --no-input.
    password: (
        Annotated[
            SecretStr,
            Field(
                min_length=8,
                max_length=128,
            ),
        ]
        | None
    ) = None
    name: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True,
                max_length=150,
            ),
        ]
        | None
    ) = None
    surname: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True,
                max_length=150,
            ),
        ]
        | None
    ) = None

    model_config = SettingsConfigDict(
        env_prefix="superuser_",
        validate_assignment=True,
    )


superuser_settings = SuperuserSettings()


class Settings(BaseSettings):
    api: ApiSettings = api_settings
    database: DatabaseSettings = database_settings
    encryption: EncryptionSettings = encryption_settings
    proxy: ProxySettings = proxy_settings
    redis: RedisSettings = redis_settings
    superuser: SuperuserSettings = superuser_settings

    # Here: the two are in different groups. Checked on import, so a wrong pair stops every process at once.
    @model_validator(mode="after")
    def _check_redis_outage_timeout(self) -> Self:
        redis_timeout = self.redis.socket_connect_timeout + self.redis.socket_timeout
        if self.proxy.redis_outage_timeout < redis_timeout:
            raise ValueError(
                f"PROXY_REDIS_OUTAGE_TIMEOUT of {self.proxy.redis_outage_timeout} s is shorter than one Redis command "
                f"may take: {redis_timeout} s, REDIS_SOCKET_CONNECT_TIMEOUT + REDIS_SOCKET_TIMEOUT.",
            )
        return self

    # Unwritten traffic for quotas is renewed every TRAFFIC_SYNC_INTERVAL, and a renewal may wait for Redis as long as
    # one command may take: else traffic of a live instance expires between renewals, and quotas miss it. Three
    # renewals, as for connections. Not covered: a renewal waiting for the announce of a write, both
    # slow, or several slow chunks of over 1000 clients each. Rare, and short: quotas miss that traffic for a moment.
    @model_validator(mode="after")
    def _check_connection_lease(self) -> Self:
        renewals = 3 * TRAFFIC_SYNC_INTERVAL
        shortest = renewals + self.redis.socket_connect_timeout + self.redis.socket_timeout
        if self.proxy.connection_lease < shortest:
            raise ValueError(
                f"PROXY_CONNECTION_LEASE of {self.proxy.connection_lease} s is shorter than three renewals of quota "
                f"traffic and one Redis command: {shortest} s, {renewals} + REDIS_SOCKET_CONNECT_TIMEOUT + "
                "REDIS_SOCKET_TIMEOUT.",
            )
        return self


settings = Settings()
