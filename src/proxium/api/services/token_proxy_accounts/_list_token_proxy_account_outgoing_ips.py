from datetime import datetime
from typing import Annotated, ClassVar

from fastapi import HTTPException, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import Field, IPvAnyAddress
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingIPModel, Permission, TokenProxyAccountModel, TokenProxyAccountOutgoingIPModel
from proxium.helpers import BaseSchema


class ListTokenProxyAccountOutgoingIPsResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
        ),
    ]
    ip: IPvAnyAddress
    created_by_id: int
    created_at: datetime


class ListTokenProxyAccountOutgoingIPsService(
    BaseUserAuthenticatedService[Page[ListTokenProxyAccountOutgoingIPsResponse]],
):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.TOKEN_PROXY_ACCOUNTS_VIEW})

    id: int

    @property
    def _get_account_statement(self) -> Select[tuple[TokenProxyAccountModel]]:
        return select(TokenProxyAccountModel).where(TokenProxyAccountModel.id == self.id)

    @property
    def _list_outgoing_ips_statement(self) -> Select[tuple[OutgoingIPModel]]:
        # In the order the IPs were added to the server.
        return (
            select(OutgoingIPModel)
            .join(
                TokenProxyAccountOutgoingIPModel,
                TokenProxyAccountOutgoingIPModel.outgoing_ip_id == OutgoingIPModel.id,
            )
            .where(TokenProxyAccountOutgoingIPModel.token_proxy_account_id == self.id)
            .order_by(OutgoingIPModel.id)
        )

    async def _get_account(self) -> TokenProxyAccountModel:
        result: Result[tuple[TokenProxyAccountModel]] = await self.session.execute(self._get_account_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

    async def process(self, *args, **kwargs) -> Page[ListTokenProxyAccountOutgoingIPsResponse]:
        # An empty pool gives an empty page, a missing account a 404.
        await self._get_account()

        return await apaginate(
            self.session,
            self._list_outgoing_ips_statement,
        )
