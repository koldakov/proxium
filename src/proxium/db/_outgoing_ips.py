from __future__ import annotations

from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import VARCHAR, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from ._base import BaseModel, BaseTimestampModel

if TYPE_CHECKING:
    # SQLAlchemy finds relationship targets by name in its registry, a runtime import would be circular.
    from ._users import UserModel  # noqa: TC004


class OutgoingMode(StrEnum):
    """Which IP the proxy connects to targets from, set per account and trusted network."""

    # The OS picks, usually the main IP of the server.
    SYSTEM = "system"
    # The IP the client connected to.
    LISTENER = "listener"
    # A random IP of the pool assigned to the account.
    POOL = "pool"


class OutgoingIPModel(BaseTimestampModel):
    """An IP of this server the proxy may connect to targets from. Assigned to accounts and trusted networks as a pool.

    The database doesn't know the server's interfaces: an IP that isn't on them fails every connection from it.
    """

    __tablename__ = "outgoing_ips"

    ip: Mapped[IPv4Address | IPv6Address] = mapped_column(
        INET(),
        unique=True,
    )
    # A label for people, e.g. "Frankfurt 1".
    name: Mapped[str] = mapped_column(
        VARCHAR(length=255),
    )
    # The admin who added the IP. An admin with IPs can't be deleted.
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
    )

    created_by: Mapped[UserModel] = relationship(
        back_populates="outgoing_ips",
    )


class BaseOutgoingIPLinkModel(BaseModel):
    """An IP in the pool of one owner. Each owner kind has its own table, so the owner is a real foreign key.

    An IP in a pool can't be deleted, take it out of the pools first.
    """

    __abstract__ = True

    # The foreign key column of the owner.
    owner_column: ClassVar[str]

    outgoing_ip_id: Mapped[int] = mapped_column(
        ForeignKey(
            "outgoing_ips.id",
            ondelete="RESTRICT",
        ),
    )

    # One row per owner and IP.
    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple[Any, ...]:
        return (
            UniqueConstraint(
                cls.owner_column,
                "outgoing_ip_id",
            ),
        )


class BasicProxyAccountOutgoingIPModel(BaseOutgoingIPLinkModel):
    __tablename__ = "basic_proxy_account_outgoing_ips"

    owner_column: ClassVar[str] = "basic_proxy_account_id"

    basic_proxy_account_id: Mapped[int] = mapped_column(
        ForeignKey(
            "basic_proxy_accounts.id",
            ondelete="RESTRICT",
        ),
    )


class TokenProxyAccountOutgoingIPModel(BaseOutgoingIPLinkModel):
    __tablename__ = "token_proxy_account_outgoing_ips"

    owner_column: ClassVar[str] = "token_proxy_account_id"

    token_proxy_account_id: Mapped[int] = mapped_column(
        ForeignKey(
            "token_proxy_accounts.id",
            ondelete="RESTRICT",
        ),
    )


class TrustedNetworkOutgoingIPModel(BaseOutgoingIPLinkModel):
    __tablename__ = "trusted_network_outgoing_ips"

    owner_column: ClassVar[str] = "trusted_network_id"

    trusted_network_id: Mapped[int] = mapped_column(
        ForeignKey(
            "trusted_networks.id",
            ondelete="RESTRICT",
        ),
    )
