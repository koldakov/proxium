from datetime import datetime
from typing import TYPE_CHECKING, Annotated, ClassVar, Literal, Self

from fastapi import HTTPException, status
from pydantic import Field, StringConstraints, model_validator
from sqlalchemy import Result, Select, func, select
from sqlalchemy.exc import NoResultFound
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
)
from proxium.helpers import BaseSchema

if TYPE_CHECKING:
    from collections.abc import Iterable


def _check_unique_ids(ids: Iterable[int | None], /) -> None:
    given = [id_ for id_ in ids if id_ is not None]
    if len(given) != len(set(given)):
        raise ValueError("Ids must be unique.")


class UpdatePolicyConditionRequest(BaseSchema):
    """When the rule applies. Only `always` for now."""

    kind: Literal["always"] = "always"


class UpdatePolicyConnectionLimitRequest(BaseSchema):
    # Of a limit of the same rule to change it, none to add one.
    id: int | None = None
    scope: LimitScope
    max_connections: Annotated[
        int,
        Field(
            ge=1,
            le=2_147_483_647,
        ),
    ]


class UpdatePolicySpeedLimitRequest(BaseSchema):
    # Of a limit of the same rule to change it, none to add one.
    id: int | None = None
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


class UpdatePolicyRuleRequest(BaseSchema):
    # Of a rule of the same policy to change it, none to add one.
    id: int | None = None
    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=255,
        ),
    ]
    condition: UpdatePolicyConditionRequest = Field(
        default_factory=UpdatePolicyConditionRequest,
    )
    connection_limits: list[UpdatePolicyConnectionLimitRequest] = Field(
        default_factory=list,
        max_length=16,
    )
    speed_limits: list[UpdatePolicySpeedLimitRequest] = Field(
        default_factory=list,
        max_length=16,
    )

    @model_validator(mode="after")
    def _check_limit_ids(self) -> Self:
        _check_unique_ids(limit.id for limit in self.connection_limits)
        _check_unique_ids(limit.id for limit in self.speed_limits)
        return self


class UpdatePolicyRequest(BaseSchema):
    """Partial update: missing or null fields stay as they are. `rules` replaces the list, see the service."""

    name: Annotated[
        str | None,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=255,
        ),
    ] = None
    is_active: bool | None = None
    is_global: bool | None = None
    rules: (
        Annotated[
            list[UpdatePolicyRuleRequest],
            Field(
                max_length=64,
            ),
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def _check_rule_ids(self) -> Self:
        if self.rules is not None:
            _check_unique_ids(rule.id for rule in self.rules)
        return self


class UpdatePolicyConditionResponse(BaseSchema):
    kind: Literal["always"]


class UpdatePolicyConnectionLimitResponse(BaseSchema):
    id: int
    scope: LimitScope
    max_connections: int


class UpdatePolicySpeedLimitResponse(BaseSchema):
    id: int
    scope: LimitScope
    direction: Direction
    rate: int
    burst: int


class UpdatePolicyRuleResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            max_length=255,
        ),
    ]
    condition: UpdatePolicyConditionResponse
    connection_limits: list[UpdatePolicyConnectionLimitResponse]
    speed_limits: list[UpdatePolicySpeedLimitResponse]


class UpdatePolicyResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            max_length=255,
        ),
    ]
    is_active: bool
    is_global: bool
    rules: list[UpdatePolicyRuleResponse]
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class UpdatePolicyService(BaseUserAuthenticatedService[UpdatePolicyResponse]):
    """`rules` is the whole new list, in order. Rules and limits with an id change in place, without one are added,
    the ones left out are deleted.

    Keep the ids of what stays: a connection limit changed in place keeps counting the connections open under it.
    The proxy gets the change with its next lookup.
    """

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.POLICIES_CHANGE})

    id: int
    data: UpdatePolicyRequest

    def _get_policy_statement(self, *, lock: bool) -> Select[tuple[PolicyModel]]:
        # The API caps rules and limits, so the policy loads a bounded number of rows.
        rules = selectinload(PolicyModel.rules)
        statement: Select[tuple[PolicyModel]] = (
            select(PolicyModel)
            .where(PolicyModel.id == self.id)
            .options(
                rules.selectinload(PolicyRuleModel.connection_limits),
                rules.selectinload(PolicyRuleModel.speed_limits),
                rules.selectinload(PolicyRuleModel.traffic_quotas),
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            # Held till commit: two admins editing the rules take turns, neither loses the other's ids.
            statement = statement.with_for_update()

        return statement

    def _check_known(self, what: str, ids: Iterable[int | None], known: Iterable[int], /) -> None:
        unknown = {id_ for id_ in ids if id_ is not None} - set(known)
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{what} not found: {', '.join(map(str, sorted(unknown)))}.",
            )

    async def _update_connection_limits(
        self,
        rule: PolicyRuleModel,
        limits: list[UpdatePolicyConnectionLimitRequest],
        /,
    ) -> None:
        current = {limit.id: limit for limit in rule.connection_limits}
        self._check_known("Connection limits of the rule", (limit.id for limit in limits), current)

        kept = {limit.id for limit in limits}
        for limit in current.values():
            if limit.id not in kept:
                await self.session.delete(limit)

        for data in limits:
            if data.id is None:
                rule.connection_limits.append(
                    PolicyConnectionLimitModel(
                        scope=data.scope,
                        max_connections=data.max_connections,
                    ),
                )
                continue

            limit = current[data.id]
            limit.scope = data.scope
            limit.max_connections = data.max_connections

    async def _update_speed_limits(self, rule: PolicyRuleModel, limits: list[UpdatePolicySpeedLimitRequest], /) -> None:
        current = {limit.id: limit for limit in rule.speed_limits}
        self._check_known("Speed limits of the rule", (limit.id for limit in limits), current)

        kept = {limit.id for limit in limits}
        for limit in current.values():
            if limit.id not in kept:
                await self.session.delete(limit)

        for data in limits:
            if data.id is None:
                rule.speed_limits.append(
                    PolicySpeedLimitModel(
                        scope=data.scope,
                        direction=data.direction,
                        rate=data.rate,
                        burst=data.burst,
                    ),
                )
                continue

            limit = current[data.id]
            limit.scope = data.scope
            limit.direction = data.direction
            limit.rate = data.rate
            limit.burst = data.burst

    async def _delete_rule(self, rule: PolicyRuleModel, /) -> None:
        # Quotas aren't in the API yet, but a deleted rule takes them along.
        for limit in [*rule.connection_limits, *rule.speed_limits, *rule.traffic_quotas]:
            await self.session.delete(limit)
        await self.session.delete(rule)

    def _create_rule(self, position: int, data: UpdatePolicyRuleRequest, /) -> PolicyRuleModel:
        return PolicyRuleModel(
            policy_id=self.id,
            position=position,
            name=data.name,
            condition=data.condition.model_dump(mode="json"),
            connection_limits=[
                PolicyConnectionLimitModel(
                    scope=limit.scope,
                    max_connections=limit.max_connections,
                )
                for limit in data.connection_limits
            ],
            speed_limits=[
                PolicySpeedLimitModel(
                    scope=limit.scope,
                    direction=limit.direction,
                    rate=limit.rate,
                    burst=limit.burst,
                )
                for limit in data.speed_limits
            ],
        )

    async def _update_rules(self, policy: PolicyModel, rules: list[UpdatePolicyRuleRequest], /) -> None:
        current = {rule.id: rule for rule in policy.rules}
        self._check_known("Rules of the policy", (rule.id for rule in rules), current)

        kept = {rule.id for rule in rules}
        for rule in current.values():
            if rule.id not in kept:
                await self._delete_rule(rule)

        # Positions may swap: the unique check waits for the commit.
        for position, data in enumerate(rules):
            if data.id is None:
                self.session.add(self._create_rule(position, data))
                continue

            rule = current[data.id]
            rule.position = position
            rule.name = data.name
            rule.condition = data.condition.model_dump(mode="json")
            await self._update_connection_limits(rule, data.connection_limits)
            await self._update_speed_limits(rule, data.speed_limits)

        # Rules are part of the policy: it shows as changed even if only they did.
        policy.updated_at = func.now()  # type: ignore[assignment]  # The database clock, as for every timestamp.

    async def process(self, *args, **kwargs) -> UpdatePolicyResponse:
        result: Result[tuple[PolicyModel]] = await self.session.execute(self._get_policy_statement(lock=True))
        try:
            policy: PolicyModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policy not found.",
            ) from None

        if self.data.name is not None:
            policy.name = self.data.name
        if self.data.is_active is not None:
            policy.is_active = self.data.is_active
        if self.data.is_global is not None:
            policy.is_global = self.data.is_global
        if self.data.rules is not None:
            await self._update_rules(policy, self.data.rules)

        await self.session.commit()

        # Ids and timestamps come from the database, deleted rows leave the collections.
        result = await self.session.execute(self._get_policy_statement(lock=False))
        return UpdatePolicyResponse.model_validate(result.scalars().one())
