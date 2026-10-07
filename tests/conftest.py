# Fixtures live in modules by topic, registered here: pytest takes `pytest_plugins` only from the root conftest.
pytest_plugins = [
    "tests.fixtures.policies",
    "tests.fixtures.proxy",
    "tests.fixtures.runners",
]
