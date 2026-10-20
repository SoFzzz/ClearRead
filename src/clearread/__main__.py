"""Entry point for `python -m clearread` and the `clearread` script."""

import sys

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication

from clearread.core.config import (
    AppConfig,
    load_client_token,
    resolve_backend_url,
)
from clearread.core.device_settings import (
    DEVICE_FILE,
    DeviceSettingsStore,
    seed_from_legacy_config,
)
from clearread.core.paths import get_profile_dir, get_user_data_dir
from clearread.core.restart import current_relaunch_command
from clearread.services.account_client import AccountClient
from clearread.services.ai_client import BackendAIClient, DiskResponseCache
from clearread.services.backend_transport import BackendTransport, BearerSource
from clearread.services.browser_launcher import BrowserLauncher
from clearread.services.network_monitor import NetworkMonitor
from clearread.services.ocr_engine import LazyOCREngine
from clearread.services.session_manager import SessionManager
from clearread.services.session_store import SESSION_FILE, SessionStore
from clearread.services.tts_controller import TTSController
from clearread.ui.app_controller import AppController, AppServices
from clearread.ui.app_icon import load_app_icon, set_windows_app_id
from clearread.ui.fonts import load_reading_font
from clearread.workers.account_tasks import AccountTaskRunner
from clearread.workers.account_worker import create_account_thread_pool


def relaunch() -> None:
    command = current_relaunch_command()
    QProcess.startDetached(command.program, command.arguments)


def make_ai_client(
    config: AppConfig, cache: DiskResponseCache, bearer: BearerSource
) -> BackendAIClient:
    return BackendAIClient(
        resolve_backend_url(config.backend_url),
        load_client_token(),
        cache,
        config.ui_language,
        bearer_source=bearer,
    )


def build_services() -> AppServices:
    data_dir = get_user_data_dir()
    backend_url = resolve_backend_url()
    client = AccountClient(BackendTransport(backend_url, load_client_token()))
    device = DeviceSettingsStore(data_dir / DEVICE_FILE)
    seed_from_legacy_config(device, data_dir)
    return AppServices(
        data_dir=data_dir,
        profile_dir_for=get_profile_dir,
        client=client,
        session=SessionManager(client, SessionStore(data_dir / SESSION_FILE)),
        runner=AccountTaskRunner(create_account_thread_pool()),
        device=device,
        network=NetworkMonitor.from_system(),
        ocr_engine=LazyOCREngine(),
        make_tts=TTSController,
        make_ai_client=make_ai_client,
        open_page=BrowserLauncher(backend_url).open_backend_page,
    )


def main() -> int:
    """Start ClearRead Desktop and return the process exit code."""
    set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("ClearRead")
    app.setWindowIcon(load_app_icon())
    load_reading_font()
    controller = AppController(build_services())
    controller.start()
    exit_code = app.exec()
    if controller.restart_requested:
        relaunch()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
