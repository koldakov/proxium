from __future__ import annotations

from collections import UserString
from enum import StrEnum
from typing import TYPE_CHECKING, Self

from sqlalchemy import TEXT, VARCHAR, Enum
from sqlalchemy.types import TypeDecorator

from proxium.core import cipher, hasher

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect


class Hash(UserString):
    """Hashed value, e.g. a password."""

    @classmethod
    def create(
        cls,
        value: str,
        /,
    ) -> Self:
        return cls(hasher.encode(value))

    def verify(
        self,
        value: str,
        /,
    ) -> bool:
        return hasher.verify(
            value,
            self.data,
        )


class HashField(TypeDecorator[Hash]):
    """Stores `Hash` as a string. Plain strings are hashed on write."""

    impl = VARCHAR
    cache_ok = True

    def process_bind_param(
        self,
        value: Hash | str | None,
        dialect: Dialect,
    ) -> str | None:
        if value is None:
            return None
        if isinstance(value, Hash):
            return value.data
        return hasher.encode(value)

    def process_result_value(
        self,
        value: str | None,
        dialect: Dialect,
    ) -> Hash | None:
        return None if value is None else Hash(value)


class Encrypted(UserString):
    """Encrypted value, e.g. a private key. Loaded as is, decrypted only by `decrypt`."""

    @classmethod
    def create(
        cls,
        value: str,
        /,
    ) -> Self:
        return cls(cipher.encrypt(value))

    def decrypt(self) -> str:
        """The plain value. Raises `DecryptionError` if `ENCRYPTION_KEY` has changed since."""
        return cipher.decrypt(self.data)


class EncryptedField(TypeDecorator[Encrypted]):
    """Stores `Encrypted` as text. Takes only `Encrypted`: a plain string is never encrypted behind the scenes."""

    impl = TEXT
    cache_ok = True

    def process_bind_param(
        self,
        value: Encrypted | None,
        dialect: Dialect,
    ) -> str | None:
        if value is None:
            return None
        if not isinstance(value, Encrypted):
            raise TypeError(f"Expected Encrypted, got {type(value).__name__}.")
        return value.data

    def process_result_value(
        self,
        value: str | None,
        dialect: Dialect,
    ) -> Encrypted | None:
        return None if value is None else Encrypted(value)


class ChoiceField[C: StrEnum](TypeDecorator[C]):
    """Stores a `StrEnum` by its values as a string with a check, not a PostgreSQL enum.

    A new choice needs no type migration. `Enum` converts values both ways.
    """

    impl = Enum
    cache_ok = True

    def __init__(
        self,
        choices: type[C],
        /,
        *,
        name: str,
        length: int,
    ) -> None:
        # Kept for the cache key of the type.
        self.choices: type[C] = choices
        self.name: str = name
        self.length: int = length

        super().__init__(
            choices,
            name=name,
            native_enum=False,
            create_constraint=True,
            length=length,
            values_callable=lambda members: [member.value for member in members],
        )
