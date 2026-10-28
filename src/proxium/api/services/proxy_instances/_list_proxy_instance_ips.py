from typing import TYPE_CHECKING, ClassVar, NamedTuple, cast

from fastapi import HTTPException, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import IPvAnyAddress
from sqlalchemy import Result, Select, func, select
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Permission, ProxyInstanceModel
from proxium.helpers import BaseSchema

if TYPE_CHECKING:
    from ipaddress import IPv4Address, IPv6Address


class ListProxyInstanceIPsResponse(BaseSchema):
    ip: IPvAnyAddress


class _ProxyInstanceIPRow(NamedTuple):
    ip: IPv4Address | IPv6Address


class ListProxyInstanceIPsService(BaseUserAuthenticatedService[Page[ListProxyInstanceIPsResponse]]):
    """IPs on the interfaces of an instance as of its last report, IPv4 first."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.PROXY_INSTANCES_VIEW})

    id: int

    @property
    def _get_proxy_instance_statement(self) -> Select[tuple[ProxyInstanceModel]]:
        return select(ProxyInstanceModel).where(
            ProxyInstanceModel.id == self.id,
            ProxyInstanceModel.is_deleted.is_(False),
        )

    @property
    def _list_proxy_instance_ips_statement(self) -> Select[_ProxyInstanceIPRow]:
        # A row per IP of the array: a page of them, not the whole array. SQLAlchemy types rows by their columns, the
        # label makes it this one.
        ip = func.unnest(ProxyInstanceModel.ips, type_=INET()).label("ip")
        return cast(
            "Select[_ProxyInstanceIPRow]",
            select(ip).where(ProxyInstanceModel.id == self.id).order_by(ip),
        )

    async def _get_proxy_instance(self) -> ProxyInstanceModel:
        result: Result[tuple[ProxyInstanceModel]] = await self.session.execute(self._get_proxy_instance_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Proxy instance not found.",
            ) from None

    async def process(self, *args, **kwargs) -> Page[ListProxyInstanceIPsResponse]:
        # No IPs give an empty page, a missing instance a 404.
        await self._get_proxy_instance()

        return await apaginate(
            self.session,
            self._list_proxy_instance_ips_statement,
        )
