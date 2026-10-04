from __future__ import annotations

import asyncio
import ssl
import tempfile
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from proxium.core import DecryptionError
from proxium.db import CertificateModel, Encrypted, session_manager
from proxium.proxy import Encryption, EncryptionUnavailable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Result, Select

    from proxium.proxy import Session


class CertificateEncryption(Encryption):
    """TLS with the active `CertificateModel`, refused while none is active.

    Looked up and built anew on every call: wrap it in `CachedEncryption`, so TLS clients don't hit the database
    before they authenticate. Activating another certificate applies to new connections, open ones keep theirs.
    """

    def __init__(self, *, alpn_protocols: Sequence[str] = ("http/1.1",)) -> None:
        # Offered to clients: only what the inbounds speak, so a client doesn't pick e.g. HTTP/2.
        self._alpn_protocols: list[str] = list(alpn_protocols)

    @property
    def _get_active_certificate_statement(self) -> Select[tuple[str, Encrypted]]:
        return select(CertificateModel.certificate, CertificateModel.private_key).where(
            CertificateModel.is_active.is_(True),
        )

    @staticmethod
    def _load_cert_chain(context: ssl.SSLContext, pem: str, /) -> None:
        """Load the key and chain through a temporary file, readable by this user alone and removed once loaded.

        `ssl` loads them from files only, not from memory: https://github.com/python/cpython/issues/60691.
        Closed before loading, as Windows can't open a file twice. Needs a writable `TMPDIR`.
        """
        with tempfile.NamedTemporaryFile("w", suffix=".pem", delete_on_close=False) as file:
            file.write(pem)
            file.close()
            context.load_cert_chain(file.name)

    def _create_context(self, certificate: str, private_key: Encrypted, /) -> ssl.SSLContext:
        """Blocking: decrypts, writes and reads a file. Runs in a thread, see `context`."""
        try:
            key = private_key.decrypt()
        except DecryptionError:
            raise EncryptionUnavailable(
                "The active certificate's key can't be decrypted: ENCRYPTION_KEY has changed since it was uploaded.",
            ) from None

        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.set_alpn_protocols(self._alpn_protocols)
        try:
            self._load_cert_chain(context, key + certificate)
        except ssl.SSLError as err:
            # The PEM was checked on upload, so it's a bug. Not raised as is: being an OSError, `Connection` would
            # take it for the client's fault and log no traceback.
            raise RuntimeError(f"Can't load the active certificate: {err}") from err
        except OSError as err:
            raise EncryptionUnavailable(
                f"Can't write the certificate to a temporary file in {tempfile.gettempdir()}: {err.strerror}. "
                "Set TMPDIR to a writable directory.",
            ) from None
        return context

    async def context(self, session: Session, /) -> ssl.SSLContext:
        async with session_manager.session() as db_session:
            result: Result[tuple[str, Encrypted]] = await db_session.execute(self._get_active_certificate_statement)

        try:
            certificate, private_key = result.one()
        except NoResultFound:
            raise EncryptionUnavailable("No active certificate.") from None

        # Decrypting and loading are CPU and file work, they would stall the loop.
        return await asyncio.to_thread(self._create_context, certificate, private_key)
