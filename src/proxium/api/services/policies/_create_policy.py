from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Final, Literal, Self

from pydantic import Field, IPvAnyNetwork, StringConstraints, model_validator
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
from proxium.policies import DEFAULT_CONDITION_PARSER, InvalidConditionError

if TYPE_CHECKING:
    from collections.abc import Mapping


def _get_utc_today() -> date:
    # Traffic days are UTC: quota periods line up with them.
    return datetime.now(UTC).date()


# Bounded: the proxy checks a condition on every connection.
_MAX_CONDITION_BLOCKS: Final[int] = 64


def _count_condition_blocks(condition: Mapping[str, Any], /) -> int:
    children = [*condition.get("conditions", ())]
    if "condition" in condition:
        children.append(condition["condition"])
    return 1 + sum(_count_condition_blocks(child) for child in children)


# Declared before its blocks: they hold one another. Checked by the proxy's parser too, see the rule.
type CreatePolicyConditionRequest = Annotated[
    CreatePolicyAlwaysConditionRequest
    | CreatePolicyAllConditionRequest
    | CreatePolicyAnyConditionRequest
    | CreatePolicyNotConditionRequest
    | CreatePolicyTargetHostConditionRequest
    | CreatePolicyTargetNetworkConditionRequest
    | CreatePolicyTargetPortConditionRequest
    | CreatePolicyProtocolConditionRequest
    | CreatePolicyClientNetworkConditionRequest
    | CreatePolicyEncryptedConditionRequest
    | CreatePolicyScheduleConditionRequest,
    Field(
        discriminator="kind",
    ),
]


class CreatePolicyAlwaysConditionRequest(BaseSchema):
    """Matches every connection: a rule for everything the rules above it left."""

    kind: Literal["always"] = "always"


class CreatePolicyAllConditionRequest(BaseSchema):
    """Every one of `conditions` matches."""

    kind: Literal["all"]
    conditions: Annotated[
        list[CreatePolicyConditionRequest],
        Field(
            min_length=1,
            max_length=_MAX_CONDITION_BLOCKS,
        ),
    ]


class CreatePolicyAnyConditionRequest(BaseSchema):
    """At least one of `conditions` matches."""

    kind: Literal["any"]
    conditions: Annotated[
        list[CreatePolicyConditionRequest],
        Field(
            min_length=1,
            max_length=_MAX_CONDITION_BLOCKS,
        ),
    ]


class CreatePolicyNotConditionRequest(BaseSchema):
    """Matches when `condition` doesn't."""

    kind: Literal["not"]
    condition: CreatePolicyConditionRequest


class CreatePolicyTargetHostConditionRequest(BaseSchema):
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


class CreatePolicyTargetNetworkConditionRequest(BaseSchema):
    """The client asked for an IP in one of `networks`. A target given by name doesn't match."""

    kind: Literal["target_network"]
    networks: Annotated[
        list[IPvAnyNetwork],
        Field(
            min_length=1,
            max_length=256,
        ),
    ]


class CreatePolicyPortRangeRequest(BaseSchema):
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


class CreatePolicyTargetPortConditionRequest(BaseSchema):
    """The target port is in one of `ports`."""

    kind: Literal["target_port"]
    ports: Annotated[
        list[CreatePolicyPortRangeRequest],
        Field(
            min_length=1,
            max_length=256,
        ),
    ]


class CreatePolicyProtocolConditionRequest(BaseSchema):
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


class CreatePolicyClientNetworkConditionRequest(BaseSchema):
    """The client connects from an IP in one of `networks`."""

    kind: Literal["client_network"]
    networks: Annotated[
        list[IPvAnyNetwork],
        Field(
            min_length=1,
            max_length=256,
        ),
    ]


class CreatePolicyEncryptedConditionRequest(BaseSchema):
    """The client came over TLS."""

    kind: Literal["encrypted"]


class CreatePolicyScheduleConditionRequest(BaseSchema):
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
    # When the rule applies, by default always.
    condition: CreatePolicyConditionRequest = Field(
        default_factory=CreatePolicyAlwaysConditionRequest,
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


# Declared before its blocks: they hold one another.
type CreatePolicyConditionResponse = Annotated[
    CreatePolicyAlwaysConditionResponse
    | CreatePolicyAllConditionResponse
    | CreatePolicyAnyConditionResponse
    | CreatePolicyNotConditionResponse
    | CreatePolicyTargetHostConditionResponse
    | CreatePolicyTargetNetworkConditionResponse
    | CreatePolicyTargetPortConditionResponse
    | CreatePolicyProtocolConditionResponse
    | CreatePolicyClientNetworkConditionResponse
    | CreatePolicyEncryptedConditionResponse
    | CreatePolicyScheduleConditionResponse,
    Field(
        discriminator="kind",
    ),
]


class CreatePolicyAlwaysConditionResponse(BaseSchema):
    kind: Literal["always"]


class CreatePolicyAllConditionResponse(BaseSchema):
    kind: Literal["all"]
    conditions: list[CreatePolicyConditionResponse]


class CreatePolicyAnyConditionResponse(BaseSchema):
    kind: Literal["any"]
    conditions: list[CreatePolicyConditionResponse]


class CreatePolicyNotConditionResponse(BaseSchema):
    kind: Literal["not"]
    condition: CreatePolicyConditionResponse


class CreatePolicyTargetHostConditionResponse(BaseSchema):
    kind: Literal["target_host"]
    domains: list[str]


class CreatePolicyTargetNetworkConditionResponse(BaseSchema):
    kind: Literal["target_network"]
    networks: list[IPvAnyNetwork]


class CreatePolicyPortRangeResponse(BaseSchema):
    first: int
    last: int


class CreatePolicyTargetPortConditionResponse(BaseSchema):
    kind: Literal["target_port"]
    ports: list[CreatePolicyPortRangeResponse]


class CreatePolicyProtocolConditionResponse(BaseSchema):
    kind: Literal["protocol"]
    protocols: list[str]


class CreatePolicyClientNetworkConditionResponse(BaseSchema):
    kind: Literal["client_network"]
    networks: list[IPvAnyNetwork]


class CreatePolicyEncryptedConditionResponse(BaseSchema):
    kind: Literal["encrypted"]


class CreatePolicyScheduleConditionResponse(BaseSchema):
    kind: Literal["schedule"]
    days: list[int]
    start: time
    end: time
    timezone: str


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
