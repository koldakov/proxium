import os

from tests.database import get_test_database_url

# Before the fixtures import proxium: its settings and `session_manager` read the URL on import.
os.environ["DATABASE_URL"] = get_test_database_url(os.environ["DATABASE_URL"])

# Fixtures live in modules by topic, registered here: pytest takes `pytest_plugins` only from the root conftest.
# Acceptance steps too: pytest-bdd makes them fixtures.
pytest_plugins = [
    "tests.fixtures.database",
    "tests.fixtures.policies",
    "tests.fixtures.proxy",
    "tests.fixtures.runners",
    "tests.fixtures.users",
    "tests.fixtures.websites",
    "tests.acceptance.steps.proxy",
]
