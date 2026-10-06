"""Rename policies starts_on to global_starts_on

Revision ID: a7d3e5c1b904
Revises: f4b8d2a6c1e3
Create Date: 2026-10-06 21:00:00.000000

"""

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "a7d3e5c1b904"
down_revision: str | None = "f4b8d2a6c1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "policies",
        "starts_on",
        new_column_name="global_starts_on",
    )


def downgrade() -> None:
    op.alter_column(
        "policies",
        "global_starts_on",
        new_column_name="starts_on",
    )
