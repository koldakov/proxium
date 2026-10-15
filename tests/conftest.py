import os

from tests.database import get_test_database_url
from tests.redis_keys import get_test_key_prefix

# Before the fixtures import proxium: its settings, `session_manager` and `redis_manager` read them on import.
os.environ["DATABASE_URL"] = get_test_database_url(os.environ["DATABASE_URL"])
os.environ["REDIS_KEY_PREFIX"] = get_test_key_prefix(os.environ["REDIS_KEY_PREFIX"])

# Fixtures live in modules by topic, registered here: pytest takes `pytest_plugins` only from the root conftest.
# Acceptance steps too: pytest-bdd makes them fixtures.
pytest_plugins = [
    "tests.fixtures.database",
    "tests.fixtures.management",
    "tests.fixtures.policies",
    "tests.fixtures.proxy",
    "tests.fixtures.runners",
    "tests.fixtures.users",
    "tests.fixtures.websites",
    "tests.acceptance.steps.management",
    "tests.acceptance.steps.proxy",
]
