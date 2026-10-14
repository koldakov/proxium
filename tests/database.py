"""The database tests run against: next to the one in DATABASE_URL, never it. Imports no proxium: used before it."""

from typing import Final

from sqlalchemy.engine import make_url

# Starts the name of every test database, checked before anything in it is wiped.
TEST_DATABASE_PREFIX: Final[str] = "test_"


def get_test_database_url(url: str, /) -> str:
    """`url` with the prefix before the database name, like Django's test database: `proxium` → `test_proxium`."""
    parsed = make_url(url)
    return parsed.set(database=f"{TEST_DATABASE_PREFIX}{parsed.database}").render_as_string(hide_password=False)
