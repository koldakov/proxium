from typing import ClassVar, Final, NamedTuple, cast

from sqlalchemy import VARCHAR, ColumnElement, Result, Select, and_, case, func, literal, select, type_coerce

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Permission, ProxyInstanceModel, ProxyInstanceStatus
from proxium.helpers import BaseSchema

_UNKNOWN: Final[str] = "unknown"


class GetProxyInstanceCountsResponse(BaseSchema):
    pending: int
    running: int
    stopped: int
    unknown: int


class _ProxyInstanceCountsRow(NamedTuple):
    pending: int
    running: int
    stopped: int
    unknown: int


class GetProxyInstanceCountsService(BaseUserAuthenticatedService[GetProxyInstanceCountsResponse]):
    """Instances by status, deregistered ones left out."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.PROXY_INSTANCES_VIEW})

    @property
    def _status_expression(self) -> ColumnElement[str]:
        # Unknown isn't stored: a gone process writes nothing, so it's what the database's clock says.
        return case(
            (
                and_(
                    ProxyInstanceModel.status != ProxyInstanceStatus.STOPPED,
                    ProxyInstanceModel.expires_at < func.now(),
                ),
                literal(_UNKNOWN),
            ),
            else_=type_coerce(ProxyInstanceModel.status, VARCHAR()),
        )

    @property
    def _count_proxy_instances_statement(self) -> Select[_ProxyInstanceCountsRow]:
        status = self._status_expression
        # One row, a count per status: no rows give zeros. SQLAlchemy types rows by their columns, the labels make
        # it this one.
        return cast(
            "Select[_ProxyInstanceCountsRow]",
            select(
                func.count().filter(status == ProxyInstanceStatus.PENDING.value).label("pending"),
                func.count().filter(status == ProxyInstanceStatus.RUNNING.value).label("running"),
                func.count().filter(status == ProxyInstanceStatus.STOPPED.value).label("stopped"),
                func.count().filter(status == _UNKNOWN).label("unknown"),
            ).where(ProxyInstanceModel.is_deleted.is_(False)),
        )

    async def process(self, *args, **kwargs) -> GetProxyInstanceCountsResponse:
        result: Result[_ProxyInstanceCountsRow] = await self.session.execute(self._count_proxy_instances_statement)
        return GetProxyInstanceCountsResponse.model_validate(result.one())
