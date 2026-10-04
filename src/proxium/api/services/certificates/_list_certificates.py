from datetime import datetime

from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import Select, select

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import CertificateModel
from proxium.helpers import BaseSchema


class ListCertificatesRequest(BaseSchema):
    """Filters from the query string, all optional and combined with AND."""

    # `true` finds the one TLS clients get, if any.
    is_active: bool | None = None


class ListCertificatesResponse(BaseSchema):
    id: int
    names: list[str]
    fingerprint: str
    is_self_signed: bool
    not_valid_before: datetime
    not_valid_after: datetime
    is_active: bool
    created_at: datetime


class ListCertificatesService(BaseUserAuthenticatedService[Page[ListCertificatesResponse]]):
    data: ListCertificatesRequest

    @property
    def _list_certificates_statement(self) -> Select[tuple[CertificateModel]]:
        statement: Select[tuple[CertificateModel]] = select(CertificateModel).order_by(
            CertificateModel.id.desc(),
        )
        if self.data.is_active is not None:
            statement = statement.where(CertificateModel.is_active.is_(self.data.is_active))

        return statement

    async def process(self, *args, **kwargs) -> Page[ListCertificatesResponse]:
        return await apaginate(
            self.session,
            self._list_certificates_statement,
        )
