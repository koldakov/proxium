from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import VARCHAR, ColumnElement, Row, Select, and_, case, func, literal, select, type_coerce

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Permission, ProxyInstanceModel, ProxyInstanceStatus
from proxium.helpers import BaseSchema

if TYPE_CHECKING:
    from collections.abc import Sequence


class ListProxyInstanceStatus(StrEnum):
    """The reported status, or unknown once the instance missed its reports."""

    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class ListProxyInstancesRequest(BaseSchema):
    """Filters from the query string, all optional and combined with AND."""

    status: ListProxyInstanceStatus | None = None


class ListProxyInstancesResponse(BaseSchema):
    id: int
    hostname: str
    name: str
    version: str
    status: ListProxyInstanceStatus
    started_at: datetime
    last_seen_at: datetime
    created_at: datetime


class ListProxyInstancesService(BaseUserAuthenticatedService[Page[ListProxyInstancesResponse]]):
    """Deregistered instances are left out."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.PROXY_INSTANCES_VIEW})

    data: ListProxyInstancesRequest

    @property
    def _status_expression(self) -> ColumnElement[str]:
        # Unknown isn't stored: a gone process writes nothing, so it's what the database's clock says.
        return case(
            (
                and_(
                    ProxyInstanceModel.status != ProxyInstanceStatus.STOPPED,
                    ProxyInstanceModel.expires_at < func.now(),
                ),
                literal(ListProxyInstanceStatus.UNKNOWN.value),
            ),
            else_=type_coerce(ProxyInstanceModel.status, VARCHAR()),
        )

    @property
    def _list_proxy_instances_statement(self) -> Select[tuple[ProxyInstanceModel, str]]:
        status = self._status_expression
        statement: Select[tuple[ProxyInstanceModel, str]] = (
            select(
                ProxyInstanceModel,
                status,
            )
            .where(ProxyInstanceModel.is_deleted.is_(False))
            .order_by(ProxyInstanceModel.id.desc())
        )
        if self.data.status is not None:
            statement = statement.where(status == self.data.status.value)

        return statement

    def _get_responses(
        self,
        rows: Sequence[Row[tuple[ProxyInstanceModel, str]]],
        /,
    ) -> list[ListProxyInstancesResponse]:
        # The stored status is what the process reported, the response gets the one with unknown.
        return [
            ListProxyInstancesResponse.model_validate(instance).model_copy(
                update={"status": ListProxyInstanceStatus(status)},
            )
            for instance, status in rows
        ]

    async def process(self, *args, **kwargs) -> Page[ListProxyInstancesResponse]:
        return await apaginate(
            self.session,
            self._list_proxy_instances_statement,
            transformer=self._get_responses,
        )
