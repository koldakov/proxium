from datetime import UTC, date, datetime
from typing import Annotated, ClassVar, Literal

from pydantic import Field, StringConstraints
from sqlalchemy import Result, Select, select
from sqlalchemy.orm import selectinload

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import (
    Direction,
    LimitScope,
    Permission,
    PolicyConnectionLimitModel,
    PolicyModel,
    PolicyRuleModel,
    PolicySpeedLimitModel,
    PolicyTrafficQuotaModel,
    QuotaPeriod,
)
from proxium.helpers import BaseSchema


def _get_utc_today() -> date:
    # Traffic days are UTC: quota periods line up with them.
    return datetime.now(UTC).date()


class CreatePolicyConditionRequest(BaseSchema):
    """When the rule applies. Only `always` for now."""

    kind: Literal["always"] = "always"


class CreatePolicyConnectionLimitRequest(BaseSchema):
    scope: LimitScope
    max_connections: Annotated[
        int,
        Field(
            ge=1,
            le=2_147_483_647,
        ),
    ]


class CreatePolicySpeedLimitRequest(BaseSchema):
    scope: LimitScope
    direction: Direction
    # Bytes per second.
    rate: Annotated[
        int,
        Field(
            ge=1,
            le=9_223_372_036_854_775_807,
        ),
    ]
    # Bytes that go at once after a pause, e.g. `rate` for one second.
    burst: Annotated[
        int,
        Field(
            ge=1,
            le=9_223_372_036_854_775_807,
        ),
    ]


class CreatePolicyTrafficQuotaRequest(BaseSchema):
    direction: Direction
    # Bytes per period. Counted per account or trusted network.
    max_bytes: Annotated[
        int,
        Field(
            ge=1,
            le=9_223_372_036_854_775_807,
        ),
    ]
    period: QuotaPeriod
    # Days or months in one period, e.g. 30 days or 3 months. Ignored for `total`.
    period_length: Annotated[
        int,
        Field(
            ge=1,
            le=3650,
        ),
    ] = 1


class CreatePolicyRuleRequest(BaseSchema):
    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=255,
        ),
    ]
    condition: CreatePolicyConditionRequest = Field(
        default_factory=CreatePolicyConditionRequest,
    )
    connection_limits: list[CreatePolicyConnectionLimitRequest] = Field(
        default_factory=list,
        max_length=16,
    )
    speed_limits: list[CreatePolicySpeedLimitRequest] = Field(
        default_factory=list,
        max_length=16,
    )
    traffic_quotas: list[CreatePolicyTrafficQuotaRequest] = Field(
        default_factory=list,
        max_length=16,
    )


class CreatePolicyRequest(BaseSchema):
    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=255,
        ),
    ]
    is_active: bool = True
    is_global: bool = False
    # Quota periods of a global policy count from this day, UTC. An assigned one counts from its assignment's day.
    global_starts_on: date = Field(
        default_factory=_get_utc_today,
    )
    # In order: the first rule whose condition matches applies.
    rules: list[CreatePolicyRuleRequest] = Field(
        default_factory=list,
        max_length=64,
    )


class CreatePolicyConditionResponse(BaseSchema):
    kind: Literal["always"]


class CreatePolicyConnectionLimitResponse(BaseSchema):
    id: int
    scope: LimitScope
    max_connections: int


class CreatePolicySpeedLimitResponse(BaseSchema):
    id: int
    scope: LimitScope
    direction: Direction
    rate: int
    burst: int


class CreatePolicyTrafficQuotaResponse(BaseSchema):
    id: int
    direction: Direction
    max_bytes: int
    period: QuotaPeriod
    period_length: int


class CreatePolicyRuleResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            max_length=255,
        ),
    ]
    condition: CreatePolicyConditionResponse
    connection_limits: list[CreatePolicyConnectionLimitResponse]
    speed_limits: list[CreatePolicySpeedLimitResponse]
    traffic_quotas: list[CreatePolicyTrafficQuotaResponse]


class CreatePolicyResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            max_length=255,
        ),
    ]
    is_active: bool
    is_global: bool
    global_starts_on: date
    rules: list[CreatePolicyRuleResponse]
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class CreatePolicyService(BaseUserAuthenticatedService[CreatePolicyResponse]):
    """A global policy applies to every client at once, an other one once assigned."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.POLICIES_ADD})

    data: CreatePolicyRequest

    def _get_policy_statement(self, policy_id: int, /) -> Select[tuple[PolicyModel]]:
        # The request caps rules and limits, so the policy loads a bounded number of rows.
        rules = selectinload(PolicyModel.rules)
        return (
            select(PolicyModel)
            .where(PolicyModel.id == policy_id)
            .options(
                rules.selectinload(PolicyRuleModel.connection_limits),
                rules.selectinload(PolicyRuleModel.speed_limits),
                rules.selectinload(PolicyRuleModel.traffic_quotas),
            )
            .execution_options(populate_existing=True)
        )

    def _create_rule(self, position: int, rule: CreatePolicyRuleRequest, /) -> PolicyRuleModel:
        return PolicyRuleModel(
            position=position,
            name=rule.name,
            condition=rule.condition.model_dump(mode="json"),
            connection_limits=[
                PolicyConnectionLimitModel(
                    scope=limit.scope,
                    max_connections=limit.max_connections,
                )
                for limit in rule.connection_limits
            ],
            speed_limits=[
                PolicySpeedLimitModel(
                    scope=limit.scope,
                    direction=limit.direction,
                    rate=limit.rate,
                    burst=limit.burst,
                )
                for limit in rule.speed_limits
            ],
            traffic_quotas=[
                PolicyTrafficQuotaModel(
                    scope=LimitScope.IDENTITY,
                    direction=quota.direction,
                    max_bytes=quota.max_bytes,
                    period=quota.period,
                    period_length=quota.period_length,
                )
                for quota in rule.traffic_quotas
            ],
        )

    async def process(self, *args, **kwargs) -> CreatePolicyResponse:
        policy: PolicyModel = PolicyModel(
            name=self.data.name,
            is_active=self.data.is_active,
            is_global=self.data.is_global,
            global_starts_on=self.data.global_starts_on,
            created_by_id=self.user.id,
            rules=[self._create_rule(position, rule) for position, rule in enumerate(self.data.rules)],
        )
        self.session.add(policy)
        await self.session.commit()

        # Ids and timestamps come from the database.
        result: Result[tuple[PolicyModel]] = await self.session.execute(self._get_policy_statement(policy.id))
        return CreatePolicyResponse.model_validate(result.scalars().one())
