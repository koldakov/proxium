from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING, Annotated, ClassVar, Final, Literal

from fastapi import HTTPException, status
from pydantic import Field, IPvAnyNetwork, TypeAdapter
from sqlalchemy import BigInteger, Date, Result, Select, and_, case, cast, column, func, or_, select, values
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.core import api_settings
from proxium.counters import RedisTrafficShare
from proxium.db import (
    Direction,
    Permission,
    PolicyModel,
    PolicyRuleModel,
    PolicyTrafficQuotaModel,
    QuotaPeriod,
    TrustedNetworkModel,
    TrustedNetworkPolicyModel,
    TrustedNetworkTrafficModel,
)
from proxium.helpers import BaseSchema
from proxium.observers import SharedTraffic, TrafficShareUnavailable, get_share_key
from proxium.policies import DEFAULT_PERIODS, EndlessPeriodError, Period
from proxium.proxy import Usage

if TYPE_CHECKING:
    from collections.abc import Collection

# One for the process: unreadable bytes of a proxy process are logged once, not on every request.
_TRAFFIC_SHARE: Final[RedisTrafficShare] = RedisTrafficShare()

# Declared before its blocks: they hold one another.
type GetTrustedNetworkQuotasConditionResponse = Annotated[
    GetTrustedNetworkQuotasAlwaysConditionResponse
    | GetTrustedNetworkQuotasAllConditionResponse
    | GetTrustedNetworkQuotasAnyConditionResponse
    | GetTrustedNetworkQuotasNotConditionResponse
    | GetTrustedNetworkQuotasTargetHostConditionResponse
    | GetTrustedNetworkQuotasTargetNetworkConditionResponse
    | GetTrustedNetworkQuotasTargetPortConditionResponse
    | GetTrustedNetworkQuotasProtocolConditionResponse
    | GetTrustedNetworkQuotasClientNetworkConditionResponse
    | GetTrustedNetworkQuotasEncryptedConditionResponse
    | GetTrustedNetworkQuotasScheduleConditionResponse,
    Field(
        discriminator="kind",
    ),
]


class GetTrustedNetworkQuotasAlwaysConditionResponse(BaseSchema):
    kind: Literal["always"]


class GetTrustedNetworkQuotasAllConditionResponse(BaseSchema):
    kind: Literal["all"]
    conditions: list[GetTrustedNetworkQuotasConditionResponse]


class GetTrustedNetworkQuotasAnyConditionResponse(BaseSchema):
    kind: Literal["any"]
    conditions: list[GetTrustedNetworkQuotasConditionResponse]


class GetTrustedNetworkQuotasNotConditionResponse(BaseSchema):
    kind: Literal["not"]
    condition: GetTrustedNetworkQuotasConditionResponse


class GetTrustedNetworkQuotasTargetHostConditionResponse(BaseSchema):
    kind: Literal["target_host"]
    domains: list[str]


class GetTrustedNetworkQuotasTargetNetworkConditionResponse(BaseSchema):
    kind: Literal["target_network"]
    networks: list[IPvAnyNetwork]


class GetTrustedNetworkQuotasPortRangeResponse(BaseSchema):
    first: int
    last: int


class GetTrustedNetworkQuotasTargetPortConditionResponse(BaseSchema):
    kind: Literal["target_port"]
    ports: list[GetTrustedNetworkQuotasPortRangeResponse]


class GetTrustedNetworkQuotasProtocolConditionResponse(BaseSchema):
    kind: Literal["protocol"]
    protocols: list[str]


class GetTrustedNetworkQuotasClientNetworkConditionResponse(BaseSchema):
    kind: Literal["client_network"]
    networks: list[IPvAnyNetwork]


class GetTrustedNetworkQuotasEncryptedConditionResponse(BaseSchema):
    kind: Literal["encrypted"]


class GetTrustedNetworkQuotasScheduleConditionResponse(BaseSchema):
    kind: Literal["schedule"]
    days: list[int]
    start: time
    end: time
    timezone: str


class GetTrustedNetworkQuotasItemResponse(BaseSchema):
    policy_id: int
    policy_name: Annotated[
        str,
        Field(
            max_length=255,
        ),
    ]
    is_global: bool
    rule_id: int
    rule_name: Annotated[
        str,
        Field(
            max_length=255,
        ),
    ]
    # The quota counts only while it matches: the first rule of the policy that matches applies.
    rule_condition: GetTrustedNetworkQuotasConditionResponse
    quota_id: int
    direction: Direction
    max_bytes: int
    period: QuotaPeriod
    period_length: int
    # The current period's first UTC day.
    period_start: date
    # The next period's first UTC day, exclusive: the usage resets then. None for `total`: it never resets.
    period_end: date | None
    # Since `period_start`, whichever direction the quota counts.
    bytes_sent: int
    bytes_received: int


class GetTrustedNetworkQuotasResponse(BaseSchema):
    # False: Redis didn't answer, only the traffic the proxy has written is counted, up to about a minute behind.
    live: bool
    items: list[GetTrustedNetworkQuotasItemResponse]


# A rule's condition as stored: saved through the API, it fits.
_CONDITION_ADAPTER: Final[TypeAdapter[GetTrustedNetworkQuotasConditionResponse]] = TypeAdapter(
    GetTrustedNetworkQuotasConditionResponse,
)


class GetTrustedNetworkQuotasService(BaseUserAuthenticatedService[GetTrustedNetworkQuotasResponse]):
    """The quotas of the network's active policies and of the active global ones, with what's used of each in its
    current period: the written traffic and what proxy processes haven't written yet.
    """

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.TRAFFIC_VIEW})

    id: int

    @property
    def _get_network_statement(self) -> Select[tuple[TrustedNetworkModel]]:
        return select(TrustedNetworkModel).where(TrustedNetworkModel.id == self.id)

    @property
    def _list_quotas_statement(self) -> Select[tuple[PolicyModel, PolicyRuleModel, PolicyTrafficQuotaModel, date]]:
        """Each quota with its rule, its policy and the day its periods count from."""
        # As the proxy anchors them: a global policy counts from its own day, even if it's assigned too.
        policies = (
            select(
                PolicyModel.id,
                case(
                    (PolicyModel.is_global.is_(True), PolicyModel.global_starts_on),
                    else_=TrustedNetworkPolicyModel.starts_on,
                ).label("anchor"),
            )
            .outerjoin(
                TrustedNetworkPolicyModel,
                and_(
                    TrustedNetworkPolicyModel.policy_id == PolicyModel.id,
                    TrustedNetworkPolicyModel.trusted_network_id == self.id,
                ),
            )
            .where(
                PolicyModel.is_active.is_(True),
                or_(PolicyModel.is_global.is_(True), TrustedNetworkPolicyModel.id.is_not(None)),
            )
            .order_by(PolicyModel.id)
            # The API caps both, so this never cuts: only bounds the query. Rules and quotas are capped per policy.
            .limit(api_settings.policies_max_per_owner + api_settings.global_policies_max)
            .subquery()
        )
        # By id after the name: names aren't unique, the order must not shuffle equal ones.
        return (
            select(PolicyModel, PolicyRuleModel, PolicyTrafficQuotaModel, policies.c.anchor)
            .select_from(policies)
            .join(PolicyModel, PolicyModel.id == policies.c.id)
            .join(PolicyRuleModel, PolicyRuleModel.policy_id == PolicyModel.id)
            .join(PolicyTrafficQuotaModel, PolicyTrafficQuotaModel.rule_id == PolicyRuleModel.id)
            .order_by(PolicyModel.name, PolicyModel.id, PolicyRuleModel.position, PolicyTrafficQuotaModel.id)
        )

    def _get_totals_statement(self, starts: Collection[date], /) -> Select[tuple[date, int, int]]:
        """Bytes since each day, zeros without traffic: a row per period start, not per day. Sums of bigint are
        numeric: cast.
        """
        requested = values(
            column("since", Date()),
            name="requested",
        ).data([(start,) for start in starts])
        return (
            select(
                requested.c.since,
                cast(func.coalesce(func.sum(TrustedNetworkTrafficModel.bytes_sent), 0), BigInteger()),
                cast(func.coalesce(func.sum(TrustedNetworkTrafficModel.bytes_received), 0), BigInteger()),
            )
            .select_from(requested)
            .outerjoin(
                TrustedNetworkTrafficModel,
                and_(
                    TrustedNetworkTrafficModel.trusted_network_id == self.id,
                    TrustedNetworkTrafficModel.day >= requested.c.since,
                ),
            )
            .group_by(requested.c.since)
        )

    async def _get_network(self) -> TrustedNetworkModel:
        result: Result[tuple[TrustedNetworkModel]] = await self.session.execute(self._get_network_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Network not found.",
            ) from None

    async def _read_shared(self) -> SharedTraffic:
        """What proxy processes haven't written yet. Raise `TrafficShareUnavailable` if Redis doesn't answer."""
        key = get_share_key((TrustedNetworkTrafficModel, self.id))
        shared = await _TRAFFIC_SHARE.read([key])
        return shared[key]

    async def _read_totals(self, starts: Collection[date], /) -> dict[date, Usage]:
        result: Result[tuple[date, int, int]] = await self.session.execute(self._get_totals_statement(starts))
        return {since: Usage(sent=sent, received=received) for since, sent, received in result.tuples()}

    @staticmethod
    def _get_period_end(period: Period, anchor: date, today: date, /, *, length: int) -> date | None:
        """None for a period that never resets."""
        try:
            return period.next_start(anchor, today, length=length)
        except EndlessPeriodError:
            return None

    @staticmethod
    def _get_used(written: Usage, shared: SharedTraffic, since: date, /) -> Usage:
        """The written bytes since the day and the ones proxy processes haven't written yet."""
        unwritten = [usage for day, usage in shared.days.items() if day >= since]
        return Usage(
            sent=written.sent + sum(usage.sent for usage in unwritten),
            received=written.received + sum(usage.received for usage in unwritten),
        )

    async def process(self, *args, **kwargs) -> GetTrustedNetworkQuotasResponse:
        # No quotas give no items, a missing network a 404.
        await self._get_network()

        result: Result[tuple[PolicyModel, PolicyRuleModel, PolicyTrafficQuotaModel, date]] = await self.session.execute(
            self._list_quotas_statement,
        )
        quotas = result.tuples().all()
        if not quotas:
            return GetTrustedNetworkQuotasResponse(live=True, items=[])

        today = datetime.now(UTC).date()
        starts = {
            quota.id: DEFAULT_PERIODS[quota.period].start(anchor, today, length=quota.period_length)
            for _, _, quota, anchor in quotas
        }
        # Redis first, then the sums: bytes written meanwhile may count twice for a moment, never missed.
        try:
            shared = await self._read_shared()
        except TrafficShareUnavailable:
            shared = SharedTraffic(version=None, processes=frozenset(), days={})
            live = False
        else:
            live = True
        totals = await self._read_totals(set(starts.values()))

        items: list[GetTrustedNetworkQuotasItemResponse] = []
        for policy, rule, quota, anchor in quotas:
            start = starts[quota.id]
            used = self._get_used(totals[start], shared, start)
            items.append(
                GetTrustedNetworkQuotasItemResponse(
                    policy_id=policy.id,
                    policy_name=policy.name,
                    is_global=policy.is_global,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    rule_condition=_CONDITION_ADAPTER.validate_python(rule.condition),
                    quota_id=quota.id,
                    direction=quota.direction,
                    max_bytes=quota.max_bytes,
                    period=quota.period,
                    period_length=quota.period_length,
                    period_start=start,
                    period_end=self._get_period_end(
                        DEFAULT_PERIODS[quota.period],
                        anchor,
                        today,
                        length=quota.period_length,
                    ),
                    bytes_sent=used.sent,
                    bytes_received=used.received,
                ),
            )
        return GetTrustedNetworkQuotasResponse(live=live, items=items)
