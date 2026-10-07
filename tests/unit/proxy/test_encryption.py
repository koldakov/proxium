from __future__ import annotations

import asyncio
import ssl
from typing import TYPE_CHECKING

import pytest

from proxium.proxy import CachedEncryption, EncryptionUnavailable, MemoryCache
from tests.fixtures.proxy import ScriptedEncryption

if TYPE_CHECKING:
    from faker import Faker

    from proxium.proxy import Session


@pytest.fixture
def server_context() -> ssl.SSLContext:
    """No certificate: only the instance matters, no handshake happens."""
    return ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)


class TestCachedEncryption:
    async def test_context_asks_inner_once_when_connections_arrive_together(
        self,
        faker: Faker,
        server_context: ssl.SSLContext,
        session: Session,
    ) -> None:
        # Arrange
        inner = ScriptedEncryption([server_context])
        encryption = CachedEncryption(inner, cache=MemoryCache(), ttl=faker.pyfloat(min_value=60, max_value=3600))

        # Act
        # A flood of handshakes: one database lookup, not one per connection.
        await asyncio.gather(*(encryption.context(session) for _ in range(faker.pyint(min_value=2, max_value=20))))

        # Assert
        assert inner.calls == 1

    async def test_context_raises_cached_refusal_without_asking_inner_again(
        self,
        faker: Faker,
        server_context: ssl.SSLContext,
        session: Session,
    ) -> None:
        # Arrange
        # No certificate now, one uploaded later: the refusal holds until the TTL runs out.
        inner = ScriptedEncryption([EncryptionUnavailable(), server_context])
        encryption = CachedEncryption(inner, cache=MemoryCache(), ttl=faker.pyfloat(min_value=60, max_value=3600))
        with pytest.raises(EncryptionUnavailable):
            await encryption.context(session)

        # Act & Assert
        with pytest.raises(EncryptionUnavailable):
            await encryption.context(session)
        assert inner.calls == 1

    async def test_context_raises_new_refusal_instance_on_every_call(
        self,
        faker: Faker,
        session: Session,
    ) -> None:
        # Arrange
        inner = ScriptedEncryption([EncryptionUnavailable()])
        encryption = CachedEncryption(inner, cache=MemoryCache(), ttl=faker.pyfloat(min_value=60, max_value=3600))
        with pytest.raises(EncryptionUnavailable) as first:
            await encryption.context(session)

        # Act
        with pytest.raises(EncryptionUnavailable) as second:
            await encryption.context(session)

        # Assert
        # One shared instance would pile up the tracebacks of every refused connection.
        assert second.value is not first.value

    async def test_context_asks_inner_again_when_it_failed_otherwise(
        self,
        faker: Faker,
        server_context: ssl.SSLContext,
        session: Session,
    ) -> None:
        # Arrange
        # The database was down for a moment: TLS must not stay off for the whole TTL.
        inner = ScriptedEncryption([ConnectionError(), server_context])
        encryption = CachedEncryption(inner, cache=MemoryCache(), ttl=faker.pyfloat(min_value=60, max_value=3600))
        with pytest.raises(ConnectionError):
            await encryption.context(session)

        # Act
        context = await encryption.context(session)

        # Assert
        assert context is server_context
