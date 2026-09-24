"""Add users

Revision ID: 1a892db2ce5d
Revises:
Create Date: 2026-09-24 20:23:40.781712

"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "1a892db2ce5d"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "email",
            sa.VARCHAR(length=255),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.VARCHAR(length=150),
            nullable=False,
        ),
        sa.Column(
            "surname",
            sa.VARCHAR(length=150),
            nullable=False,
        ),
        sa.Column(
            "password",
            sa.VARCHAR(length=255),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default="false",
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
        sa.UniqueConstraint("email"),
    )


def downgrade() -> None:
    op.drop_table("users")
