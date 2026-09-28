import asyncio
import secrets

from fastapi import HTTPException, status
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.auth import TOKEN_PREFIX, TOKEN_SEPARATOR
from proxium.db import Hash, TokenProxyAccountModel
from proxium.helpers import BaseSchema


class UpdateTokenProxyAccountTokenResponse(BaseSchema):
    key: str
    # Only here, the database keeps the hash.
    token: str


class UpdateTokenProxyAccountTokenService(BaseUserAuthenticatedService[UpdateTokenProxyAccountTokenResponse]):
    """Issue a new token, the old one stops working. The key changes too."""

    id: int

    @property
    def _get_account_statement(self) -> Select[tuple[TokenProxyAccountModel]]:
        return select(TokenProxyAccountModel).where(TokenProxyAccountModel.id == self.id)

    async def process(self, *args, **kwargs) -> UpdateTokenProxyAccountTokenResponse:
        result: Result[tuple[TokenProxyAccountModel]] = await self.session.execute(self._get_account_statement)
        try:
            account: TokenProxyAccountModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

        key: str = f"{TOKEN_PREFIX}{secrets.token_hex(8)}"
        token: str = f"{key}{TOKEN_SEPARATOR}{secrets.token_urlsafe(32)}"
        account.key = key
        # Hashing is slow CPU work, it would stall the loop.
        account.token = await asyncio.to_thread(Hash.create, token)
        await self.session.commit()

        return UpdateTokenProxyAccountTokenResponse(key=key, token=token)
