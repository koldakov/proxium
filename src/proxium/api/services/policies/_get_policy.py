from datetime import date, datetime
from typing import Annotated, ClassVar, Literal

from fastapi import HTTPException, status
from pydantic import Field
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import selectinload

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Direction, LimitScope, Permission, PolicyModel, PolicyRuleModel, QuotaPeriod
from proxium.helpers import BaseSchema


class GetPolicyConditionResponse(BaseSchema):
    kind: Literal["always"]


class GetPolicyConnectionLimitResponse(BaseSchema):
    id: int
    scope: LimitScope
    max_connections: int


class GetPolicySpeedLimitResponse(BaseSchema):
    id: int
    scope: LimitScope
    direction: Direction
    rate: int
    burst: int


class GetPolicyTrafficQuotaResponse(BaseSchema):
    id: int
    direction: Direction
    max_bytes: int
    period: QuotaPeriod
    period_length: int


class GetPolicyRuleResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            max_length=255,
        ),
    ]
    condition: GetPolicyConditionResponse
    connection_limits: list[GetPolicyConnectionLimitResponse]
    speed_limits: list[GetPolicySpeedLimitResponse]
    traffic_quotas: list[GetPolicyTrafficQuotaResponse]


class GetPolicyResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            max_length=255,
        ),
    ]
    is_active: bool
    is_global: bool
    # Quota periods of a global policy count from this day, UTC.
    global_starts_on: date
    # In order: the first rule whose condition matches applies.
    rules: list[GetPolicyRuleResponse]
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class GetPolicyService(BaseUserAuthenticatedService[GetPolicyResponse]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.POLICIES_VIEW})

    id: int

    @property
    def _get_policy_statement(self) -> Select[tuple[PolicyModel]]:
        # The API caps rules and limits, so the policy loads a bounded number of rows.
        rules = selectinload(PolicyModel.rules)
        return (
            select(PolicyModel)
            .where(PolicyModel.id == self.id)
            .options(
                rules.selectinload(PolicyRuleModel.connection_limits),
                rules.selectinload(PolicyRuleModel.speed_limits),
                rules.selectinload(PolicyRuleModel.traffic_quotas),
            )
        )

    async def process(self, *args, **kwargs) -> GetPolicyResponse:
        result: Result[tuple[PolicyModel]] = await self.session.execute(self._get_policy_statement)
        try:
            policy: PolicyModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policy not found.",
            ) from None

        return GetPolicyResponse.model_validate(policy)
