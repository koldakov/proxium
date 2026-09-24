from __future__ import annotations

from collections import UserString
from typing import TYPE_CHECKING, Self

from sqlalchemy import VARCHAR
from sqlalchemy.types import TypeDecorator

from proxium.core import hasher

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
