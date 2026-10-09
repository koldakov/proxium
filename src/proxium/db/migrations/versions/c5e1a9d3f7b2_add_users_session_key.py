"""Add users session_key

Revision ID: c5e1a9d3f7b2
Revises: b2c6e8f4a1d7
Create Date: 2026-10-09 12:00:00.000000

"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "c5e1a9d3f7b2"
down_revision: str | None = "b2c6e8f4a1d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "session_key",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "session_key")
