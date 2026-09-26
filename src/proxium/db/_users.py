from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import VARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import BaseTimestampModel
from ._fields import Hash, HashField

# SQLAlchemy finds relationship targets by name in its registry, a runtime import would be circular.
if TYPE_CHECKING:
    from ._proxy_accounts import BasicProxyAccountModel, TokenProxyAccountModel  # noqa: TC004


class UserModel(BaseTimestampModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        VARCHAR(length=255),
        unique=True,
    )
    name: Mapped[str] = mapped_column(
        VARCHAR(length=150),
    )
    surname: Mapped[str] = mapped_column(
        VARCHAR(length=150),
    )
    password: Mapped[Hash] = mapped_column(
        HashField(length=255),
    )
    is_active: Mapped[bool] = mapped_column(
        default=False,
        server_default="false",
    )

    # Accounts the admin created. passive_deletes leaves them to the database, so its RESTRICT keeps the admin.
    basic_proxy_accounts: Mapped[list[BasicProxyAccountModel]] = relationship(
        back_populates="created_by",
        passive_deletes="all",
    )
    token_proxy_accounts: Mapped[list[TokenProxyAccountModel]] = relationship(
        back_populates="created_by",
        passive_deletes="all",
    )
