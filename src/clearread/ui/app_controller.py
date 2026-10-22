"""Which window is open and why: login, or the main window of one account (v1.6).

This is the only place that knows both windows. It opens the profile of a stored or new
session, keeps it in step with the account, and brings the login screen back when the
person signs out, deletes the account or the account ends the session.
"""

import os
import shutil
import stat
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from functools import partial
from pathlib import Path

from PySide6.QtCore import QObject

from clearread.core.config import AppConfig
from clearread.core.device_settings import DeviceSettings, DeviceSettingsStore
from clearread.services.account_client import (
    AccountClient,
    AccountErrorKind,
    GoogleMode,
)
from clearread.services.ai_client import AIClient, DiskResponseCache
from clearread.services.network_monitor import NetworkMonitor
from clearread.services.ocr_engine import OCREngine
from clearread.services.profile_migration import LEGACY_ITEMS, adopt_legacy_data
from clearread.services.profile_stores import ProfileStores, open_profile_stores
from clearread.services.profile_sync import SyncStateStore
from clearread.services.session_manager import SessionManager
from clearread.services.session_store import Session, StoredSession
from clearread.services.tts_controller import TTSController
from clearread.ui.account_state import AccountBusy, AccountInfo
from clearread.ui.google_flow import POLL_INTERVAL_MS, GoogleFlow
from clearread.ui.login_window import LoginWindow
from clearread.ui.main_window import MainWindow
from clearread.ui.sync_controller import DEBOUNCE_MS, SyncController
from clearread.workers.account_tasks import AccountTaskRunner
from clearread.workers.account_worker import DeleteAccountWorker, RefreshSessionWorker

WINDOW_SIZE = (1280, 800)
_ENDED_KINDS = (AccountErrorKind.SESSION_REVOKED, AccountErrorKind.INVALID_SESSION)


def remove_profile_folder(profile_dir: Path) -> None:
    """Delete one profile folder; a read-only file must not leave the data behind."""

    def make_writable_and_retry(
        function: Callable[[str], object], path: str, _error: object
    ) -> None:
        os.chmod(path, stat.S_IWRITE)
        function(path)

    shutil.rmtree(profile_dir, onerror=make_writable_and_retry)


class LoginNotice(Enum):
    SESSION_ENDED = "session_ended"
    ACCOUNT_DELETED = "account_deleted"


@dataclass(frozen=True)
class AppServices:
    """What the app is built from; tests pass fakes for every piece."""

    data_dir: Path
    profile_dir_for: Callable[[str], Path]
    client: AccountClient
    session: SessionManager
    runner: AccountTaskRunner
    device: DeviceSettingsStore
    network: NetworkMonitor
    ocr_engine: OCREngine
    make_tts: Callable[[], TTSController]
    make_ai_client: Callable[[AppConfig, DiskResponseCache, SessionManager], AIClient]
    open_page: Callable[[str], bool]  # BrowserLauncher.open_backend_page
    sync_debounce_ms: int = DEBOUNCE_MS
    google_poll_ms: int = POLL_INTERVAL_MS


class AppController(QObject):
    def __init__(self, services: AppServices) -> None:
        super().__init__()
        self._services = services
        self._generation = 0  # tells answers of a closed profile from the open one
        self._profile_dir: Path | None = None
        self._account_refreshed = False
        self._device = services.device.load()
        self.window: MainWindow | None = None
        self.login_window: LoginWindow | None = None
        self.sync: SyncController | None = None
        self.google = GoogleFlow(
            services.client,
            services.session,
            services.runner,
            services.open_page,
            services.google_poll_ms,
            parent=self,
        )
        self.google.starting.connect(self._google_starting)
        self.google.waiting.connect(self._google_waiting)
        self.google.linked.connect(self._google_linked)
        self.google.failed.connect(self._google_failed)
        self._info: AccountInfo | None = None
        services.network.online_changed.connect(self._on_online_changed)

    @property
    def restart_requested(self) -> bool:
        return self.window is not None and self.window.restart_requested

    def start(self) -> None:
        identity = self._services.session.resume()
        if identity is None:
            self.show_login()
        else:
            self._open_profile(identity, AccountInfo.from_identity(identity), False)

    # ---- login ---------------------------------------------------------

    def show_login(self, notice: LoginNotice | None = None) -> None:
        window = LoginWindow(
            self._services.client,
            self._services.session,
            self._services.runner,
            self._services.network,
            self._services.device.load(),
            self._services.open_page,
            self._services.google_poll_ms,
        )
        window.view.signed_in.connect(self._on_signed_in)
        if notice is LoginNotice.SESSION_ENDED:
            window.view.show_session_ended()
        elif notice is LoginNotice.ACCOUNT_DELETED:
            window.view.show_account_deleted()
        window.resize(*WINDOW_SIZE)
        window.show()
        self.login_window = window

    def _on_signed_in(self, session: object) -> None:
        if not isinstance(session, Session):
            return
        identity = StoredSession(
            session.uid, session.email, session.display_name, session.refresh_token
        )
        self._open_profile(identity, AccountInfo.from_session(session), True)
        self._close_login()

    def _close_login(self) -> None:
        window, self.login_window = self.login_window, None
        if window is not None:
            window.close()
            window.deleteLater()

    # ---- the profile window --------------------------------------------

    def _open_profile(
        self, identity: StoredSession, info: AccountInfo, signed_in_now: bool
    ) -> None:
        services = self._services
        self._generation += 1
        profile_dir = services.profile_dir_for(identity.uid)
        had_old_files = any((services.data_dir / n).exists() for n in LEGACY_ITEMS)
        adopted = adopt_legacy_data(services.data_dir, profile_dir, identity.uid)
        stores = open_profile_stores(profile_dir)
        window = self._make_window(stores, info)
        self._profile_dir = profile_dir
        self.window = window
        self.sync = self._make_sync(window, stores, profile_dir)
        self._info = info
        self._connect_google(window)
        self._wire(window, self.sync)
        self._remember_device(stores.config.theme, stores.config.ui_language)
        window.follow_language_voice()
        window.resize(*WINDOW_SIZE)
        window.show()
        if adopted and had_old_files:
            window.show_notice("profile.migrated")
        self._account_refreshed = signed_in_now
        if not signed_in_now and services.network.is_online:
            self._refresh_account()
        self.sync.sync_now()

    def _make_window(self, stores: ProfileStores, info: AccountInfo) -> MainWindow:
        services = self._services
        return MainWindow(
            config=stores.config,
            ocr_engine=services.ocr_engine,
            tts=services.make_tts(),
            library=stores.library,
            config_dir=stores.directory,
            ai_client=services.make_ai_client(
                stores.config, stores.ai_cache, services.session
            ),
            network=services.network,
            glossary=stores.glossary,
            stats=stores.stats,
            folders=stores.folders,
            topics=stores.topics,
            account=info,
        )

    def _make_sync(
        self, window: MainWindow, stores: ProfileStores, profile_dir: Path
    ) -> SyncController:
        services = self._services
        return SyncController(
            services.client,
            services.session,
            services.runner,
            SyncStateStore(profile_dir),
            lambda: window.config,
            stores.glossary,
            stores.topics,
            online=services.network.is_online,
            debounce_ms=services.sync_debounce_ms,
            parent=self,
        )

    def _connect_google(self, window: MainWindow) -> None:
        window.google_link_requested.connect(self._link_google)
        window.google_cancel_requested.connect(self.google.cancel)

    def _link_google(self) -> None:
        self.google.start(GoogleMode.LINK)

    def _google_starting(self) -> None:
        if self.window is not None:
            self.window.set_google_starting(True)

    def _google_waiting(self) -> None:
        if self.window is not None:
            self.window.set_google_starting(False)
            self.window.show_google_waiting()

    def _google_linked(self) -> None:
        window = self.window
        if window is None:
            return
        window.set_google_starting(False)
        window.close_google_waiting()
        if self._info is not None:
            self._info = replace(self._info, google_linked=True)
            window.set_account(self._info)
        # Linking can also confirm the email, which only the backend knows.
        if self._services.network.is_online:
            self._refresh_account()

    def _google_failed(self, kind: AccountErrorKind) -> None:
        window = self.window
        if window is None:
            return
        window.set_google_starting(False)
        window.close_google_waiting()
        if kind in _ENDED_KINDS:
            self._on_session_ended()
        else:
            window.show_account_error(kind)
            if kind is AccountErrorKind.EMAIL_NOT_VERIFIED:
                # The session may be stale: refresh it so the card tells the truth.
                self._refresh_account()

    def _wire(self, window: MainWindow, sync: SyncController) -> None:
        window.profile_changed.connect(sync.notify_changed)
        window.device_preferences_changed.connect(self._remember_device)
        window.sign_out_requested.connect(self._sign_out)
        window.delete_account_requested.connect(self._delete_account)
        window.session_check_requested.connect(self._refresh_account)
        sync.status_changed.connect(window.set_sync_status)
        sync.config_pulled.connect(window.apply_remote_config)
        sync.session_ended.connect(self._on_session_ended)

    def _remember_device(self, theme: str, language: str) -> None:
        settings = DeviceSettings(theme, language)
        if settings != self._device:
            self._device = settings
            self._services.device.save(settings)

    def _on_online_changed(self, online: bool) -> None:
        if self.sync is None:
            return
        if online and not self._account_refreshed:
            self._refresh_account()
        self.sync.set_online(online)

    # ---- the account ---------------------------------------------------

    def _refresh_account(self) -> None:
        """Ask the account who this is; a revoked session ends here."""
        generation = self._generation
        self._services.runner.run(
            RefreshSessionWorker(self._services.client, self._services.session),
            on_finished=partial(self._on_refreshed, generation),
            on_failed=partial(self._on_refresh_failed, generation),
        )

    def _on_refreshed(self, generation: int, result: object) -> None:
        if generation != self._generation or self.window is None:
            return
        if isinstance(result, Session):
            self._account_refreshed = True
            self._info = AccountInfo.from_session(result)
            self.window.set_account(self._info)

    def _on_refresh_failed(self, generation: int, kind: AccountErrorKind) -> None:
        if generation == self._generation and kind in _ENDED_KINDS:
            self._on_session_ended()

    def _on_session_ended(self) -> None:
        self._end_session(LoginNotice.SESSION_ENDED)

    def _sign_out(self) -> None:
        if self.window is None or self.sync is None:
            return
        self.window.set_account_busy(AccountBusy.SIGNING_OUT)
        self.sync.flush(partial(self._finish_sign_out, self._generation))

    def _finish_sign_out(self, generation: int) -> None:
        if generation == self._generation:
            self._end_session(None)

    def _delete_account(self, password: str) -> None:
        if self.window is None or self.sync is None:
            return
        self.window.set_account_busy(AccountBusy.DELETING)
        self.sync.suspend()
        generation = self._generation
        self._services.runner.run(
            DeleteAccountWorker(
                self._services.client, self._services.session, password
            ),
            on_finished=partial(self._on_deleted, generation),
            on_failed=partial(self._on_delete_failed, generation),
        )

    def _on_deleted(self, generation: int, _result: object) -> None:
        if generation == self._generation:
            self._end_session(LoginNotice.ACCOUNT_DELETED, remove_profile=True)

    def _on_delete_failed(self, generation: int, kind: AccountErrorKind) -> None:
        if generation != self._generation or self.window is None or self.sync is None:
            return
        if kind in _ENDED_KINDS:
            self._on_session_ended()
            return
        self.window.set_account_busy(None)
        if kind is AccountErrorKind.INVALID_CREDENTIALS:
            self.window.show_wrong_delete_password()
        else:
            self.window.show_account_error(kind)
        self.sync.resume()

    def _end_session(
        self, notice: LoginNotice | None, remove_profile: bool = False
    ) -> None:
        """Back to the login screen; nothing of the old profile stays on screen."""
        self._generation += 1
        if self.sync is not None:
            self.sync.shutdown()
            self.sync.deleteLater()
            self.sync = None
        self.google.cancel()
        self._services.session.sign_out()
        self.show_login(notice)
        window, self.window = self.window, None
        profile_dir, self._profile_dir = self._profile_dir, None
        if window is not None:
            window.close()
            window.deleteLater()
        if remove_profile and profile_dir is not None:
            remove_profile_folder(profile_dir)
