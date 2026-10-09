from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from proxium.db import Hash, UserModel

if TYPE_CHECKING:
    from faker import Faker


@pytest.fixture
def user_model(faker: Faker) -> UserModel:
    """A user that never reaches the database. The hash is random: only its value matters, not the password."""
    # Column defaults apply on insert only, so the session key is set here.
    return UserModel(
        id=faker.pyint(min_value=1),
        password=Hash(faker.sha256()),
        session_key=faker.uuid4(cast_to=None),
    )
