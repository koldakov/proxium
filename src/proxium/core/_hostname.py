import re
from collections import UserString
from typing import Final

# RFC 1123: dot-separated labels of letters, digits and inner hyphens.
HOSTNAME: Final[re.Pattern[str]] = re.compile(
    r"(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*",
    re.I,
)


class Hostname(UserString):
    """A valid DNS host name, lowercased. Only created through validation, so a plain `str` never passes for it."""

    def __init__(self, value: str, /) -> None:
        if not HOSTNAME.fullmatch(value):
            raise ValueError(f"Invalid host name {value!r}.")
        super().__init__(value.lower())
