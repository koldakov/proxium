from enum import StrEnum
from typing import Self


class LogLevel(StrEnum):
    """Names `logging` accepts as levels. Case-insensitive: `debug` works too."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    @classmethod
    def _missing_(cls, value: object) -> Self | None:
        return cls.__members__.get(value.upper()) if isinstance(value, str) else None
