from typing import TYPE_CHECKING, ClassVar

from sqlalchemy import Result, Select, Update, select, update

from proxium.core import DecryptionError
from proxium.db import CertificateModel, Encrypted, session_manager
from proxium.management._base import BaseAsyncCommand, CommandError

if TYPE_CHECKING:
    from argparse import Namespace


class RotateEncryptionKeyCommand(BaseAsyncCommand):
    """Re-encrypts secrets in the database with `ENCRYPTION_KEY`, reading them with it or `ENCRYPTION_OLD_KEYS`.

    Runs with both keys set everywhere, so the proxy and the API read every secret meanwhile, before or after
    rotation. Commits in chunks: stopped halfway, it's just run again.
    """

    name: ClassVar[str] = "rotateencryptionkey"
    help: ClassVar[str] = "Re-encrypt stored secrets with ENCRYPTION_KEY, so ENCRYPTION_OLD_KEYS can be removed."

    chunk_size: ClassVar[int] = 100

    def _get_private_keys_statement(self, after_id: int, /) -> Select[tuple[int, Encrypted]]:
        return (
            select(CertificateModel.id, CertificateModel.private_key)
            .where(CertificateModel.id > after_id)
            .order_by(CertificateModel.id)
            .limit(self.chunk_size)
        )

    @staticmethod
    def _update_private_key_statement(certificate_id: int, private_key: Encrypted, /) -> Update:
        return update(CertificateModel).where(CertificateModel.id == certificate_id).values(private_key=private_key)

    @staticmethod
    def _rotate(certificate_id: int, private_key: Encrypted, /) -> Encrypted:
        try:
            return private_key.rotate()
        except DecryptionError:
            raise CommandError(
                f"The private key of certificate {certificate_id} can't be decrypted: neither ENCRYPTION_KEY "
                "nor ENCRYPTION_OLD_KEYS is the key it was encrypted with.",
            ) from None

    async def _rotate_chunk(self, after_id: int, /) -> list[int]:
        """Re-encrypt the next chunk after `after_id`. Returns the ids done, empty when nothing is left."""
        async with session_manager.session() as session:
            result: Result[tuple[int, Encrypted]] = await session.execute(self._get_private_keys_statement(after_id))
            rows = result.all()
            for certificate_id, private_key in rows:
                await session.execute(
                    self._update_private_key_statement(certificate_id, self._rotate(certificate_id, private_key)),
                )
            await session.commit()
        return [certificate_id for certificate_id, _ in rows]

    async def ahandle(self, args: Namespace, /) -> None:
        count = 0
        after_id = 0
        while ids := await self._rotate_chunk(after_id):
            count += len(ids)
            after_id = ids[-1]
        self.stdout.write(f"Re-encrypted {count} private key(s) with ENCRYPTION_KEY.\n")
