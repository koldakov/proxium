"""Immutable proxy credentials

Revision ID: 5c3f8a1e7b20
Revises: 9e18185e5a1d
Create Date: 2026-09-29 12:00:00.000000

"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "5c3f8a1e7b20"
down_revision: str | None = "9e18185e5a1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing accounts get their username as the name.
    op.add_column(
        "basic_proxy_accounts",
        sa.Column(
            "name",
            sa.VARCHAR(length=255),
            nullable=True,
        ),
    )
    op.execute("UPDATE basic_proxy_accounts SET name = username")
    op.alter_column(
        "basic_proxy_accounts",
        "name",
        nullable=False,
    )
    op.drop_constraint(
        "token_proxy_accounts_name_key",
        "token_proxy_accounts",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "token_proxy_accounts_name_key",
        "token_proxy_accounts",
        ["name"],
    )
    op.drop_column("basic_proxy_accounts", "name")
