"""Add users is_superuser

Revision ID: 9e18185e5a1d
Revises: d2242c2f261b
Create Date: 2026-09-27 23:03:14.000000

"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "9e18185e5a1d"
down_revision: str | None = "d2242c2f261b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_superuser",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_superuser")
