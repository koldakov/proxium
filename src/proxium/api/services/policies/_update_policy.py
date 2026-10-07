from datetime import date, datetime, time
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Final, Literal, Self

from fastapi import HTTPException, status
from pydantic import Field, IPvAnyNetwork, StringConstraints, model_validator
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
    PolicyTrafficQuotaModel,
    QuotaPeriod,
)
from proxium.helpers import BaseSchema
from proxium.policies import DEFAULT_CONDITION_PARSER, InvalidConditionError

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


def _check_unique_ids(ids: Iterable[int | None], /) -> None:
    given = [id_ for id_ in ids if id_ is not None]
    if len(given) != len(set(given)):
        raise ValueError("Ids must be unique.")


# Bounded: the proxy checks a condition on every connection.
_MAX_CONDITION_BLOCKS: Final[int] = 64


def _count_condition_blocks(condition: Mapping[str, Any], /) -> int:
    children = [*condition.get("conditions", ())]
    if "condition" in condition:
        children.append(condition["condition"])
    return 1 + sum(_count_condition_blocks(child) for child in children)


# Declared before its blocks: they hold one another. Checked by the proxy's parser too, see the rule.
type UpdatePolicyConditionRequest = Annotated[
    UpdatePolicyAlwaysConditionRequest
    | UpdatePolicyAllConditionRequest
    | UpdatePolicyAnyConditionRequest
    | UpdatePolicyNotConditionRequest
    | UpdatePolicyTargetHostConditionRequest
    | UpdatePolicyTargetNetworkConditionRequest
    | UpdatePolicyTargetPortConditionRequest
    | UpdatePolicyProtocolConditionRequest
    | UpdatePolicyClientNetworkConditionRequest
    | UpdatePolicyEncryptedConditionRequest
    | UpdatePolicyScheduleConditionRequest,
    Field(
        discriminator="kind",
    ),
]


class UpdatePolicyAlwaysConditionRequest(BaseSchema):
    """Matches every connection: a rule for everything the rules above it left."""

    kind: Literal["always"] = "always"


class UpdatePolicyAllConditionRequest(BaseSchema):
    """Every one of `conditions` matches."""

    kind: Literal["all"]
    conditions: Annotated[
        list[UpdatePolicyConditionRequest],
        Field(
            min_length=1,
            max_length=_MAX_CONDITION_BLOCKS,
        ),
    ]


class UpdatePolicyAnyConditionRequest(BaseSchema):
    """At least one of `conditions` matches."""

    kind: Literal["any"]
    conditions: Annotated[
        list[UpdatePolicyConditionRequest],
        Field(
            min_length=1,
            max_length=_MAX_CONDITION_BLOCKS,
        ),
    ]


class UpdatePolicyNotConditionRequest(BaseSchema):
    """Matches when `condition` doesn't."""

    kind: Literal["not"]
    condition: UpdatePolicyConditionRequest


class UpdatePolicyTargetHostConditionRequest(BaseSchema):
    """The target is one of `domains` or their subdomains, by the name the client sent."""

    kind: Literal["target_host"]
    domains: Annotated[
        list[
            Annotated[
                str,
                StringConstraints(
                    strip_whitespace=True,
                    min_length=1,
                    max_length=253,
                ),
            ]
        ],
        Field(
            min_length=1,
            max_length=256,
        ),
    ]


class UpdatePolicyTargetNetworkConditionRequest(BaseSchema):
    """The client asked for an IP in one of `networks`. A target given by name doesn't match."""

    kind: Literal["target_network"]
    networks: Annotated[
        list[IPvAnyNetwork],
        Field(
            min_length=1,
            max_length=256,
        ),
    ]


class UpdatePolicyPortRangeRequest(BaseSchema):
    # Both included, e.g. 443 to 443 for one port.
    first: Annotated[
        int,
        Field(
            ge=1,
            le=65535,
        ),
    ]
    last: Annotated[
        int,
        Field(
            ge=1,
            le=65535,
        ),
    ]


class UpdatePolicyTargetPortConditionRequest(BaseSchema):
    """The target port is in one of `ports`."""

    kind: Literal["target_port"]
    ports: Annotated[
        list[UpdatePolicyPortRangeRequest],
        Field(
            min_length=1,
            max_length=256,
        ),
    ]


class UpdatePolicyProtocolConditionRequest(BaseSchema):
    """The client came in over one of `protocols`."""

    kind: Literal["protocol"]
    # As the proxy names them: plain HTTP, HTTPS tunnels by CONNECT, SOCKS5.
    protocols: Annotated[
        list[Literal["http", "http-connect", "socks5"]],
        Field(
            min_length=1,
            max_length=3,
        ),
    ]


class UpdatePolicyClientNetworkConditionRequest(BaseSchema):
    """The client connects from an IP in one of `networks`."""

    kind: Literal["client_network"]
    networks: Annotated[
        list[IPvAnyNetwork],
        Field(
            min_length=1,
            max_length=256,
        ),
    ]


class UpdatePolicyEncryptedConditionRequest(BaseSchema):
    """The client came over TLS."""

    kind: Literal["encrypted"]


class UpdatePolicyScheduleConditionRequest(BaseSchema):
    """From `start` till `end` on `days`, in `timezone`. `end` before `start` runs past midnight, equal is all day."""

    kind: Literal["schedule"]
    # ISO weekdays: 1 is Monday.
    days: Annotated[
        list[
            Annotated[
                int,
                Field(
                    ge=1,
                    le=7,
                ),
            ]
        ],
        Field(
            min_length=1,
            max_length=7,
        ),
    ]
    start: time
    end: time
    # IANA, e.g. Europe/Berlin.
    timezone: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=64,
        ),
    ]


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


class UpdatePolicyTrafficQuotaRequest(BaseSchema):
    # Of a quota of the same rule to change it, none to add one.
    id: int | None = None
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
    # When the rule applies, by default always.
    condition: UpdatePolicyConditionRequest = Field(
        default_factory=UpdatePolicyAlwaysConditionRequest,
    )
    connection_limits: list[UpdatePolicyConnectionLimitRequest] = Field(
        default_factory=list,
        max_length=16,
    )
    speed_limits: list[UpdatePolicySpeedLimitRequest] = Field(
        default_factory=list,
        max_length=16,
    )
    traffic_quotas: list[UpdatePolicyTrafficQuotaRequest] = Field(
        default_factory=list,
        max_length=16,
    )

    @model_validator(mode="after")
    def _check_limit_ids(self) -> Self:
        _check_unique_ids(limit.id for limit in self.connection_limits)
        _check_unique_ids(limit.id for limit in self.speed_limits)
        _check_unique_ids(quota.id for quota in self.traffic_quotas)
        return self

    @model_validator(mode="after")
    def _check_condition(self) -> Self:
        condition = self.condition.model_dump(mode="json")
        if _count_condition_blocks(condition) > _MAX_CONDITION_BLOCKS:
            raise ValueError(f"A condition has at most {_MAX_CONDITION_BLOCKS} blocks.")
        # By the proxy's own parser: what's saved, the proxy can build.
        try:
            DEFAULT_CONDITION_PARSER.parse(condition)
        except InvalidConditionError as err:
            raise ValueError(f"Condition: {err}") from err
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
    # Quota periods of a global policy count from this day, UTC.
    global_starts_on: date | None = None
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


# Declared before its blocks: they hold one another.
type UpdatePolicyConditionResponse = Annotated[
    UpdatePolicyAlwaysConditionResponse
    | UpdatePolicyAllConditionResponse
    | UpdatePolicyAnyConditionResponse
    | UpdatePolicyNotConditionResponse
    | UpdatePolicyTargetHostConditionResponse
    | UpdatePolicyTargetNetworkConditionResponse
    | UpdatePolicyTargetPortConditionResponse
    | UpdatePolicyProtocolConditionResponse
    | UpdatePolicyClientNetworkConditionResponse
    | UpdatePolicyEncryptedConditionResponse
    | UpdatePolicyScheduleConditionResponse,
    Field(
        discriminator="kind",
    ),
]


class UpdatePolicyAlwaysConditionResponse(BaseSchema):
    kind: Literal["always"]


class UpdatePolicyAllConditionResponse(BaseSchema):
    kind: Literal["all"]
    conditions: list[UpdatePolicyConditionResponse]


class UpdatePolicyAnyConditionResponse(BaseSchema):
    kind: Literal["any"]
    conditions: list[UpdatePolicyConditionResponse]


class UpdatePolicyNotConditionResponse(BaseSchema):
    kind: Literal["not"]
    condition: UpdatePolicyConditionResponse


class UpdatePolicyTargetHostConditionResponse(BaseSchema):
    kind: Literal["target_host"]
    domains: list[str]


class UpdatePolicyTargetNetworkConditionResponse(BaseSchema):
    kind: Literal["target_network"]
    networks: list[IPvAnyNetwork]


class UpdatePolicyPortRangeResponse(BaseSchema):
    first: int
    last: int


class UpdatePolicyTargetPortConditionResponse(BaseSchema):
    kind: Literal["target_port"]
    ports: list[UpdatePolicyPortRangeResponse]


class UpdatePolicyProtocolConditionResponse(BaseSchema):
    kind: Literal["protocol"]
    protocols: list[str]


class UpdatePolicyClientNetworkConditionResponse(BaseSchema):
    kind: Literal["client_network"]
    networks: list[IPvAnyNetwork]


class UpdatePolicyEncryptedConditionResponse(BaseSchema):
    kind: Literal["encrypted"]


class UpdatePolicyScheduleConditionResponse(BaseSchema):
    kind: Literal["schedule"]
    days: list[int]
    start: time
    end: time
    timezone: str


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


class UpdatePolicyTrafficQuotaResponse(BaseSchema):
    id: int
    direction: Direction
    max_bytes: int
    period: QuotaPeriod
    period_length: int


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
    traffic_quotas: list[UpdatePolicyTrafficQuotaResponse]


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
    global_starts_on: date
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

    async def _update_traffic_quotas(
        self,
        rule: PolicyRuleModel,
        quotas: list[UpdatePolicyTrafficQuotaRequest],
        /,
    ) -> None:
        current = {quota.id: quota for quota in rule.traffic_quotas}
        self._check_known("Traffic quotas of the rule", (quota.id for quota in quotas), current)

        kept = {quota.id for quota in quotas}
        for quota in current.values():
            if quota.id not in kept:
                await self.session.delete(quota)

        for data in quotas:
            if data.id is None:
                rule.traffic_quotas.append(
                    PolicyTrafficQuotaModel(
                        scope=LimitScope.IDENTITY,
                        direction=data.direction,
                        max_bytes=data.max_bytes,
                        period=data.period,
                        period_length=data.period_length,
                    ),
                )
                continue

            quota = current[data.id]
            quota.direction = data.direction
            quota.max_bytes = data.max_bytes
            quota.period = data.period
            quota.period_length = data.period_length

    async def _delete_rule(self, rule: PolicyRuleModel, /) -> None:
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
            traffic_quotas=[
                PolicyTrafficQuotaModel(
                    scope=LimitScope.IDENTITY,
                    direction=quota.direction,
                    max_bytes=quota.max_bytes,
                    period=quota.period,
                    period_length=quota.period_length,
                )
                for quota in data.traffic_quotas
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
            await self._update_traffic_quotas(rule, data.traffic_quotas)

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
        if self.data.global_starts_on is not None:
            policy.global_starts_on = self.data.global_starts_on
        if self.data.rules is not None:
            await self._update_rules(policy, self.data.rules)

        await self.session.commit()

        # Ids and timestamps come from the database, deleted rows leave the collections.
        result = await self.session.execute(self._get_policy_statement(lock=False))
        return UpdatePolicyResponse.model_validate(result.scalars().one())
