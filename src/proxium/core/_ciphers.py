from __future__ import annotations

from typing import TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken

from ._settings import encryption_settings

if TYPE_CHECKING:
    from pydantic import SecretStr


class DecryptionError(Exception):
    """The value wasn't encrypted with this key: the key changed, or the value is broken."""


class FernetCipher:
    """Encrypts secrets kept in the database, e.g. private keys. Authenticated: a tampered value fails to decrypt."""

    def __init__(self, key: SecretStr, /) -> None:
        self._fernet: Fernet = Fernet(key.get_secret_value())

    def encrypt(self, value: str, /) -> str:
        return self._fernet.encrypt(value.encode()).decode("ascii")

    def decrypt(self, token: str, /) -> str:
        try:
            return self._fernet.decrypt(token).decode()
        except InvalidToken:
            raise DecryptionError() from None


cipher: FernetCipher = FernetCipher(encryption_settings.key)
