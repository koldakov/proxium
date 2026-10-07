"""Split settings cache_ttl per cache

Revision ID: b2c6e8f4a1d7
Revises: a7d3e5c1b904
Create Date: 2026-10-07 12:00:00.000000

"""

from typing import TYPE_CHECKING, Final

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "b2c6e8f4a1d7"
down_revision: str | None = "a7d3e5c1b904"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS: Final[tuple[str, ...]] = (
    "basic_account_cache_ttl",
    "basic_account_refusal_cache_ttl",
    "token_account_cache_ttl",
    "token_account_refusal_cache_ttl",
    "trusted_network_cache_ttl",
    "trusted_network_refusal_cache_ttl",
    "certificate_cache_ttl",
)


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column(
            "settings",
            sa.Column(
                column,
                sa.Float(),
                server_default="10",
                nullable=False,
            ),
        )
        op.create_check_constraint(
            f"ck_settings_{column}_positive",
            "settings",
            f"{column} > 0",
        )

    # Every cache keeps the TTL it had.
    op.execute(
        "UPDATE settings SET "
        "basic_account_cache_ttl = cache_ttl, "
        "basic_account_refusal_cache_ttl = cache_ttl, "
        "token_account_cache_ttl = cache_ttl, "
        "token_account_refusal_cache_ttl = cache_ttl, "
        "trusted_network_cache_ttl = cache_ttl, "
        "trusted_network_refusal_cache_ttl = cache_ttl, "
        "certificate_cache_ttl = cache_ttl",
    )

    op.drop_constraint(
        "ck_settings_cache_ttl_positive",
        "settings",
        type_="check",
    )
    op.drop_column("settings", "cache_ttl")


def downgrade() -> None:
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

    # The shortest: no change waits longer than it did.
    op.execute(
        "UPDATE settings SET cache_ttl = LEAST("
        "basic_account_cache_ttl, "
        "basic_account_refusal_cache_ttl, "
        "token_account_cache_ttl, "
        "token_account_refusal_cache_ttl, "
        "trusted_network_cache_ttl, "
        "trusted_network_refusal_cache_ttl, "
        "certificate_cache_ttl)",
    )

    for column in COLUMNS:
        op.drop_constraint(
            f"ck_settings_{column}_positive",
            "settings",
            type_="check",
        )
        op.drop_column("settings", column)
