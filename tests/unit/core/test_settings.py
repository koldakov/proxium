from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from proxium.core import RedisSettings

if TYPE_CHECKING:
    from faker import Faker


class TestRedisSettings:
    # Every field passed: the values from .env.test mustn't take part.

    def test_raises_when_password_in_url_and_apart(self, faker: Faker) -> None:
        # Arrange
        url = f"redis://:{faker.password(special_chars=False)}@{faker.hostname()}:6379/0"

        # Act & Assert
        with pytest.raises(ValidationError, match="keep one"):
            RedisSettings(url=url, password=faker.password())

    def test_raises_when_scheme_not_redis(self, faker: Faker) -> None:
        # Act & Assert
        with pytest.raises(ValidationError, match="URL scheme should be"):
            RedisSettings(url=faker.url(), password=None)
