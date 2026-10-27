"""Add proxy instance permissions

Revision ID: d8b4f1a6c3e9
Revises: a3f9c2e7d415
Create Date: 2026-10-27 13:00:00.000000

"""

from typing import TYPE_CHECKING, Final

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "d8b4f1a6c3e9"
down_revision: str | None = "a3f9c2e7d415"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
    "policies.view",
    "policies.add",
    "policies.change",
    "policies.delete",
    "settings.view",
    "settings.change",
)
PROXY_INSTANCE_PERMISSIONS: Final[tuple[str, ...]] = (
    "proxy_instances.view",
    "proxy_instances.deregister",
)


def set_permissions(permissions: Sequence[str], /) -> None:
    """Replace the check of every permission column, named after the enum as `ChoiceField` creates it."""
    values = ", ".join(f"'{permission}'" for permission in permissions)
    for table in PERMISSION_TABLES:
        op.drop_constraint("permission", table, type_="check")
        op.create_check_constraint("permission", table, f"permission IN ({values})")


def upgrade() -> None:
    set_permissions([*OLD_PERMISSIONS, *PROXY_INSTANCE_PERMISSIONS])


def downgrade() -> None:
    # Users and groups lose the proxy instance permissions: the old check doesn't allow them.
    values = ", ".join(f"'{permission}'" for permission in PROXY_INSTANCE_PERMISSIONS)
    for table in PERMISSION_TABLES:
        op.execute(f"DELETE FROM {table} WHERE permission IN ({values})")  # noqa: S608, constants, not input.
    set_permissions(OLD_PERMISSIONS)
