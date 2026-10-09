from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import VARCHAR, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import BaseTimestampModel
from ._fields import Hash, HashField

if TYPE_CHECKING:
    # SQLAlchemy finds relationship targets by name in its registry, a runtime import would be circular.
    from ._outgoing_ips import OutgoingIPModel  # noqa: TC004
    from ._policies import PolicyModel  # noqa: TC004
    from ._proxy_accounts import BasicProxyAccountModel, TokenProxyAccountModel  # noqa: TC004
    from ._trusted_networks import TrustedNetworkModel  # noqa: TC004


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
    # Tokens carry it, a new one revokes the tokens issued before. Random, so a token tells nothing about the password.
    session_key: Mapped[uuid.UUID] = mapped_column(
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    is_active: Mapped[bool] = mapped_column(
        default=False,
        server_default="false",
    )
    is_superuser: Mapped[bool] = mapped_column(
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
    trusted_networks: Mapped[list[TrustedNetworkModel]] = relationship(
        back_populates="created_by",
        passive_deletes="all",
    )
    outgoing_ips: Mapped[list[OutgoingIPModel]] = relationship(
        back_populates="created_by",
        passive_deletes="all",
    )
    policies: Mapped[list[PolicyModel]] = relationship(
        back_populates="created_by",
        passive_deletes="all",
    )

    def set_password(self, password: Hash, /) -> None:
        """Also revokes the tokens issued before, like Django's session auth hash."""
        self.password = password
        self.session_key = uuid.uuid4()
