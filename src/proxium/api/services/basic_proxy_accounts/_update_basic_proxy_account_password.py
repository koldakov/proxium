import asyncio
from typing import Annotated

from fastapi import HTTPException, status
from pydantic import Field, SecretStr
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import BasicProxyAccountModel, Hash
from proxium.helpers import BaseSchema


class UpdateBasicProxyAccountPasswordRequest(BaseSchema):
    """Set by the admin, the old password isn't asked."""

    password: Annotated[
        SecretStr,
        Field(
            min_length=8,
            max_length=128,
        ),
    ]


class UpdateBasicProxyAccountPasswordService(BaseUserAuthenticatedService[None]):
    id: int
    data: UpdateBasicProxyAccountPasswordRequest

    @property
    def _get_account_statement(self) -> Select[tuple[BasicProxyAccountModel]]:
        return select(BasicProxyAccountModel).where(BasicProxyAccountModel.id == self.id)

    async def process(self, *args, **kwargs) -> None:
        result: Result[tuple[BasicProxyAccountModel]] = await self.session.execute(self._get_account_statement)
        try:
            account: BasicProxyAccountModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

        # Hashing is slow CPU work, it would stall the loop.
        account.password = await asyncio.to_thread(Hash.create, self.data.password.get_secret_value())
        await self.session.commit()
