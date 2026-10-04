from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import TYPE_CHECKING

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cryptography.hazmat.primitives.asymmetric.types import PublicKeyTypes


class InvalidCertificateError(Exception):
    """The certificate or its key can't be used. The message says why, for people."""


@dataclass(frozen=True, slots=True)
class CertificateInfo:
    """A checked certificate with its key, both as normalized PEM, and what clients see in it."""

    certificate: str
    private_key: str
    names: list[str]
    fingerprint: str
    is_self_signed: bool
    not_valid_before: datetime
    not_valid_after: datetime


def _public_key_der(key: PublicKeyTypes, /) -> bytes:
    return key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _names(certificate: x509.Certificate, /) -> list[str]:
    try:
        extension = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except x509.ExtensionNotFound:
        return []
    return [
        *extension.value.get_values_for_type(x509.DNSName),
        *(str(ip) for ip in extension.value.get_values_for_type(x509.IPAddress)),
    ]


def _general_name(name: str, /) -> x509.GeneralName:
    try:
        return x509.IPAddress(ip_address(name))
    except ValueError:
        return x509.DNSName(name)


def read_certificate(certificate: str, private_key: str, /) -> CertificateInfo:
    """Check that the PEM chain and the key are readable, match each other and the certificate hasn't expired.

    The chain starts with the server's certificate, intermediates follow. The key must have no password.
    """
    try:
        chain = x509.load_pem_x509_certificates(certificate.encode())
    except ValueError:
        raise InvalidCertificateError("No PEM certificate found.") from None
    server = chain[0]

    try:
        key = serialization.load_pem_private_key(private_key.encode(), password=None)
    except TypeError:
        raise InvalidCertificateError("The private key is password-protected, upload it without a password.") from None
    except ValueError:
        raise InvalidCertificateError("No PEM private key found.") from None

    if _public_key_der(key.public_key()) != _public_key_der(server.public_key()):
        raise InvalidCertificateError("The private key doesn't match the certificate.")
    if server.not_valid_after_utc <= datetime.now(UTC):
        raise InvalidCertificateError(f"The certificate expired on {server.not_valid_after_utc:%Y-%m-%d}.")

    return CertificateInfo(
        certificate="".join(item.public_bytes(serialization.Encoding.PEM).decode() for item in chain),
        private_key=key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
        names=_names(server),
        fingerprint=server.fingerprint(hashes.SHA256()).hex(),
        is_self_signed=server.issuer == server.subject,
        not_valid_before=server.not_valid_before_utc,
        not_valid_after=server.not_valid_after_utc,
    )


def generate_self_signed(names: Sequence[str], /, *, days: int) -> tuple[str, str]:
    """A new certificate for host names and IPs, valid for `days` from now, and its key: both PEM.

    Marked as a CA, like `openssl req -x509` does: clients given it with e.g. curl's --proxy-cacert trust it then.
    """
    key = ec.generate_private_key(ec.SECP256R1())
    # The names clients check go in the alternative names, the subject only labels it.
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Proxium self-signed")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=days))
        .add_extension(
            x509.SubjectAlternativeName([_general_name(name) for name in names]),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return (
        certificate.public_bytes(serialization.Encoding.PEM).decode(),
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
    )
