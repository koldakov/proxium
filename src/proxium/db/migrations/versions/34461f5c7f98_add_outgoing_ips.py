"""Add outgoing IPs

Revision ID: 34461f5c7f98
Revises: d6d13be2f480
Create Date: 2026-10-01 00:19:06.514616

"""

from typing import TYPE_CHECKING, Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "34461f5c7f98"
down_revision: str | None = "d6d13be2f480"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Table, owner column, owner table: one pool table per owner kind, the same shape.
LINK_TABLES: Final[tuple[tuple[str, str, str], ...]] = (
    ("basic_proxy_account_outgoing_ips", "basic_proxy_account_id", "basic_proxy_accounts"),
    ("token_proxy_account_outgoing_ips", "token_proxy_account_id", "token_proxy_accounts"),
    ("trusted_network_outgoing_ips", "trusted_network_id", "trusted_networks"),
)


def upgrade() -> None:
    op.create_table(
        "outgoing_ips",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "ip",
            postgresql.INET(),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.VARCHAR(length=255),
            nullable=False,
        ),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ip"),
    )

    for table, owner_column, owner_table in LINK_TABLES:
        op.create_table(
            table,
            sa.Column(
                "id",
                sa.Integer(),
                nullable=False,
            ),
            sa.Column(
                owner_column,
                sa.Integer(),
                nullable=False,
            ),
            sa.Column(
                "outgoing_ip_id",
                sa.Integer(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                [owner_column],
                [f"{owner_table}.id"],
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["outgoing_ip_id"],
                ["outgoing_ips.id"],
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                owner_column,
                "outgoing_ip_id",
            ),
        )

        # Existing owners go out the way they did: the OS picks the IP.
        op.add_column(
            owner_table,
            sa.Column(
                "outgoing_mode",
                sa.Enum(
                    "system",
                    "listener",
                    "pool",
                    name="outgoing_mode",
                    native_enum=False,
                    create_constraint=True,
                    length=16,
                ),
                server_default="system",
                nullable=False,
            ),
        )


def downgrade() -> None:
    for table, _, owner_table in reversed(LINK_TABLES):
        op.drop_column(owner_table, "outgoing_mode")
        op.drop_table(table)
    op.drop_table("outgoing_ips")
