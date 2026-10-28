"""Add proxy instances ips

Revision ID: e6c2b9f4d1a8
Revises: d8b4f1a6c3e9
Create Date: 2026-10-28 12:00:00.000000

"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "e6c2b9f4d1a8"
down_revision: str | None = "d8b4f1a6c3e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "proxy_instances",
        sa.Column(
            "ips",
            sa.ARRAY(postgresql.INET()),
            server_default="{}",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("proxy_instances", "ips")
