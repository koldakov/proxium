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
from proxium.policies import RuleSetBuilder, RuleSetPolicy
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
from proxium.watchers import PolicyWatcher, SettingsSnapshot, SettingsWatcher

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
    from proxium.watchers import PolicySnapshot

logger = logging.getLogger(__name__)

LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def _get_identity_size(identity: Identity, /) -> int:
    """One plus the pool IPs: an identity with a big pool takes as much memory as many without."""
    return 1 + len(identity.claims.get(OUTGOING_IPS_CLAIM, ()))


@dataclass(frozen=True, slots=True)
class _Caches:
    """Where the proxy keeps checks of clients and the certificate between connections."""

    basic: Cache[Identity]
    basic_refusals: Cache[AuthenticationRequired]
    bearer: Cache[Identity]
    bearer_refusals: Cache[AuthenticationRequired]
    trusted_network: Cache[Identity]
    trusted_network_refusals: Cache[AuthenticationRequired]
    encryption: Cache[EncryptionOutcome]

    async def clear(self) -> None:
        await self.basic.clear()
        await self.basic_refusals.clear()
        await self.bearer.clear()
        await self.bearer_refusals.clear()
        await self.trusted_network.clear()
        await self.trusted_network_refusals.clear()
        await self.encryption.clear()


@dataclass(frozen=True, slots=True)
class _Checks:
    """Checks of clients and the certificate, reusing what's cached for `ttl` seconds."""

    ttl: float
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
        self._caches: _Caches = _Caches(
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
        self._settings_watcher: SettingsWatcher = SettingsWatcher(
            self._apply_settings,
            interval=settings_poll_interval,
        )
        # Kept across settings changes: their limits count open connections. Rules change in place.
        self._rule_set_policy: RuleSetPolicy = RuleSetPolicy()
        self._rule_set_builder: RuleSetBuilder = RuleSetBuilder()
        self._policy_watcher: PolicyWatcher = PolicyWatcher(
            self._apply_policies,
            interval=settings_poll_interval,
        )
        self._graceful_timeout: float = graceful_timeout
        self._listen: Sequence[ListenAddress] = listen

        self._server: ProxyServer = ProxyServer()
        self._stop: asyncio.Event = asyncio.Event()

    def _create_authenticator(self, ttl: float, /) -> Authenticator:
        return DispatchAuthenticator(
            {
                BasicCredentials: CachedAuthenticator(
                    BasicProxyAccountAuthenticator(),
                    key=self._credentials_key,
                    cache=self._caches.basic,
                    refusals=self._caches.basic_refusals,
                    ttl=ttl,
                ),
                BearerCredentials: CachedAuthenticator(
                    TokenProxyAccountAuthenticator(),
                    key=self._credentials_key,
                    cache=self._caches.bearer,
                    refusals=self._caches.bearer_refusals,
                    ttl=ttl,
                ),
            },
            without_credentials=CachedAuthenticator(
                TrustedNetworkAuthenticator(),
                key=self._client_key,
                cache=self._caches.trusted_network,
                refusals=self._caches.trusted_network_refusals,
                ttl=ttl,
            ),
        )

    def _create_encryption(self, ttl: float, /) -> Encryption:
        return CachedEncryption(
            CertificateEncryption(),
            cache=self._caches.encryption,
            ttl=ttl,
        )

    def _create_checks(self, ttl: float, /) -> _Checks:
        return _Checks(
            ttl=ttl,
            authenticator=self._create_authenticator(ttl),
            encryption=self._create_encryption(ttl),
        )

    def _create_default_profile(self, settings: SettingsSnapshot, checks: _Checks, /) -> Profile:
        """HTTP and SOCKS5 proxy for accounts and trusted networks from the database, going straight to targets.

        Each goes out from the IP its account or network says, within the limits of its and the global policies.
        Their traffic is counted in the database.
        Both may come wrapped in TLS with the active certificate from the database.
        Checks of clients and the certificate are reused for the cache TTL from `settings`, by `checks`.
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
        if checks is None or checks.ttl != settings.cache_ttl:
            checks = self._create_checks(settings.cache_ttl)
        self._checks = checks

        # The same addresses: no socket is opened or closed, only the profile changes.
        await self._server.update(self._create_listeners(self._create_default_profile(settings, checks)))

        # What's cached keeps the TTL it was stored with: a shorter one mustn't wait the longer one out.
        # After the update, so no new connection stores with the old TTL. A check in progress still may, once.
        if previous is not None and settings.cache_ttl < previous.ttl:
            await self._caches.clear()

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

    async def _serve(self) -> None:
        self._on_signal(self._stop.set)
        settings = await self._settings_watcher.load()
        # Before listening: no connection goes through without its limits.
        await self._apply_policies(await self._policy_watcher.load())
        self._traffic_observer.start()
        await self._apply_settings(settings)
        self._settings_watcher.start()
        self._policy_watcher.start()
        await self._stop.wait()

        # A second signal cuts the graceful wait short.
        if task := asyncio.current_task():
            self._on_signal(task.cancel)

        logger.info("Shutting down, press Ctrl+C again to force")
        # First: a change applied during the shutdown would listen again.
        await self._settings_watcher.close()
        await self._policy_watcher.close()
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
