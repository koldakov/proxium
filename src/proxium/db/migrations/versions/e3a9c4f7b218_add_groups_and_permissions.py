"""Add groups and permissions

Revision ID: e3a9c4f7b218
Revises: c8f1d3a5e902
Create Date: 2026-10-04 21:00:00.000000

"""

from typing import TYPE_CHECKING, Final

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "e3a9c4f7b218"
down_revision: str | None = "c8f1d3a5e902"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# As of this revision. A new permission later changes the check of both tables.
PERMISSIONS: Final[tuple[str, ...]] = (
    "basic_proxy_accounts.view",
    "basic_proxy_accounts.add",
    "basic_proxy_accounts.change",
    "basic_proxy_accounts.revoke",
    "token_proxy_accounts.view",
    "token_proxy_accounts.add",
    "token_proxy_accounts.change",
    "token_proxy_accounts.revoke",
    "trusted_networks.view",
    "trusted_networks.add",
    "trusted_networks.change",
    "trusted_networks.delete",
    "traffic.view",
    "outgoing_ips.view",
    "outgoing_ips.add",
    "outgoing_ips.change",
    "outgoing_ips.delete",
    "certificates.view",
    "certificates.add",
    "certificates.delete",
    "certificates.activate",
    "users.view",
    "users.add",
    "users.change",
    "groups.view",
    "groups.add",
    "groups.change",
    "groups.delete",
    "settings.view",
    "settings.change",
)


def permission_column() -> sa.Column:
    return sa.Column(
        "permission",
        sa.Enum(
            *PERMISSIONS,
            name="permission",
            native_enum=False,
            create_constraint=True,
            length=64,
        ),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.VARCHAR(length=150),
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
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "group_permissions",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "group_id",
            sa.Integer(),
            nullable=False,
        ),
        permission_column(),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "group_id",
            "permission",
        ),
    )
    op.create_table(
        "user_groups",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "group_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "group_id",
        ),
    )
    op.create_table(
        "user_permissions",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
        ),
        permission_column(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "permission",
        ),
    )


def downgrade() -> None:
    op.drop_table("user_permissions")
    op.drop_table("user_groups")
    op.drop_table("group_permissions")
    op.drop_table("groups")
