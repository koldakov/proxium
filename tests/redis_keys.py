"""The Redis keys tests use: under their own prefix, never an instance's. Imports no proxium: used before it."""

from typing import Final

# Starts the key prefix of every test run, checked before any key is dropped.
TEST_KEY_PREFIX: Final[str] = "test_"


def get_test_key_prefix(prefix: str, /) -> str:
    """`prefix` for tests, like the test database: `proxium:` → `test_proxium:`."""
    return f"{TEST_KEY_PREFIX}{prefix}"
