"""Add settings cache_ttl

Revision ID: c8f1d3a5e902
Revises: b4e2a7c91f3d
Create Date: 2026-10-04 18:00:00.000000

"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "c8f1d3a5e902"
down_revision: str | None = "b4e2a7c91f3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column(
            "cache_ttl",
            sa.Float(),
            server_default="10",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_settings_cache_ttl_positive",
        "settings",
        "cache_ttl > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_settings_cache_ttl_positive",
        "settings",
        type_="check",
    )
    op.drop_column("settings", "cache_ttl")
