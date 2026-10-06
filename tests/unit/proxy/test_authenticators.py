from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from proxium.proxy import (
    AnonymousAuthenticator,
    AuthenticationRequired,
    AuthenticationUnavailable,
    BasicCredentials,
    BearerCredentials,
    CachedAuthenticator,
    ClientKey,
    CredentialsKey,
    DispatchAuthenticator,
    MemoryCache,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from faker import Faker

    from proxium.proxy import Session
    from tests.fixtures.proxy import FailingOnceAuthenticator


class TestDispatchAuthenticator:
    async def test_authenticate_raises_authentication_required_when_no_credentials(self, session: Session) -> None:
        # Arrange
        authenticator = DispatchAuthenticator({BasicCredentials: AnonymousAuthenticator()})

        # Act & Assert
        with pytest.raises(AuthenticationRequired):
            await authenticator.authenticate(None, session)

    async def test_authenticate_raises_authentication_required_when_credentials_type_not_registered(
        self,
        faker: Faker,
        session: Session,
    ) -> None:
        # Arrange
        authenticator = DispatchAuthenticator({BasicCredentials: AnonymousAuthenticator()})

        # Act & Assert
        with pytest.raises(AuthenticationRequired):
            await authenticator.authenticate(BearerCredentials(token=faker.sha256()), session)


class TestCredentialsKey:
    def test_call_returns_different_keys_when_passwords_differ(self, faker: Faker, session: Session) -> None:
        # Arrange
        key = CredentialsKey(secret=faker.binary(length=32))
        username = faker.user_name()
        credentials = BasicCredentials(username=username, password=faker.unique.password())
        other_credentials = BasicCredentials(username=username, password=faker.unique.password())

        # Act
        digest = key(credentials, session)
        other_digest = key(other_credentials, session)

        # Assert
        assert digest != other_digest


class TestClientKey:
    def test_call_returns_different_keys_when_client_hosts_differ(
        self,
        faker: Faker,
        session_factory: Callable[[], Session],
    ) -> None:
        # Arrange
        key = ClientKey(secret=faker.binary(length=32))
        session = session_factory()
        other_session = session_factory()

        # Act
        digest = key(None, session)
        other_digest = key(None, other_session)

        # Assert
        assert digest != other_digest

    def test_call_returns_different_keys_when_only_one_has_credentials(self, faker: Faker, session: Session) -> None:
        # Arrange
        key = ClientKey(secret=faker.binary(length=32))
        credentials = BearerCredentials(token=faker.sha256())

        # Act
        digest = key(None, session)
        other_digest = key(credentials, session)

        # Assert
        assert digest != other_digest


class TestCachedAuthenticator:
    async def test_authenticate_raises_authentication_unavailable_when_inner_fails(
        self,
        faker: Faker,
        failing_once_authenticator: FailingOnceAuthenticator,
        session: Session,
    ) -> None:
        # Arrange
        authenticator = CachedAuthenticator(
            failing_once_authenticator,
            key=CredentialsKey(secret=faker.binary(length=32)),
            cache=MemoryCache(),
            refusals=MemoryCache(),
        )

        # Act & Assert
        with pytest.raises(AuthenticationUnavailable):
            await authenticator.authenticate(None, session)

    async def test_authenticate_returns_identity_when_inner_failed_before(
        self,
        faker: Faker,
        failing_once_authenticator: FailingOnceAuthenticator,
        session: Session,
    ) -> None:
        # Arrange
        authenticator = CachedAuthenticator(
            failing_once_authenticator,
            key=CredentialsKey(secret=faker.binary(length=32)),
            cache=MemoryCache(),
            refusals=MemoryCache(),
        )
        with pytest.raises(AuthenticationUnavailable):
            await authenticator.authenticate(None, session)

        # Act
        identity = await authenticator.authenticate(None, session)

        # Assert
        assert identity == failing_once_authenticator.identity
