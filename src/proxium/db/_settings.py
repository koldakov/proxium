from ipaddress import IPv4Network, IPv6Network

from sqlalchemy import ARRAY, CheckConstraint
from sqlalchemy.dialects.postgresql import CIDR
from sqlalchemy.orm import Mapped, mapped_column

from ._base import BaseTimestampModel


class SettingsModel(BaseTimestampModel):
    """Proxy settings edited in the admin. Exactly one row, added by the migration: read it, never insert.

    The proxy looks them up every few seconds and applies them to new connections, open ones keep the old.
    """

    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint(
            "id = 1",
            name="ck_settings_single_row",
        ),
        CheckConstraint(
            "handshake_timeout > 0",
            name="ck_settings_handshake_timeout_positive",
        ),
        CheckConstraint(
            "idle_timeout > 0",
            name="ck_settings_idle_timeout_positive",
        ),
        CheckConstraint(
            "connect_timeout > 0",
            name="ck_settings_connect_timeout_positive",
        ),
        CheckConstraint(
            "basic_account_cache_ttl > 0",
            name="ck_settings_basic_account_cache_ttl_positive",
        ),
        CheckConstraint(
            "basic_account_refusal_cache_ttl > 0",
            name="ck_settings_basic_account_refusal_cache_ttl_positive",
        ),
        CheckConstraint(
            "token_account_cache_ttl > 0",
            name="ck_settings_token_account_cache_ttl_positive",
        ),
        CheckConstraint(
            "token_account_refusal_cache_ttl > 0",
            name="ck_settings_token_account_refusal_cache_ttl_positive",
        ),
        CheckConstraint(
            "trusted_network_cache_ttl > 0",
            name="ck_settings_trusted_network_cache_ttl_positive",
        ),
        CheckConstraint(
            "trusted_network_refusal_cache_ttl > 0",
            name="ck_settings_trusted_network_refusal_cache_ttl_positive",
        ),
        CheckConstraint(
            "certificate_cache_ttl > 0",
            name="ck_settings_certificate_cache_ttl_positive",
        ),
    )

    # Private networks the proxy may connect to anyway, e.g. an internal service. Empty: the public internet only.
    guard_allow: Mapped[list[IPv4Network | IPv6Network]] = mapped_column(
        ARRAY(
            CIDR(),
        ),
        default=list,
        server_default="{}",
    )
    # Seconds a client has to authenticate and send its request.
    handshake_timeout: Mapped[float] = mapped_column(
        default=10.0,
        server_default="10",
    )
    # Seconds a tunnel may stay silent both ways before it's closed.
    idle_timeout: Mapped[float] = mapped_column(
        default=300.0,
        server_default="300",
    )
    # Seconds to resolve and connect to a target.
    connect_timeout: Mapped[float] = mapped_column(
        default=10.0,
        server_default="10",
    )
    # Seconds the proxy reuses a passed check of a basic account: how soon new connections see it revoked or changed.
    basic_account_cache_ttl: Mapped[float] = mapped_column(
        default=10.0,
        server_default="10",
    )
    # Seconds the proxy reuses a refused check of basic account credentials: how soon a new or fixed account works.
    basic_account_refusal_cache_ttl: Mapped[float] = mapped_column(
        default=10.0,
        server_default="10",
    )
    # The same for token accounts.
    token_account_cache_ttl: Mapped[float] = mapped_column(
        default=10.0,
        server_default="10",
    )
    token_account_refusal_cache_ttl: Mapped[float] = mapped_column(
        default=10.0,
        server_default="10",
    )
    # The same for trusted networks, checked by the client's IP.
    trusted_network_cache_ttl: Mapped[float] = mapped_column(
        default=10.0,
        server_default="10",
    )
    trusted_network_refusal_cache_ttl: Mapped[float] = mapped_column(
        default=10.0,
        server_default="10",
    )
    # Seconds the proxy reuses the active TLS certificate, or that there's none: how soon activating one applies.
    certificate_cache_ttl: Mapped[float] = mapped_column(
        default=10.0,
        server_default="10",
    )
