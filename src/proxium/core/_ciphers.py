from __future__ import annotations

from typing import TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from ._settings import encryption_settings

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pydantic import SecretStr


class DecryptionError(Exception):
    """The value wasn't encrypted with any of the keys: the key changed, or the value is broken."""


class FernetCipher:
    """Encrypts secrets kept in the database, e.g. private keys. Authenticated: a tampered value fails to decrypt.

    Encrypts with `key`, decrypts with it or any of `old_keys`: secrets stay readable while they're rotated.
    """

    def __init__(self, key: SecretStr, /, *, old_keys: Sequence[SecretStr] = ()) -> None:
        self._fernet: MultiFernet = MultiFernet(
            [Fernet(item.get_secret_value()) for item in (key, *old_keys)],
        )

    def encrypt(self, value: str, /) -> str:
        return self._fernet.encrypt(value.encode()).decode("ascii")

    def decrypt(self, token: str, /) -> str:
        try:
            return self._fernet.decrypt(token).decode()
        except InvalidToken:
            raise DecryptionError() from None

    def rotate(self, token: str, /) -> str:
        """The same value encrypted with `key`."""
        try:
            return self._fernet.rotate(token).decode("ascii")
        except InvalidToken:
            raise DecryptionError() from None


cipher: FernetCipher = FernetCipher(encryption_settings.key, old_keys=encryption_settings.old_keys)
