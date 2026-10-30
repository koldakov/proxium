"""Add proxy instances workers

Revision ID: b7e3a1d9c5f2
Revises: e6c2b9f4d1a8
Create Date: 2026-10-30 12:00:00.000000

"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "b7e3a1d9c5f2"
down_revision: str | None = "e6c2b9f4d1a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "proxy_instances",
        sa.Column(
            "workers",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )
    op.add_column(
        "proxy_instances",
        sa.Column(
            "running_workers",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("proxy_instances", "running_workers")
    op.drop_column("proxy_instances", "workers")
