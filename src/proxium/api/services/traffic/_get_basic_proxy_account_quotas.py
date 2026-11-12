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
    BasicProxyAccountModel,
    BasicProxyAccountPolicyModel,
    BasicProxyAccountTrafficModel,
    Direction,
    Permission,
    PolicyModel,
    PolicyRuleModel,
    PolicyTrafficQuotaModel,
    QuotaPeriod,
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
type GetBasicProxyAccountQuotasConditionResponse = Annotated[
    GetBasicProxyAccountQuotasAlwaysConditionResponse
    | GetBasicProxyAccountQuotasAllConditionResponse
    | GetBasicProxyAccountQuotasAnyConditionResponse
    | GetBasicProxyAccountQuotasNotConditionResponse
    | GetBasicProxyAccountQuotasTargetHostConditionResponse
    | GetBasicProxyAccountQuotasTargetNetworkConditionResponse
    | GetBasicProxyAccountQuotasTargetPortConditionResponse
    | GetBasicProxyAccountQuotasProtocolConditionResponse
    | GetBasicProxyAccountQuotasClientNetworkConditionResponse
    | GetBasicProxyAccountQuotasEncryptedConditionResponse
    | GetBasicProxyAccountQuotasScheduleConditionResponse,
    Field(
        discriminator="kind",
    ),
]


class GetBasicProxyAccountQuotasAlwaysConditionResponse(BaseSchema):
    kind: Literal["always"]


class GetBasicProxyAccountQuotasAllConditionResponse(BaseSchema):
    kind: Literal["all"]
    conditions: list[GetBasicProxyAccountQuotasConditionResponse]


class GetBasicProxyAccountQuotasAnyConditionResponse(BaseSchema):
    kind: Literal["any"]
    conditions: list[GetBasicProxyAccountQuotasConditionResponse]


class GetBasicProxyAccountQuotasNotConditionResponse(BaseSchema):
    kind: Literal["not"]
    condition: GetBasicProxyAccountQuotasConditionResponse


class GetBasicProxyAccountQuotasTargetHostConditionResponse(BaseSchema):
    kind: Literal["target_host"]
    domains: list[str]


class GetBasicProxyAccountQuotasTargetNetworkConditionResponse(BaseSchema):
    kind: Literal["target_network"]
    networks: list[IPvAnyNetwork]


class GetBasicProxyAccountQuotasPortRangeResponse(BaseSchema):
    first: int
    last: int


class GetBasicProxyAccountQuotasTargetPortConditionResponse(BaseSchema):
    kind: Literal["target_port"]
    ports: list[GetBasicProxyAccountQuotasPortRangeResponse]


class GetBasicProxyAccountQuotasProtocolConditionResponse(BaseSchema):
    kind: Literal["protocol"]
    protocols: list[str]


class GetBasicProxyAccountQuotasClientNetworkConditionResponse(BaseSchema):
    kind: Literal["client_network"]
    networks: list[IPvAnyNetwork]


class GetBasicProxyAccountQuotasEncryptedConditionResponse(BaseSchema):
    kind: Literal["encrypted"]


class GetBasicProxyAccountQuotasScheduleConditionResponse(BaseSchema):
    kind: Literal["schedule"]
    days: list[int]
    start: time
    end: time
    timezone: str


class GetBasicProxyAccountQuotasItemResponse(BaseSchema):
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
    rule_condition: GetBasicProxyAccountQuotasConditionResponse
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


class GetBasicProxyAccountQuotasResponse(BaseSchema):
    # False: Redis didn't answer, only the traffic the proxy has written is counted, up to about a minute behind.
    live: bool
    items: list[GetBasicProxyAccountQuotasItemResponse]


# A rule's condition as stored: saved through the API, it fits.
_CONDITION_ADAPTER: Final[TypeAdapter[GetBasicProxyAccountQuotasConditionResponse]] = TypeAdapter(
    GetBasicProxyAccountQuotasConditionResponse,
)


class GetBasicProxyAccountQuotasService(BaseUserAuthenticatedService[GetBasicProxyAccountQuotasResponse]):
    """The quotas of the account's active policies and of the active global ones, with what's used of each in its
    current period: the written traffic and what proxy processes haven't written yet.
    """

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.TRAFFIC_VIEW})

    id: int

    @property
    def _get_account_statement(self) -> Select[tuple[BasicProxyAccountModel]]:
        return select(BasicProxyAccountModel).where(BasicProxyAccountModel.id == self.id)

    @property
    def _list_quotas_statement(self) -> Select[tuple[PolicyModel, PolicyRuleModel, PolicyTrafficQuotaModel, date]]:
        """Each quota with its rule, its policy and the day its periods count from."""
        # As the proxy anchors them: a global policy counts from its own day, even if it's assigned too.
        policies = (
            select(
                PolicyModel.id,
                case(
                    (PolicyModel.is_global.is_(True), PolicyModel.global_starts_on),
                    else_=BasicProxyAccountPolicyModel.starts_on,
                ).label("anchor"),
            )
            .outerjoin(
                BasicProxyAccountPolicyModel,
                and_(
                    BasicProxyAccountPolicyModel.policy_id == PolicyModel.id,
                    BasicProxyAccountPolicyModel.basic_proxy_account_id == self.id,
                ),
            )
            .where(
                PolicyModel.is_active.is_(True),
                or_(PolicyModel.is_global.is_(True), BasicProxyAccountPolicyModel.id.is_not(None)),
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
                cast(func.coalesce(func.sum(BasicProxyAccountTrafficModel.bytes_sent), 0), BigInteger()),
                cast(func.coalesce(func.sum(BasicProxyAccountTrafficModel.bytes_received), 0), BigInteger()),
            )
            .select_from(requested)
            .outerjoin(
                BasicProxyAccountTrafficModel,
                and_(
                    BasicProxyAccountTrafficModel.basic_proxy_account_id == self.id,
                    BasicProxyAccountTrafficModel.day >= requested.c.since,
                ),
            )
            .group_by(requested.c.since)
        )

    async def _get_account(self) -> BasicProxyAccountModel:
        result: Result[tuple[BasicProxyAccountModel]] = await self.session.execute(self._get_account_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

    async def _read_shared(self) -> SharedTraffic:
        """What proxy processes haven't written yet. Raise `TrafficShareUnavailable` if Redis doesn't answer."""
        key = get_share_key((BasicProxyAccountTrafficModel, self.id))
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

    async def process(self, *args, **kwargs) -> GetBasicProxyAccountQuotasResponse:
        # No quotas give no items, a missing account a 404.
        await self._get_account()

        result: Result[tuple[PolicyModel, PolicyRuleModel, PolicyTrafficQuotaModel, date]] = await self.session.execute(
            self._list_quotas_statement,
        )
        quotas = result.tuples().all()
        if not quotas:
            return GetBasicProxyAccountQuotasResponse(live=True, items=[])

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

        items: list[GetBasicProxyAccountQuotasItemResponse] = []
        for policy, rule, quota, anchor in quotas:
            start = starts[quota.id]
            used = self._get_used(totals[start], shared, start)
            items.append(
                GetBasicProxyAccountQuotasItemResponse(
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
        return GetBasicProxyAccountQuotasResponse(live=live, items=items)
