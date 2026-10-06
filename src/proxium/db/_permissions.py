from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import VARCHAR, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from ._base import BaseModel, BaseTimestampModel
from ._fields import ChoiceField


class Permission(StrEnum):
    """What a user may do in the API, `<resource>.<action>`. Superusers have them all.

    The code checks them, so the list lives here, not in a table.
    """

    BASIC_PROXY_ACCOUNTS_VIEW = "basic_proxy_accounts.view"
    BASIC_PROXY_ACCOUNTS_ADD = "basic_proxy_accounts.add"
    BASIC_PROXY_ACCOUNTS_CHANGE = "basic_proxy_accounts.change"
    BASIC_PROXY_ACCOUNTS_REVOKE = "basic_proxy_accounts.revoke"

    TOKEN_PROXY_ACCOUNTS_VIEW = "token_proxy_accounts.view"  # noqa: S105, a permission, not a secret.
    TOKEN_PROXY_ACCOUNTS_ADD = "token_proxy_accounts.add"  # noqa: S105, a permission, not a secret.
    TOKEN_PROXY_ACCOUNTS_CHANGE = "token_proxy_accounts.change"  # noqa: S105, a permission, not a secret.
    TOKEN_PROXY_ACCOUNTS_REVOKE = "token_proxy_accounts.revoke"  # noqa: S105, a permission, not a secret.

    TRUSTED_NETWORKS_VIEW = "trusted_networks.view"
    TRUSTED_NETWORKS_ADD = "trusted_networks.add"
    TRUSTED_NETWORKS_CHANGE = "trusted_networks.change"
    TRUSTED_NETWORKS_DELETE = "trusted_networks.delete"

    TRAFFIC_VIEW = "traffic.view"

    OUTGOING_IPS_VIEW = "outgoing_ips.view"
    OUTGOING_IPS_ADD = "outgoing_ips.add"
    OUTGOING_IPS_CHANGE = "outgoing_ips.change"
    OUTGOING_IPS_DELETE = "outgoing_ips.delete"

    CERTIFICATES_VIEW = "certificates.view"
    CERTIFICATES_ADD = "certificates.add"
    CERTIFICATES_DELETE = "certificates.delete"
    CERTIFICATES_ACTIVATE = "certificates.activate"

    USERS_VIEW = "users.view"
    USERS_ADD = "users.add"
    USERS_CHANGE = "users.change"

    GROUPS_VIEW = "groups.view"
    GROUPS_ADD = "groups.add"
    GROUPS_CHANGE = "groups.change"
    GROUPS_DELETE = "groups.delete"

    POLICIES_VIEW = "policies.view"
    POLICIES_ADD = "policies.add"
    POLICIES_CHANGE = "policies.change"
    POLICIES_DELETE = "policies.delete"

    SETTINGS_VIEW = "settings.view"
    SETTINGS_CHANGE = "settings.change"


class GroupModel(BaseTimestampModel):
    """A named set of permissions. Its users have them all."""

    __tablename__ = "groups"

    name: Mapped[str] = mapped_column(
        VARCHAR(length=150),
        unique=True,
    )

    permissions: Mapped[list[GroupPermissionModel]] = relationship(
        back_populates="group",
        passive_deletes="all",
    )


class GroupPermissionModel(BaseModel):
    __tablename__ = "group_permissions"
    __table_args__ = (
        UniqueConstraint(
            "group_id",
            "permission",
        ),
    )

    group_id: Mapped[int] = mapped_column(
        ForeignKey(
            "groups.id",
            ondelete="RESTRICT",
        ),
    )
    permission: Mapped[Permission] = mapped_column(
        ChoiceField(
            Permission,
            name="permission",
            length=64,
        ),
    )

    group: Mapped[GroupModel] = relationship(
        back_populates="permissions",
    )


class BaseUserLinkModel(BaseModel):
    """A row of a user's access. The service deleting a group removes its rows first."""

    __abstract__ = True

    # The column of what the user gets, one row per user and value.
    value_column: ClassVar[str]

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
    )

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple[Any, ...]:
        return (
            UniqueConstraint(
                "user_id",
                cls.value_column,
            ),
        )


class UserGroupModel(BaseUserLinkModel):
    __tablename__ = "user_groups"

    value_column: ClassVar[str] = "group_id"

    group_id: Mapped[int] = mapped_column(
        ForeignKey(
            "groups.id",
            ondelete="RESTRICT",
        ),
    )


class UserPermissionModel(BaseUserLinkModel):
    """A permission given to the user directly, besides the ones of the groups."""

    __tablename__ = "user_permissions"

    value_column: ClassVar[str] = "permission"

    permission: Mapped[Permission] = mapped_column(
        ChoiceField(
            Permission,
            name="permission",
            length=64,
        ),
    )
