from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from proxium.db import Hash, UserModel, session_manager

if TYPE_CHECKING:
    import asyncio

    from faker import Faker


async def _store(user: UserModel, /) -> None:
    async with session_manager.session() as session:
        session.add(user)
        await session.commit()


@pytest.fixture
def user_model(faker: Faker) -> UserModel:
    """A user that never reaches the database. The hash is random: only its value matters, not the password."""
    # Column defaults apply on insert only, so the session key is set here.
    return UserModel(
        id=faker.pyint(min_value=1),
        password=Hash(faker.sha256()),
        session_key=faker.uuid4(cast_to=None),
    )


@pytest.fixture
def stored_user(faker: Faker, loop_runner: asyncio.Runner, database: None) -> UserModel:
    """An active admin in the database, e.g. to create proxy accounts by."""
    user = UserModel(
        email=faker.email(),
        name=faker.first_name(),
        surname=faker.last_name(),
        password=Hash.create(faker.password()),
        is_active=True,
    )
    loop_runner.run(_store(user))
    return user
