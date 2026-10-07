from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

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

    def test_encode_raises_when_password_empty(self) -> None:
        # Act & Assert
        with pytest.raises(ValueError, match="Password"):
            hasher.encode("")

    def test_encode_raises_when_salt_empty(self, faker: Faker) -> None:
        # Act & Assert
        with pytest.raises(ValueError, match="Salt"):
            hasher.encode(faker.password(), salt="")

    def test_encode_raises_when_salt_contains_separator(self, faker: Faker) -> None:
        # Arrange
        # Such a salt would split the encoded hash into wrong parts.
        salt = f"{faker.word()}{hasher.separator}{faker.word()}"

        # Act & Assert
        with pytest.raises(ValueError, match="Salt"):
            hasher.encode(faker.password(), salt=salt)

    def test_verify_returns_false_when_algorithm_differs(self, faker: Faker) -> None:
        # Arrange
        password = faker.password()
        # Few iterations: the count is stored in the hash, the check is the same.
        encoded = hasher.encode(password, iterations=faker.pyint(min_value=1, max_value=1_000))
        foreign = encoded.replace(hasher.algorithm, faker.word(), 1)

        # Act
        verified = hasher.verify(password, foreign)

        # Assert
        assert not verified

    def test_verify_returns_false_when_password_empty(self, faker: Faker) -> None:
        # Arrange
        # Few iterations: the count is stored in the hash, the check is the same.
        encoded = hasher.encode(faker.password(), iterations=faker.pyint(min_value=1, max_value=1_000))

        # Act
        verified = hasher.verify("", encoded)

        # Assert
        # False, not the encode error: an empty login form is a wrong password, not a server error.
        assert not verified
