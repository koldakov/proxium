"""Add policies

Revision ID: f4b8d2a6c1e3
Revises: e3a9c4f7b218
Create Date: 2026-10-05 22:00:00.000000

"""

from typing import TYPE_CHECKING, Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "f4b8d2a6c1e3"
down_revision: str | None = "e3a9c4f7b218"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UTC_TODAY: Final[str] = "(timezone('utc', now()))::date"

# As of this revision. A new choice later changes the check of every table with it.
LIMIT_SCOPES: Final[tuple[str, ...]] = (
    "connection",
    "identity",
    "client_ip",
    "target_host",
    "global",
)
DIRECTIONS: Final[tuple[str, ...]] = (
    "sent",
    "received",
    "both",
)
QUOTA_PERIODS: Final[tuple[str, ...]] = (
    "day",
    "month",
    "total",
)

# Tables with a permission column: their check lists every permission.
PERMISSION_TABLES: Final[tuple[str, ...]] = (
    "group_permissions",
    "user_permissions",
)
# As of the previous revision.
OLD_PERMISSIONS: Final[tuple[str, ...]] = (
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
POLICY_PERMISSIONS: Final[tuple[str, ...]] = (
    "policies.view",
    "policies.add",
    "policies.change",
    "policies.delete",
)

# Table, owner column, owner table: one assignment table per owner kind, the same shape.
LINK_TABLES: Final[tuple[tuple[str, str, str], ...]] = (
    ("basic_proxy_account_policies", "basic_proxy_account_id", "basic_proxy_accounts"),
    ("token_proxy_account_policies", "token_proxy_account_id", "token_proxy_accounts"),
    ("trusted_network_policies", "trusted_network_id", "trusted_networks"),
)


def choice_column(column: str, choices: Sequence[str], *, name: str) -> sa.Column:
    return sa.Column(
        column,
        sa.Enum(
            *choices,
            name=name,
            native_enum=False,
            create_constraint=True,
            length=16,
        ),
        nullable=False,
    )


def id_column() -> sa.Column:
    return sa.Column(
        "id",
        sa.Integer(),
        nullable=False,
    )


def rule_id_column() -> sa.Column:
    return sa.Column(
        "rule_id",
        sa.Integer(),
        nullable=False,
    )


def rule_foreign_key() -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["rule_id"],
        ["policy_rules.id"],
        ondelete="RESTRICT",
    )


def timestamp_columns() -> tuple[sa.Column, sa.Column]:
    return (
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
    )


def set_permissions(permissions: Sequence[str], /) -> None:
    """Replace the check of every permission column, named after the enum as `ChoiceField` creates it."""
    values = ", ".join(f"'{permission}'" for permission in permissions)
    for table in PERMISSION_TABLES:
        op.drop_constraint("permission", table, type_="check")
        op.create_check_constraint("permission", table, f"permission IN ({values})")


def upgrade() -> None:
    set_permissions([*OLD_PERMISSIONS, *POLICY_PERMISSIONS])
    op.create_table(
        "policies",
        id_column(),
        sa.Column(
            "name",
            sa.VARCHAR(length=255),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column(
            "is_global",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "starts_on",
            sa.Date(),
            server_default=sa.text(UTC_TODAY),
            nullable=False,
        ),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            nullable=False,
        ),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "policy_rules",
        id_column(),
        sa.Column(
            "policy_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.VARCHAR(length=255),
            nullable=False,
        ),
        sa.Column(
            "condition",
            postgresql.JSONB(),
            server_default=sa.text("""'{"kind": "always"}'::jsonb"""),
            nullable=False,
        ),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["policies.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "policy_id",
            "position",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_policy_rules_position_not_negative",
        ),
    )
    op.create_table(
        "policy_connection_limits",
        id_column(),
        rule_id_column(),
        choice_column("scope", LIMIT_SCOPES, name="limit_scope"),
        sa.Column(
            "max_connections",
            sa.Integer(),
            nullable=False,
        ),
        rule_foreign_key(),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "max_connections > 0",
            name="ck_policy_connection_limits_max_connections_positive",
        ),
    )
    op.create_table(
        "policy_speed_limits",
        id_column(),
        rule_id_column(),
        choice_column("scope", LIMIT_SCOPES, name="limit_scope"),
        choice_column("direction", DIRECTIONS, name="direction"),
        sa.Column(
            "rate",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "burst",
            sa.BigInteger(),
            nullable=False,
        ),
        rule_foreign_key(),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "rate > 0",
            name="ck_policy_speed_limits_rate_positive",
        ),
        sa.CheckConstraint(
            "burst > 0",
            name="ck_policy_speed_limits_burst_positive",
        ),
    )
    op.create_table(
        "policy_traffic_quotas",
        id_column(),
        rule_id_column(),
        choice_column("scope", LIMIT_SCOPES, name="limit_scope"),
        choice_column("direction", DIRECTIONS, name="direction"),
        sa.Column(
            "max_bytes",
            sa.BigInteger(),
            nullable=False,
        ),
        choice_column("period", QUOTA_PERIODS, name="quota_period"),
        sa.Column(
            "period_length",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        rule_foreign_key(),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "max_bytes > 0",
            name="ck_policy_traffic_quotas_max_bytes_positive",
        ),
        sa.CheckConstraint(
            "period_length > 0",
            name="ck_policy_traffic_quotas_period_length_positive",
        ),
    )
    for table, owner_column, owner_table in LINK_TABLES:
        op.create_table(
            table,
            id_column(),
            sa.Column(
                "policy_id",
                sa.Integer(),
                nullable=False,
            ),
            sa.Column(
                "starts_on",
                sa.Date(),
                server_default=sa.text(UTC_TODAY),
                nullable=False,
            ),
            sa.Column(
                owner_column,
                sa.Integer(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["policy_id"],
                ["policies.id"],
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                [owner_column],
                [f"{owner_table}.id"],
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                owner_column,
                "policy_id",
            ),
        )


def downgrade() -> None:
    for table, _, _ in reversed(LINK_TABLES):
        op.drop_table(table)
    op.drop_table("policy_traffic_quotas")
    op.drop_table("policy_speed_limits")
    op.drop_table("policy_connection_limits")
    op.drop_table("policy_rules")
    op.drop_table("policies")
    # Users and groups lose the policy permissions: the old check doesn't allow them.
    values = ", ".join(f"'{permission}'" for permission in POLICY_PERMISSIONS)
    for table in PERMISSION_TABLES:
        op.execute(f"DELETE FROM {table} WHERE permission IN ({values})")  # noqa: S608, constants, not input.
    set_permissions(OLD_PERMISSIONS)
