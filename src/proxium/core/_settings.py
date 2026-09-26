from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import Field, PostgresDsn, field_validator
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


class Settings(BaseSettings):
    database_url: PostgresDsn

    proxy: ProxySettings = proxy_settings

    @field_validator(
        "database_url",
        mode="before",
    )
    @classmethod
    def _fix_database_url(cls, value: Any) -> Any:
        if isinstance(value, str):
            return _fix_postgres_url(value)
        return value


settings = Settings()
