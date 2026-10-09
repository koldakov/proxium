from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import jwt
import pytest

from proxium.api.services import (
    AccessToken,
    ExpiredTokenError,
    InvalidTokenError,
    InvalidTokenPayloadError,
    RefreshToken,
    TokenUser,
)
from proxium.db import Hash

if TYPE_CHECKING:
    from faker import Faker

    from proxium.db import UserModel


class TestTokenUser:
    def test_has_session_of_returns_true_when_password_unchanged(self, user_model: UserModel) -> None:
        # Arrange
        token_user = TokenUser.from_user(user_model)

        # Act
        has_session = token_user.has_session_of(user_model)

        # Assert
        assert has_session

    def test_has_session_of_returns_false_when_password_changed(self, faker: Faker, user_model: UserModel) -> None:
        # Arrange
        token_user = TokenUser.from_user(user_model)
        user_model.set_password(Hash(faker.unique.sha256()))

        # Act
        has_session = token_user.has_session_of(user_model)

        # Assert
        # Tokens issued before the change are revoked.
        assert not has_session


class TestAccessToken:
    def test_decode_returns_same_user_when_encoded_by_itself(self, user_model: UserModel) -> None:
        # Arrange
        token = AccessToken.from_user(user_model)

        # Act
        decoded = AccessToken.decode(token.encode())

        # Assert
        assert decoded.user == token.user

    def test_decode_raises_payload_error_when_given_refresh_token(self, user_model: UserModel) -> None:
        # Arrange
        token = RefreshToken.from_user(user_model).encode()

        # Act & Assert
        with pytest.raises(InvalidTokenPayloadError):
            AccessToken.decode(token)

    def test_decode_raises_expired_when_exp_passed(self, faker: Faker, user_model: UserModel) -> None:
        # Arrange
        token = AccessToken(
            exp=datetime.now(UTC) - timedelta(seconds=faker.pyint(min_value=1, max_value=3600)),
            user=TokenUser.from_user(user_model),
        ).encode()

        # Act & Assert
        with pytest.raises(ExpiredTokenError):
            AccessToken.decode(token)

    def test_decode_raises_invalid_when_signed_with_other_key(self, faker: Faker, user_model: UserModel) -> None:
        # Arrange
        # HS256 wants at least 32 bytes of key.
        other_key = faker.pystr(min_chars=32, max_chars=64)
        token = jwt.encode(AccessToken.from_user(user_model).model_dump(), other_key, algorithm=AccessToken.algorithm)

        # Act & Assert
        with pytest.raises(InvalidTokenError):
            AccessToken.decode(token)
