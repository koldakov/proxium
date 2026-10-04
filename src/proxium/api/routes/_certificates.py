from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002, FastAPI reads signatures at runtime.
from fastapi_pagination import Page  # noqa: TC002, FastAPI reads signatures at runtime.

from proxium.api.services.certificates import (
    ActivateCertificateRequest,
    ActivateCertificateService,
    CreateCertificateRequest,
    CreateCertificateResponse,
    CreateCertificateService,
    DeactivateCertificateService,
    DeleteCertificateService,
    GetCertificateResponse,
    GetCertificateService,
    ListCertificatesRequest,
    ListCertificatesResponse,
    ListCertificatesService,
)

from ._security import bearer_scheme

certificates_router: APIRouter = APIRouter(
    prefix="/certificates",
    tags=["certificates"],
)


@certificates_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "The certificate. Inactive unless `activate`: then TLS clients get it within a few seconds.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `certificates.add`.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "The certificate is already uploaded, or with `activate` the active one isn't `replaces`.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": (
                "The body is malformed, the PEM can't be read, the key doesn't match or has a password, "
                "the certificate has expired, or a name is neither a host name nor an IP."
            ),
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def create_certificate(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    data: CreateCertificateRequest,
) -> CreateCertificateResponse:
    """Add a TLS certificate for clients of the proxy. The private key is stored encrypted.

    - `source: upload`: a PEM chain and its key, e.g. from Let's Encrypt.
    - `source: generate`: a new self-signed one for `names`, valid for `days`.
    - `activate`: give it to TLS clients right away, turning the active one off. Inactive by default.
    - `replaces`: with `activate`, the id of the active certificate the client saw, null if none.
    """
    service: CreateCertificateService = CreateCertificateService(token=credentials.credentials, data=data)
    return await service()


@certificates_router.get(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of certificates.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `certificates.view`.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Query parameters are malformed, e.g. the page size is out of range.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_certificates(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    # `Depends`, not `Query`: next to the pagination params, FastAPI documents a `Query` model as one `data` param.
    data: Annotated[ListCertificatesRequest, Depends()],
) -> Page[ListCertificatesResponse]:
    """List certificates, newest first.

    - `isActive`: `true` for the one TLS clients get. None means TLS is off.
    """
    service: ListCertificatesService = ListCertificatesService(token=credentials.credentials, data=data)
    return await service()


@certificates_router.get(
    "/{certificate_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The certificate with its PEM chain, without the key.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `certificates.view`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Certificate not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The certificate id is not an integer.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def get_certificate(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    certificate_id: int,
) -> GetCertificateResponse:
    """Get a certificate. Its PEM chain is what clients of a self-signed one need to trust the proxy."""
    service: GetCertificateService = GetCertificateService(token=credentials.credentials, id=certificate_id)
    return await service()


@certificates_router.post(
    "/{certificate_id}/activate",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "The certificate is active, the one active before is turned off.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `certificates.activate`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Certificate not found.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "The active certificate isn't `replaces` anymore, e.g. another admin activated one.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": (
                "The certificate id is not an integer, the body is malformed or the certificate has expired."
            ),
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def activate_certificate(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    certificate_id: int,
    data: ActivateCertificateRequest,
) -> None:
    """Give the certificate to TLS clients instead of the active one, which is turned off.

    New connections get it within a few seconds, open ones keep the old one.

    - `replaces`: the id of the active certificate the client saw, null if none. Fails if it has changed.
    """
    service: ActivateCertificateService = ActivateCertificateService(
        token=credentials.credentials,
        id=certificate_id,
        data=data,
    )
    return await service()


@certificates_router.post(
    "/{certificate_id}/deactivate",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "The certificate is inactive. If it was the active one, TLS is off.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `certificates.activate`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Certificate not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The certificate id is not an integer.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def deactivate_certificate(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    certificate_id: int,
) -> None:
    """Turn the certificate off. Without an active one, new TLS connections are refused, open ones stay."""
    service: DeactivateCertificateService = DeactivateCertificateService(
        token=credentials.credentials,
        id=certificate_id,
    )
    return await service()


@certificates_router.delete(
    "/{certificate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "The certificate and its key are deleted.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `certificates.delete`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Certificate not found.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "The certificate is active: deactivate it first.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The certificate id is not an integer.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def delete_certificate(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    certificate_id: int,
) -> None:
    """Delete an inactive certificate with its key."""
    service: DeleteCertificateService = DeleteCertificateService(
        token=credentials.credentials,
        id=certificate_id,
    )
    return await service()
