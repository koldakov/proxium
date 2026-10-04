from datetime import datetime
from typing import Annotated, ClassVar

from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import Field
from sqlalchemy import Select, or_, select

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingMode, Permission, TokenProxyAccountModel
from proxium.helpers import BaseSchema


class ListTokenProxyAccountsResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
        ),
    ]
    key: str
    is_active: bool
    expires_at: datetime | None
    outgoing_mode: OutgoingMode
    created_by_id: int
    created_at: datetime


class ListTokenProxyAccountsService(BaseUserAuthenticatedService[Page[ListTokenProxyAccountsResponse]]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.TOKEN_PROXY_ACCOUNTS_VIEW})

    # Matches name or key, case-insensitive.
    query: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=255,
        ),
    ] = None

    @property
    def _list_accounts_statement(self) -> Select[tuple[TokenProxyAccountModel]]:
        statement: Select[tuple[TokenProxyAccountModel]] = select(TokenProxyAccountModel).order_by(
            TokenProxyAccountModel.id.desc(),
        )
        if self.query is not None:
            statement = statement.where(
                or_(
                    TokenProxyAccountModel.name.icontains(self.query, autoescape=True),
                    TokenProxyAccountModel.key.icontains(self.query, autoescape=True),
                ),
            )

        return statement

    async def process(self, *args, **kwargs) -> Page[ListTokenProxyAccountsResponse]:
        return await apaginate(
            self.session,
            self._list_accounts_statement,
        )
