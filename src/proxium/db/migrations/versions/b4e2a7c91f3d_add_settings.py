"""Add settings

Revision ID: b4e2a7c91f3d
Revises: 7b1e4c9d2a60
Create Date: 2026-10-04 12:00:00.000000

"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "b4e2a7c91f3d"
down_revision: str | None = "7b1e4c9d2a60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "guard_allow",
            sa.ARRAY(postgresql.CIDR()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "handshake_timeout",
            sa.Float(),
            server_default="10",
            nullable=False,
        ),
        sa.Column(
            "idle_timeout",
            sa.Float(),
            server_default="300",
            nullable=False,
        ),
        sa.Column(
            "connect_timeout",
            sa.Float(),
            server_default="10",
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
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "id = 1",
            name="ck_settings_single_row",
        ),
        sa.CheckConstraint(
            "handshake_timeout > 0",
            name="ck_settings_handshake_timeout_positive",
        ),
        sa.CheckConstraint(
            "idle_timeout > 0",
            name="ck_settings_idle_timeout_positive",
        ),
        sa.CheckConstraint(
            "connect_timeout > 0",
            name="ck_settings_connect_timeout_positive",
        ),
    )
    # The only row, with the defaults. The proxy doesn't start without it.
    op.execute("INSERT INTO settings (id) VALUES (1)")


def downgrade() -> None:
    op.drop_table("settings")
