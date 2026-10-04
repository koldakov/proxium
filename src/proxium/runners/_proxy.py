import asyncio
import logging
import signal
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
from proxium.proxy import (
    AddressGuard,
    BasicCredentials,
    BearerCredentials,
    CachedEncryption,
    DirectConnector,
    DispatchAuthenticator,
    HttpInbound,
    Listener,
    ListenError,
    LoggingObserver,
    Profile,
    ProxyServer,
    Socks5Inbound,
    Timeouts,
)
from proxium.selectors import OutgoingSourceSelector
from proxium.watchers import SettingsSnapshot, SettingsWatcher

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from proxium.core import ListenAddress, LogLevel
    from proxium.proxy import Authenticator, Encryption, Inbound, Observer, SourceSelector

logger = logging.getLogger(__name__)

LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s: %(message)s"


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
        self._authenticator: Authenticator = DispatchAuthenticator(
            {
                BasicCredentials: BasicProxyAccountAuthenticator(),
                BearerCredentials: TokenProxyAccountAuthenticator(),
            },
            without_credentials=TrustedNetworkAuthenticator(),
        )
        self._source: SourceSelector = OutgoingSourceSelector()
        self._observers: list[Observer] = [
            LoggingObserver(),
            self._traffic_observer,
        ]
        self._encryption: Encryption = CachedEncryption(CertificateEncryption())
        self._settings_watcher: SettingsWatcher = SettingsWatcher(
            self._apply_settings,
            interval=settings_poll_interval,
        )
        self._graceful_timeout: float = graceful_timeout
        self._listen: Sequence[ListenAddress] = listen

        self._server: ProxyServer = ProxyServer()
        self._stop: asyncio.Event = asyncio.Event()

    def _create_default_profile(self, settings: SettingsSnapshot, /) -> Profile:
        """HTTP and SOCKS5 proxy for accounts and trusted networks from the database, going straight to targets.

        Each goes out from the IP its account or network says. Their traffic is counted in the database.
        Both may come wrapped in TLS with the active certificate from the database, looked up every few seconds.
        Private networks are reachable only if `settings` allow them, timeouts come from `settings` too.
        """
        return Profile(
            inbounds=self._inbounds,
            authenticator=self._authenticator,
            connector=DirectConnector(
                timeout=settings.connect_timeout,
                guard=AddressGuard(allow=settings.guard_allow),
                source=self._source,
            ),
            observers=self._observers,
            timeouts=Timeouts(
                handshake=settings.handshake_timeout,
                idle=settings.idle_timeout,
            ),
            encryption=self._encryption,
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
        # The same addresses: no socket is opened or closed, only the profile changes.
        await self._server.update(self._create_listeners(self._create_default_profile(settings)))

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
        self._traffic_observer.start()
        await self._server.update(self._create_listeners(self._create_default_profile(settings)))
        self._settings_watcher.start()
        await self._stop.wait()

        # A second signal cuts the graceful wait short.
        if task := asyncio.current_task():
            self._on_signal(task.cancel)

        logger.info("Shutting down, press Ctrl+C again to force")
        # First: a change applied during the shutdown would listen again.
        await self._settings_watcher.close()
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
