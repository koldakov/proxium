from datetime import datetime
from typing import Annotated

from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import Field
from sqlalchemy import Select, select

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import BasicProxyAccountModel
from proxium.helpers import BaseSchema


class ListBasicProxyAccountsResponse(BaseSchema):
    id: int
    username: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
        ),
    ]
    is_active: bool
    expires_at: datetime | None
    created_by_id: int
    created_at: datetime


class ListBasicProxyAccountsService(BaseUserAuthenticatedService[Page[ListBasicProxyAccountsResponse]]):
    # Matches username, case-insensitive.
    query: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=255,
        ),
    ] = None

    @property
    def _list_accounts_statement(self) -> Select[tuple[BasicProxyAccountModel]]:
        statement: Select[tuple[BasicProxyAccountModel]] = select(BasicProxyAccountModel).order_by(
            BasicProxyAccountModel.id.desc(),
        )
        if self.query is not None:
            statement = statement.where(BasicProxyAccountModel.username.icontains(self.query, autoescape=True))

        return statement

    async def process(self, *args, **kwargs) -> Page[ListBasicProxyAccountsResponse]:
        return await apaginate(
            self.session,
            self._list_accounts_statement,
        )
