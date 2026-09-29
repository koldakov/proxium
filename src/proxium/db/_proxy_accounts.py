from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import VARCHAR, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from ._base import BaseTimestampModel
from ._fields import Hash, HashField

if TYPE_CHECKING:
    from ._users import UserModel


class ProxyBaseAccountModel(BaseTimestampModel):
    """A proxy client. Each auth method has its own table."""

    __abstract__ = True

    is_active: Mapped[bool] = mapped_column(
        default=True,
        server_default="true",
    )
    # Never expires when empty.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    # The admin who created the account. An admin with accounts can't be deleted, deactivate them instead.
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
    )

    @property
    def secret_hash(self) -> Hash:
        """The stored hash of the secret the client proves itself with."""
        raise NotImplementedError()

    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= datetime.now(UTC)

    # Relationships on an abstract model must be declared per subclass.
    @declared_attr
    @classmethod
    def created_by(cls) -> Mapped[UserModel]:
        # UserModel names its back reference after the account table.
        return relationship(
            back_populates=cls.__tablename__,
        )


class BasicProxyAccountModel(ProxyBaseAccountModel):
    """Username and password, e.g. HTTP Basic or SOCKS5."""

    __tablename__ = "basic_proxy_accounts"

    username: Mapped[str] = mapped_column(
        VARCHAR(length=255),
        unique=True,
    )
    password: Mapped[Hash] = mapped_column(
        HashField(length=255),
    )

    @property
    def secret_hash(self) -> Hash:
        return self.password


class TokenProxyAccountModel(ProxyBaseAccountModel):
    """Bearer token `<key>.<secret>`. Found by the public `key`, then checked against the hashed `token`.

    A salted hash can't be looked up by value, hence the key.
    """

    __tablename__ = "token_proxy_accounts"

    # Tells tokens apart in logs and the admin, the token itself is never shown again.
    name: Mapped[str] = mapped_column(
        VARCHAR(length=255),
        unique=True,
    )
    key: Mapped[str] = mapped_column(
        VARCHAR(length=32),
        unique=True,
    )
    # The whole token, key included.
    token: Mapped[Hash] = mapped_column(
        HashField(length=255),
    )

    @property
    def secret_hash(self) -> Hash:
        return self.token
