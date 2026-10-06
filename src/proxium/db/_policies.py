from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar, Final

from sqlalchemy import VARCHAR, BigInteger, CheckConstraint, Date, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from ._base import BaseModel, BaseTimestampModel
from ._fields import ChoiceField

if TYPE_CHECKING:
    # SQLAlchemy finds relationship targets by name in its registry, a runtime import would be circular.
    from ._users import UserModel  # noqa: TC004

# Today in UTC, as traffic days are: quota periods line up with them whatever the database time zone.
UTC_TODAY: Final[str] = "(timezone('utc', now()))::date"
# A rule without a condition: it always matches.
ALWAYS: Final[dict[str, Any]] = {"kind": "always"}


class LimitScope(StrEnum):
    """What a limit is counted over: connections with the same value share it."""

    # Each connection on its own.
    CONNECTION = "connection"
    # An account or a trusted network: all its connections together.
    IDENTITY = "identity"
    # The IP the client connects from.
    CLIENT_IP = "client_ip"
    # The host the client connects to, e.g. one site everybody hits.
    TARGET_HOST = "target_host"
    # The whole proxy.
    GLOBAL = "global"


class Direction(StrEnum):
    # From the client to the target: uploads.
    SENT = "sent"
    # From the target to the client: downloads.
    RECEIVED = "received"
    BOTH = "both"


class QuotaPeriod(StrEnum):
    DAY = "day"
    MONTH = "month"
    # Never resets: one allowance since the start.
    TOTAL = "total"


class PolicyModel(BaseTimestampModel):
    """A named set of rules on how clients may use the proxy, e.g. a plan. Assigned to accounts and trusted networks.

    A client gets every active policy assigned to it and every active global one: all of them apply at once.
    """

    __tablename__ = "policies"

    # A label for people, e.g. "Basic 50 GB".
    name: Mapped[str] = mapped_column(
        VARCHAR(length=255),
    )
    # False turns the policy off for everyone without losing it.
    is_active: Mapped[bool] = mapped_column(
        default=True,
        server_default="true",
    )
    # Applies to every client without assigning it, e.g. a speed limit for the whole proxy at peak hours.
    is_global: Mapped[bool] = mapped_column(
        default=False,
        server_default="false",
    )
    # Quota periods of a global policy count from this day. Unused by others: an assigned policy counts from the day
    # of its assignment.
    global_starts_on: Mapped[date] = mapped_column(
        Date(),
        server_default=text(UTC_TODAY),
    )
    # The admin who created the policy. An admin with policies can't be deleted.
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
    )

    created_by: Mapped[UserModel] = relationship(
        back_populates="policies",
    )
    # In order: the first rule whose condition matches is the one that applies. The service deleting a policy
    # removes its rules and assignments first.
    rules: Mapped[list[PolicyRuleModel]] = relationship(
        back_populates="policy",
        order_by="PolicyRuleModel.position",
        passive_deletes="all",
    )


class PolicyConnectionLimitModel(BaseModel):
    """At most `max_connections` open connections per scope value, more are refused."""

    __tablename__ = "policy_connection_limits"
    __table_args__ = (
        CheckConstraint(
            "max_connections > 0",
            name="ck_policy_connection_limits_max_connections_positive",
        ),
    )

    rule_id: Mapped[int] = mapped_column(
        ForeignKey(
            "policy_rules.id",
            ondelete="RESTRICT",
        ),
    )
    scope: Mapped[LimitScope] = mapped_column(
        ChoiceField(
            LimitScope,
            name="limit_scope",
            length=16,
        ),
    )
    max_connections: Mapped[int] = mapped_column()


class PolicySpeedLimitModel(BaseModel):
    """At most `rate` bytes per second per scope value, shared by its connections. Slows them down, never cuts.

    `both` limits each way separately: uploads don't slow downloads. Up to `burst` bytes go at once after a pause.
    """

    __tablename__ = "policy_speed_limits"
    __table_args__ = (
        CheckConstraint(
            "rate > 0",
            name="ck_policy_speed_limits_rate_positive",
        ),
        CheckConstraint(
            "burst > 0",
            name="ck_policy_speed_limits_burst_positive",
        ),
    )

    rule_id: Mapped[int] = mapped_column(
        ForeignKey(
            "policy_rules.id",
            ondelete="RESTRICT",
        ),
    )
    scope: Mapped[LimitScope] = mapped_column(
        ChoiceField(
            LimitScope,
            name="limit_scope",
            length=16,
        ),
    )
    direction: Mapped[Direction] = mapped_column(
        ChoiceField(
            Direction,
            name="direction",
            length=16,
        ),
    )
    rate: Mapped[int] = mapped_column(
        BigInteger(),
    )
    burst: Mapped[int] = mapped_column(
        BigInteger(),
    )


class PolicyTrafficQuotaModel(BaseModel):
    """At most `max_bytes` per period per scope value. Past it new connections are refused and open ones are cut.

    Periods are `period_length` days or months long, counted from the policy's or the assignment's start day.
    `both` counts the two ways together. To slow down instead of cutting, use a rule with a speed limit.
    """

    __tablename__ = "policy_traffic_quotas"
    __table_args__ = (
        CheckConstraint(
            "max_bytes > 0",
            name="ck_policy_traffic_quotas_max_bytes_positive",
        ),
        CheckConstraint(
            "period_length > 0",
            name="ck_policy_traffic_quotas_period_length_positive",
        ),
    )

    rule_id: Mapped[int] = mapped_column(
        ForeignKey(
            "policy_rules.id",
            ondelete="RESTRICT",
        ),
    )
    scope: Mapped[LimitScope] = mapped_column(
        ChoiceField(
            LimitScope,
            name="limit_scope",
            length=16,
        ),
    )
    direction: Mapped[Direction] = mapped_column(
        ChoiceField(
            Direction,
            name="direction",
            length=16,
        ),
    )
    max_bytes: Mapped[int] = mapped_column(
        BigInteger(),
    )
    period: Mapped[QuotaPeriod] = mapped_column(
        ChoiceField(
            QuotaPeriod,
            name="quota_period",
            length=16,
        ),
    )
    # Days or months in one period, e.g. 30 days or 3 months. Ignored for `total`.
    period_length: Mapped[int] = mapped_column(
        default=1,
        server_default="1",
    )


class PolicyRuleModel(BaseTimestampModel):
    """When `condition` matches, its limits apply. A rule may have any number of limits of each kind.

    The service deleting a rule removes its limits first.
    """

    __tablename__ = "policy_rules"
    __table_args__ = (
        # Deferred: reordering swaps positions within one transaction.
        UniqueConstraint(
            "policy_id",
            "position",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "position >= 0",
            name="ck_policy_rules_position_not_negative",
        ),
    )

    policy_id: Mapped[int] = mapped_column(
        ForeignKey(
            "policies.id",
            ondelete="RESTRICT",
        ),
    )
    # Lower first.
    position: Mapped[int] = mapped_column()
    # A label for people, e.g. "Saturday peak".
    name: Mapped[str] = mapped_column(
        VARCHAR(length=255),
    )
    # When the rule applies, a tree of blocks by `kind`, e.g. a schedule or all/any/not of other blocks.
    condition: Mapped[dict[str, Any]] = mapped_column(
        JSONB(),
        default=lambda: dict(ALWAYS),
        server_default=text("""'{"kind": "always"}'::jsonb"""),
    )

    policy: Mapped[PolicyModel] = relationship(
        back_populates="rules",
    )
    connection_limits: Mapped[list[PolicyConnectionLimitModel]] = relationship(
        order_by="PolicyConnectionLimitModel.id",
        passive_deletes="all",
    )
    speed_limits: Mapped[list[PolicySpeedLimitModel]] = relationship(
        order_by="PolicySpeedLimitModel.id",
        passive_deletes="all",
    )
    traffic_quotas: Mapped[list[PolicyTrafficQuotaModel]] = relationship(
        order_by="PolicyTrafficQuotaModel.id",
        passive_deletes="all",
    )


class BasePolicyLinkModel(BaseModel):
    """A policy assigned to one owner. Each owner kind has its own table, so the owner is a real foreign key.

    The service deleting a policy removes its assignments first.
    """

    __abstract__ = True

    # The foreign key column of the owner.
    owner_column: ClassVar[str]

    policy_id: Mapped[int] = mapped_column(
        ForeignKey(
            "policies.id",
            ondelete="RESTRICT",
        ),
    )
    # Quota periods count from this day, e.g. the day the client paid: each owner gets its own billing cycle.
    starts_on: Mapped[date] = mapped_column(
        Date(),
        server_default=text(UTC_TODAY),
    )

    # One row per owner and policy.
    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple[Any, ...]:
        return (
            UniqueConstraint(
                cls.owner_column,
                "policy_id",
            ),
        )


class BasicProxyAccountPolicyModel(BasePolicyLinkModel):
    __tablename__ = "basic_proxy_account_policies"

    owner_column: ClassVar[str] = "basic_proxy_account_id"

    basic_proxy_account_id: Mapped[int] = mapped_column(
        ForeignKey(
            "basic_proxy_accounts.id",
            ondelete="RESTRICT",
        ),
    )


class TokenProxyAccountPolicyModel(BasePolicyLinkModel):
    __tablename__ = "token_proxy_account_policies"

    owner_column: ClassVar[str] = "token_proxy_account_id"

    token_proxy_account_id: Mapped[int] = mapped_column(
        ForeignKey(
            "token_proxy_accounts.id",
            ondelete="RESTRICT",
        ),
    )


class TrustedNetworkPolicyModel(BasePolicyLinkModel):
    __tablename__ = "trusted_network_policies"

    owner_column: ClassVar[str] = "trusted_network_id"

    trusted_network_id: Mapped[int] = mapped_column(
        ForeignKey(
            "trusted_networks.id",
            ondelete="RESTRICT",
        ),
    )
