"""Add traffic

Revision ID: d6d13be2f480
Revises: 9459b06b4cc6
Create Date: 2026-09-30 20:26:23.414915

"""

from typing import TYPE_CHECKING, Final

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "d6d13be2f480"
down_revision: str | None = "9459b06b4cc6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Table, owner column, owner table: one traffic table per owner kind, the same shape.
TRAFFIC_TABLES: Final[tuple[tuple[str, str, str], ...]] = (
    ("basic_proxy_account_traffic", "basic_proxy_account_id", "basic_proxy_accounts"),
    ("token_proxy_account_traffic", "token_proxy_account_id", "token_proxy_accounts"),
    ("trusted_network_traffic", "trusted_network_id", "trusted_networks"),
)


def upgrade() -> None:
    for table, owner_column, owner_table in TRAFFIC_TABLES:
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
                "day",
                sa.Date(),
                nullable=False,
            ),
            sa.Column(
                "bytes_sent",
                sa.BigInteger(),
                server_default="0",
                nullable=False,
            ),
            sa.Column(
                "bytes_received",
                sa.BigInteger(),
                server_default="0",
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                [owner_column],
                [f"{owner_table}.id"],
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                owner_column,
                "day",
            ),
        )


def downgrade() -> None:
    for table, _, _ in reversed(TRAFFIC_TABLES):
        op.drop_table(table)
