from datetime import datetime

from sqlalchemy import ARRAY, TEXT, VARCHAR, DateTime, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from ._base import BaseTimestampModel
from ._fields import Encrypted, EncryptedField


class CertificateModel(BaseTimestampModel):
    """A TLS certificate the proxy presents to clients. One at most is active, none turns TLS off.

    The fields after `private_key` are read from the certificate on upload, so lists need no parsing.
    """

    __tablename__ = "certificates"
    __table_args__ = (
        # One active certificate: the database refuses a second one, even from racing requests.
        Index(
            "uq_certificates_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    # PEM chain, the server's certificate first. Public: clients get it on every handshake.
    certificate: Mapped[str] = mapped_column(
        TEXT(),
    )
    # PEM, encrypted with `ENCRYPTION_KEY`. Never leaves the API.
    private_key: Mapped[Encrypted] = mapped_column(
        EncryptedField(),
    )
    # Host names and IPs of the subject alternative names: what clients check. Empty if it has none.
    # Text, not VARCHAR(255): nothing checks the length of names in an uploaded certificate.
    names: Mapped[list[str]] = mapped_column(
        ARRAY(
            TEXT(),
        ),
    )
    # SHA-256 of the server's certificate, hex. The same certificate can't be uploaded twice.
    fingerprint: Mapped[str] = mapped_column(
        VARCHAR(length=64),
        unique=True,
    )
    # Issued by itself: clients trust it only if told to, e.g. curl's --proxy-cacert.
    is_self_signed: Mapped[bool] = mapped_column()
    not_valid_before: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )
    not_valid_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )
    # Presented to TLS clients. Turning another one on turns this one off.
    is_active: Mapped[bool] = mapped_column(
        default=False,
        server_default="false",
    )
