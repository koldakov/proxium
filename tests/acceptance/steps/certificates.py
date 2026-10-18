from __future__ import annotations

import ssl
from typing import TYPE_CHECKING

import httpx
from pytest_bdd import given, then

from proxium.certificates import generate_self_signed, read_certificate
from proxium.db import CertificateModel, Encrypted, session_manager
from tests.fixtures.runners import LOOPBACK

from ._async import async_step

if TYPE_CHECKING:
    from .proxy import Outcome


async def _store_certificate(*, is_active: bool) -> ssl.SSLContext:
    """Store a self-signed certificate of the proxy address, return a client context trusting it alone."""
    certificate, private_key = generate_self_signed([str(LOOPBACK)], days=1)
    info = read_certificate(certificate, private_key)
    model = CertificateModel(
        certificate=info.certificate,
        private_key=Encrypted.create(info.private_key),
        names=info.names,
        fingerprint=info.fingerprint,
        is_self_signed=info.is_self_signed,
        not_valid_before=info.not_valid_before,
        not_valid_after=info.not_valid_after,
        is_active=is_active,
    )
    async with session_manager.session() as session:
        session.add(model)
        await session.commit()
    return ssl.create_default_context(cadata=info.certificate)


@given("an active certificate", target_fixture="client_ssl_context")
@async_step
async def _(database: None) -> ssl.SSLContext:
    return await _store_certificate(is_active=True)


@given("a certificate that isn't active", target_fixture="client_ssl_context")
@async_step
async def _(database: None) -> ssl.SSLContext:
    return await _store_certificate(is_active=False)


@given("no certificate")
def _() -> None:
    """None is stored: the database starts empty."""


@then("the TLS handshake fails")
def _(outcome: Outcome) -> None:
    assert isinstance(outcome, httpx.ConnectError)
