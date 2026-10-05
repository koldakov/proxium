from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network
from typing import TYPE_CHECKING

from sqlalchemy import VARCHAR, ForeignKey
from sqlalchemy.dialects.postgresql import CIDR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import BaseTimestampModel
from ._fields import ChoiceField
from ._outgoing_ips import OutgoingMode

if TYPE_CHECKING:
    # SQLAlchemy finds relationship targets by name in its registry, a runtime import would be circular.
    from ._users import UserModel  # noqa: TC004


class TrustedNetworkModel(BaseTimestampModel):
    """A network whose clients use the proxy without credentials. None by default, so everyone needs them."""

    __tablename__ = "trusted_networks"

    # A single address is stored as /32 or /128. The database rejects host bits, e.g. 10.0.0.1/8.
    network: Mapped[IPv4Network | IPv6Network] = mapped_column(
        CIDR(),
        unique=True,
    )
    # A label for people, e.g. "Office".
    name: Mapped[str] = mapped_column(
        VARCHAR(length=255),
    )
    # False turns the network off without losing it.
    is_active: Mapped[bool] = mapped_column(
        default=True,
        server_default="true",
    )
    # Which IP the proxy connects to targets from. `pool` needs a non-empty pool, the other modes ignore it.
    outgoing_mode: Mapped[OutgoingMode] = mapped_column(
        ChoiceField(
            OutgoingMode,
            name="outgoing_mode",
            length=16,
        ),
        default=OutgoingMode.SYSTEM,
        server_default=OutgoingMode.SYSTEM.value,
    )
    # The admin who added the network. An admin with networks can't be deleted.
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
    )

    created_by: Mapped[UserModel] = relationship(
        back_populates="trusted_networks",
    )
