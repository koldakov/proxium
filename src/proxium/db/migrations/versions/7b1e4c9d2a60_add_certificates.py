"""Add certificates

Revision ID: 7b1e4c9d2a60
Revises: 34461f5c7f98
Create Date: 2026-10-02 12:00:00.000000

"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "7b1e4c9d2a60"
down_revision: str | None = "34461f5c7f98"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "certificates",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "certificate",
            sa.TEXT(),
            nullable=False,
        ),
        sa.Column(
            "private_key",
            sa.TEXT(),
            nullable=False,
        ),
        sa.Column(
            "names",
            sa.ARRAY(sa.TEXT()),
            nullable=False,
        ),
        sa.Column(
            "fingerprint",
            sa.VARCHAR(length=64),
            nullable=False,
        ),
        sa.Column(
            "is_self_signed",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "not_valid_before",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "not_valid_after",
            sa.DateTime(timezone=True),
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
        sa.UniqueConstraint("fingerprint"),
    )
    op.create_index(
        "uq_certificates_active",
        "certificates",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_certificates_active",
        table_name="certificates",
        postgresql_where=sa.text("is_active"),
    )
    op.drop_table("certificates")
