from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

from sqlalchemy import BigInteger, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from ._base import BaseModel


class BaseTrafficModel(BaseModel):
    """Bytes of one owner in one UTC day. Each owner kind has its own table, so the owner is a real foreign key.

    The proxy only adds to a row. An owner with traffic can't be deleted.
    """

    __abstract__ = True

    # The foreign key column of the owner. The proxy finds the owner by the identity claim of the same name.
    owner_column: ClassVar[str]

    day: Mapped[date] = mapped_column(
        Date(),
    )
    # From the client to the target, request heads included.
    bytes_sent: Mapped[int] = mapped_column(
        BigInteger(),
        default=0,
        server_default="0",
    )
    # From the target to the client.
    bytes_received: Mapped[int] = mapped_column(
        BigInteger(),
        default=0,
        server_default="0",
    )

    # One row per owner and day, the proxy upserts into it.
    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple[Any, ...]:
        return (
            UniqueConstraint(
                cls.owner_column,
                "day",
            ),
        )


class BasicProxyAccountTrafficModel(BaseTrafficModel):
    __tablename__ = "basic_proxy_account_traffic"

    owner_column: ClassVar[str] = "basic_proxy_account_id"

    basic_proxy_account_id: Mapped[int] = mapped_column(
        ForeignKey(
            "basic_proxy_accounts.id",
            ondelete="RESTRICT",
        ),
    )


class TokenProxyAccountTrafficModel(BaseTrafficModel):
    __tablename__ = "token_proxy_account_traffic"

    owner_column: ClassVar[str] = "token_proxy_account_id"

    token_proxy_account_id: Mapped[int] = mapped_column(
        ForeignKey(
            "token_proxy_accounts.id",
            ondelete="RESTRICT",
        ),
    )


class TrustedNetworkTrafficModel(BaseTrafficModel):
    __tablename__ = "trusted_network_traffic"

    owner_column: ClassVar[str] = "trusted_network_id"

    trusted_network_id: Mapped[int] = mapped_column(
        ForeignKey(
            "trusted_networks.id",
            ondelete="RESTRICT",
        ),
    )
