from __future__ import annotations

import asyncio
from argparse import Namespace
from io import StringIO
from typing import TYPE_CHECKING

import pytest
import uvloop
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from proxium.db import BaseModel, SettingsModel, session_manager
from proxium.management.commands import MigrateCommand
from tests.database import TEST_DATABASE_PREFIX

if TYPE_CHECKING:
    from collections.abc import Iterator


async def _execute_on_server(statement: str, /) -> None:
    """Run `statement` connected to the server's default database: one can't drop the database it's connected to."""
    # AUTOCOMMIT: CREATE and DROP DATABASE can't run in a transaction.
    engine = create_async_engine(
        session_manager.engine.url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


async def _clear_database() -> None:
    tables = ", ".join(
        session_manager.engine.dialect.identifier_preparer.quote(table.name)
        for table in BaseModel.metadata.sorted_tables
    )
    async with session_manager.session() as session:
        await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        # The only settings row, as the migration adds it: the proxy reads it and never inserts.
        await session.execute(insert(SettingsModel).values(id=1))
        await session.commit()


@pytest.fixture(scope="session")
def loop_runner() -> Iterator[asyncio.Runner]:
    """One event loop for the whole run, uvloop as in the proxy: `session_manager` keeps connections bound to it.

    pytest-bdd calls only sync steps, async ones run here, see `tests.acceptance.steps.async_step`.
    """
    with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
        yield runner


@pytest.fixture(scope="session")
def test_database(loop_runner: asyncio.Runner) -> Iterator[str]:
    """A new database with every migration, dropped after the run. One left by a crashed run is dropped first."""
    name = session_manager.engine.url.database
    # The last guard of real data: everything in this database gets wiped.
    if name is None or not name.startswith(TEST_DATABASE_PREFIX):
        raise RuntimeError(f"Refusing to run tests on {name!r}: its name doesn't start with {TEST_DATABASE_PREFIX!r}.")

    quoted = session_manager.engine.dialect.identifier_preparer.quote(name)
    # FORCE: connections left by a crashed run don't block the drop.
    loop_runner.run(_execute_on_server(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))
    loop_runner.run(_execute_on_server(f"CREATE DATABASE {quoted}"))
    MigrateCommand(stdout=StringIO()).handle(Namespace(revision="head", wait=0, lock=False))

    yield name

    loop_runner.run(session_manager.close())
    loop_runner.run(_execute_on_server(f"DROP DATABASE {quoted} WITH (FORCE)"))


@pytest.fixture
def database(loop_runner: asyncio.Runner, test_database: str) -> None:
    """The test database as the migrations leave it: every table empty, the settings at their defaults."""
    loop_runner.run(_clear_database())
