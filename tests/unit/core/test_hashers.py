from __future__ import annotations

from typing import TYPE_CHECKING

from proxium.core import hasher

if TYPE_CHECKING:
    from faker import Faker


class TestPBKDF2Hasher:
    def test_verify_returns_true_when_password_matches(self, faker: Faker) -> None:
        # Arrange
        password = faker.password()
        # Few iterations: the count is stored in the hash, the check is the same.
        encoded = hasher.encode(password, iterations=faker.pyint(min_value=1, max_value=1_000))

        # Act
        verified = hasher.verify(password, encoded)

        # Assert
        assert verified

    def test_verify_returns_false_when_password_differs(self, faker: Faker) -> None:
        # Arrange
        # Few iterations: the count is stored in the hash, the check is the same.
        encoded = hasher.encode(faker.unique.password(), iterations=faker.pyint(min_value=1, max_value=1_000))

        # Act
        verified = hasher.verify(faker.unique.password(), encoded)

        # Assert
        assert not verified
