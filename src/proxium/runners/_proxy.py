import asyncio
import logging
import secrets
import signal
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Final

import uvloop

from proxium.auth import (
    BasicProxyAccountAuthenticator,
    TokenProxyAccountAuthenticator,
    TrustedNetworkAuthenticator,
)
from proxium.certificates import CertificateEncryption
from proxium.core import proxy_settings
from proxium.db import (
    BasicProxyAccountTrafficModel,
    TokenProxyAccountTrafficModel,
    TrustedNetworkTrafficModel,
    session_manager,
)
from proxium.observers import TrafficObserver
from proxium.policies import InvalidPolicyError, RuleSetBuilder, RuleSetPolicy
from proxium.proxy import (
    AddressGuard,
    BasicCredentials,
    BearerCredentials,
    CachedAuthenticator,
    CachedEncryption,
    ClientKey,
    CredentialsKey,
    DirectConnector,
    DispatchAuthenticator,
    HttpInbound,
    Listener,
    ListenError,
    LoggingObserver,
    MemoryCache,
    Profile,
    ProxyServer,
    Socks5Inbound,
    Timeouts,
)
from proxium.selectors import OUTGOING_IPS_CLAIM, OutgoingSourceSelector
from proxium.watchers import PolicyWatcher, SettingsWatcher, Watchers

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from proxium.core import ListenAddress, LogLevel
    from proxium.proxy import (
        AuthenticationRequired,
        Authenticator,
        Cache,
        Encryption,
        EncryptionOutcome,
        Identity,
        Inbound,
        Observer,
        SourceSelector,
    )
    from proxium.watchers import CacheTtlsSnapshot, PolicySnapshot, SettingsSnapshot

logger = logging.getLogger(__name__)

LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def _get_identity_size(identity: Identity, /) -> int:
    """One plus the pool IPs: an identity with a big pool takes as much memory as many without."""
    return 1 + len(identity.claims.get(OUTGOING_IPS_CLAIM, ()))


@dataclass(frozen=True, slots=True)
class ProxyCaches:
    """Where the proxy keeps checks of clients and the certificate between connections."""

    basic: Cache[Identity]
    basic_refusals: Cache[AuthenticationRequired]
    bearer: Cache[Identity]
    bearer_refusals: Cache[AuthenticationRequired]
    trusted_network: Cache[Identity]
    trusted_network_refusals: Cache[AuthenticationRequired]
    encryption: Cache[EncryptionOutcome]

    async def clear_shortened(self, previous: CacheTtlsSnapshot, current: CacheTtlsSnapshot, /) -> None:
        """Drop what each cache keeps if its TTL got shorter: entries keep the TTL they were stored with."""
        shortened = [
            cache
            for cache, before, after in (
                (
                    self.basic,
                    previous.basic_account,
                    current.basic_account,
                ),
                (
                    self.basic_refusals,
                    previous.basic_account_refusal,
                    current.basic_account_refusal,
                ),
                (
                    self.bearer,
                    previous.token_account,
                    current.token_account,
                ),
                (
                    self.bearer_refusals,
                    previous.token_account_refusal,
                    current.token_account_refusal,
                ),
                (
                    self.trusted_network,
                    previous.trusted_network,
                    current.trusted_network,
                ),
                (
                    self.trusted_network_refusals,
                    previous.trusted_network_refusal,
                    current.trusted_network_refusal,
                ),
                (
                    self.encryption,
                    previous.certificate,
                    current.certificate,
                ),
            )
            if after < before
        ]
        # Independent of each other: no order, e.g. Redis ones clear at once.
        await asyncio.gather(*(cache.clear() for cache in shortened))


@dataclass(frozen=True, slots=True)
class _Checks:
    """Checks of clients and the certificate, reusing what's cached for `ttls`."""

    ttls: CacheTtlsSnapshot
    authenticator: Authenticator
    encryption: Encryption


class ProxyRunner:
    """Runs the proxy until SIGINT/SIGTERM, then shuts it down gracefully. A second signal forces the stop.

    Settings from the database are applied without a restart: new connections get them, open ones keep the old.
    """

    signals: ClassVar[tuple[signal.Signals, ...]] = (
        signal.SIGINT,
        signal.SIGTERM,
    )

    def __init__(
        self,
        *,
        listen: Sequence[ListenAddress] = proxy_settings.listen,
        graceful_timeout: float = proxy_settings.graceful_timeout,
        log_level: LogLevel = proxy_settings.log_level,
        settings_poll_interval: float = proxy_settings.settings_poll_interval,
    ) -> None:
        self._log_level: LogLevel = log_level
        # Needs the loop to flush, so the runner starts and closes it.
        self._traffic_observer: TrafficObserver = TrafficObserver(
            [
                BasicProxyAccountTrafficModel,
                TokenProxyAccountTrafficModel,
                TrustedNetworkTrafficModel,
            ],
        )
        # Kept across settings changes: they hold no settings, and caches survive.
        self._inbounds: list[Inbound] = [
            HttpInbound(),
            Socks5Inbound(),
        ]
        # Kept across settings changes, so what's cached survives them. In memory: one process, nothing to share.
        # Identities sized in pool IPs, see `_get_identity_size`: about 100 bytes each.
        self._caches: ProxyCaches = ProxyCaches(
            basic=MemoryCache(maxsize=100_000, getsizeof=_get_identity_size),
            basic_refusals=MemoryCache(),
            bearer=MemoryCache(maxsize=100_000, getsizeof=_get_identity_size),
            bearer_refusals=MemoryCache(),
            trusted_network=MemoryCache(maxsize=100_000, getsizeof=_get_identity_size),
            trusted_network_refusals=MemoryCache(),
            encryption=MemoryCache(),
        )
        # Random per process, as the caches are: digests of credentials are of no use outside it.
        digest_secret = secrets.token_bytes(32)
        self._credentials_key: CredentialsKey = CredentialsKey(secret=digest_secret)
        self._client_key: ClientKey = ClientKey(secret=digest_secret)
        # Built on the first settings, rebuilt only for a new TTL.
        self._checks: _Checks | None = None
        self._source: SourceSelector = OutgoingSourceSelector()
        self._observers: list[Observer] = [
            LoggingObserver(),
            self._traffic_observer,
        ]
        # Kept across settings changes: their limits count open connections. Rules change in place.
        self._rule_set_policy: RuleSetPolicy = RuleSetPolicy()
        # Quotas measure the traffic the observer counts.
        self._rule_set_builder: RuleSetBuilder = RuleSetBuilder(self._traffic_observer)
        self._watchers: Watchers = Watchers(
            [
                # Before the settings, which start listening: no connection goes through without its limits.
                PolicyWatcher(
                    self._apply_policies,
                    interval=settings_poll_interval,
                ),
                SettingsWatcher(
                    self._apply_settings,
                    interval=settings_poll_interval,
                ),
            ],
        )
        self._graceful_timeout: float = graceful_timeout
        self._listen: Sequence[ListenAddress] = listen

        self._server: ProxyServer = ProxyServer()
        self._stop: asyncio.Event = asyncio.Event()

    def _create_authenticator(self, ttls: CacheTtlsSnapshot, /) -> Authenticator:
        return DispatchAuthenticator(
            {
                BasicCredentials: CachedAuthenticator(
                    BasicProxyAccountAuthenticator(),
                    key=self._credentials_key,
                    cache=self._caches.basic,
                    refusals=self._caches.basic_refusals,
                    ttl=ttls.basic_account,
                    refusal_ttl=ttls.basic_account_refusal,
                ),
                BearerCredentials: CachedAuthenticator(
                    TokenProxyAccountAuthenticator(),
                    key=self._credentials_key,
                    cache=self._caches.bearer,
                    refusals=self._caches.bearer_refusals,
                    ttl=ttls.token_account,
                    refusal_ttl=ttls.token_account_refusal,
                ),
            },
            without_credentials=CachedAuthenticator(
                TrustedNetworkAuthenticator(),
                key=self._client_key,
                cache=self._caches.trusted_network,
                refusals=self._caches.trusted_network_refusals,
                ttl=ttls.trusted_network,
                refusal_ttl=ttls.trusted_network_refusal,
            ),
        )

    def _create_encryption(self, ttls: CacheTtlsSnapshot, /) -> Encryption:
        return CachedEncryption(
            CertificateEncryption(),
            cache=self._caches.encryption,
            ttl=ttls.certificate,
        )

    def _create_checks(self, ttls: CacheTtlsSnapshot, /) -> _Checks:
        return _Checks(
            ttls=ttls,
            authenticator=self._create_authenticator(ttls),
            encryption=self._create_encryption(ttls),
        )

    def _create_default_profile(self, settings: SettingsSnapshot, checks: _Checks, /) -> Profile:
        """HTTP and SOCKS5 proxy for accounts and trusted networks from the database, going straight to targets.

        Each goes out from the IP its account or network says, within the limits of its and the global policies.
        Their traffic is counted in the database.
        Both may come wrapped in TLS with the active certificate from the database.
        Checks of clients and the certificate are reused for the cache TTLs from `settings`, by `checks`.
        Private networks are reachable only if `settings` allow them, timeouts come from `settings` too.
        """
        return Profile(
            inbounds=self._inbounds,
            authenticator=checks.authenticator,
            connector=DirectConnector(
                timeout=settings.connect_timeout,
                guard=AddressGuard(allow=settings.guard_allow),
                source=self._source,
            ),
            policies=[self._rule_set_policy],
            observers=self._observers,
            timeouts=Timeouts(
                handshake=settings.handshake_timeout,
                idle=settings.idle_timeout,
            ),
            encryption=checks.encryption,
        )

    def _create_listeners(self, profile: Profile, /) -> list[Listener]:
        return [
            Listener(
                host=host,
                ports=address.ports,
                profile=profile,
            )
            for address in self._listen
            for host in address.hosts
        ]

    async def _apply_settings(self, settings: SettingsSnapshot, /) -> None:
        # Kept on other changes: old and new connections share the checks in progress.
        previous = self._checks
        checks = previous
        if checks is None or checks.ttls != settings.cache_ttls:
            checks = self._create_checks(settings.cache_ttls)
        self._checks = checks

        # The same addresses: no socket is opened or closed, only the profile changes.
        await self._server.update(self._create_listeners(self._create_default_profile(settings, checks)))

        # A shorter TTL mustn't wait the longer one out. After the update, so no new connection stores with the old
        # TTL. A check in progress still may, once.
        if previous is not None:
            await self._caches.clear_shortened(previous.ttls, settings.cache_ttls)

    async def _apply_policies(self, policies: tuple[PolicySnapshot, ...], /) -> None:
        self._rule_set_policy.update(self._rule_set_builder.build(policies))

    def run(self) -> None:
        logging.basicConfig(level=self._log_level, format=LOG_FORMAT)
        try:
            uvloop.run(self._serve())
        except asyncio.CancelledError:
            logger.warning("Forced shutdown")
        except ListenError as error:
            logger.error("%s", error)
            raise SystemExit(1) from None
        except InvalidPolicyError as error:
            # Only at the start: later the proxy keeps the policies it has, see `PolicyWatcher`.
            logger.error("Can't start: %s", error)
            raise SystemExit(1) from None

    async def _serve(self) -> None:
        self._on_signal(self._stop.set)
        # Before listening, which the watchers start: every connection counts its traffic.
        self._traffic_observer.start()
        await self._watchers.start()
        await self._stop.wait()

        # A second signal cuts the graceful wait short.
        if task := asyncio.current_task():
            self._on_signal(task.cancel)

        logger.info("Shutting down, press Ctrl+C again to force")
        # First: a change applied during the shutdown would listen again.
        await self._watchers.close()
        await self._server.shutdown(timeout=self._graceful_timeout)
        # After the shutdown: closed connections have counted their last bytes.
        await self._traffic_observer.close()
        await session_manager.close()

    def _on_signal(self, callback: Callable[[], object], /) -> None:
        loop = asyncio.get_running_loop()
        for sig in self.signals:
            loop.add_signal_handler(sig, callback)


def run_proxy() -> None:
    runner: ProxyRunner = ProxyRunner()
    runner.run()
