from typing import Any
from urllib.parse import urlparse

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings


def _fix_postgres_url(url: str, /, *, scheme: str = "postgresql+asyncpg") -> str:
    return urlparse(url)._replace(scheme=scheme).geturl()


class Settings(BaseSettings):
    database_url: PostgresDsn

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
