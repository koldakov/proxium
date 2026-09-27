from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from ._listen_address import ListenAddress
from ._log_level import LogLevel


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
    log_level: LogLevel = LogLevel.INFO

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


class ApiSettings(BaseSettings):
    # Signs user JWTs. Changing it logs everyone out. HS256 needs at least 32 bytes.
    secret_key: Annotated[
        SecretStr,
        Field(
            min_length=32,
        ),
    ]

    model_config = SettingsConfigDict(
        env_prefix="api_",
    )


api_settings = ApiSettings()


class Settings(BaseSettings):
    api: ApiSettings = api_settings
    database: DatabaseSettings = database_settings
    proxy: ProxySettings = proxy_settings


settings = Settings()
