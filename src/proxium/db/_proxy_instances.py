from datetime import datetime
from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address

from sqlalchemy import ARRAY, TEXT, VARCHAR, DateTime
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from ._base import BaseTimestampModel
from ._fields import ChoiceField


class ProxyInstanceStatus(StrEnum):
    """What a proxy process reports about itself. One that stops reporting is unknown, see `expires_at`."""

    # Started, not serving yet.
    PENDING = "pending"
    # Serving clients.
    RUNNING = "running"
    # Shut down gracefully.
    STOPPED = "stopped"


class ProxyInstanceModel(BaseTimestampModel):
    """A proxy instance, written by its process. `created_at` is when the instance was first seen.

    `last_seen_at` and `expires_at` are the database's time, so clocks of instances don't matter there.
    """

    __tablename__ = "proxy_instances"

    # SHA-256 of the machine id and the host name, hex: what tells instances apart. Kept across restarts, differs
    # between machines, containers and pods. In Docker the host name is the container id, so a recreated container is
    # a new instance.
    key: Mapped[str] = mapped_column(
        VARCHAR(length=64),
        unique=True,
    )
    hostname: Mapped[str] = mapped_column(
        VARCHAR(length=255),
    )
    # When the current process started, by the instance's clock. Two processes of one instance, e.g. during a restart
    # without downtime, share the clock: the newer one owns the row.
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )
    # `PROXY_NAME`, the instance in `Proxy-Status` of HTTP responses. Text: the setting has no length limit.
    name: Mapped[str] = mapped_column(
        TEXT(),
    )
    # The proxium version the process runs.
    version: Mapped[str] = mapped_column(
        VARCHAR(length=64),
    )
    status: Mapped[ProxyInstanceStatus] = mapped_column(
        ChoiceField(
            ProxyInstanceStatus,
            name="proxy_instance_status",
            length=16,
        ),
    )
    # The last report. For a stopped instance it's when it stopped.
    # Not indexed, as `expires_at`: reports then update in place (HOT), the table doesn't bloat.
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )
    # The next report is due by then. Past it and not stopped, the instance is unknown: crashed, hung or cut off.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )
    # IPs on the instance's interfaces as of the last report: the outgoing IPs it can connect from. Inside Docker
    # bridge networking these are the container's, not the host's. Part of the instance's state like `version`,
    # replaced on each report, so a column, not rows.
    ips: Mapped[list[IPv4Address | IPv6Address]] = mapped_column(
        ARRAY(
            INET(),
        ),
        default=list,
        server_default="{}",
    )
    # Deregistered by an admin. A report of the process registers it again: it's alive after all.
    is_deleted: Mapped[bool] = mapped_column(
        default=False,
        server_default="false",
    )
