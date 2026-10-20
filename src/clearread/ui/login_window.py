"""Window shown while nobody is signed in: the brand bar and the login view (A.4.1)."""

from collections.abc import Callable

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from clearread.core.device_settings import DeviceSettings
from clearread.services.account_client import AccountClient
from clearread.services.network_monitor import NetworkMonitor
from clearread.services.session_manager import SessionManager
from clearread.ui.app_icon import load_app_icon
from clearread.ui.focus_ring import KeyboardFocusRing
from clearread.ui.google_flow import POLL_INTERVAL_MS, GoogleFlow
from clearread.ui.strings import Language
from clearread.ui.theme import THEMES, ThemeId, build_stylesheet
from clearread.ui.views.login_view import LoginView
from clearread.workers.account_tasks import AccountTaskRunner

MIN_WINDOW_SIZE = (1024, 700)
TOP_BAR_HEIGHT = 56
BRAND_ICON_PX = 28


class LoginWindow(QMainWindow):
    def __init__(
        self,
        client: AccountClient,
        session: SessionManager,
        runner: AccountTaskRunner,
        network: NetworkMonitor,
        device: DeviceSettings,
        open_page: Callable[[str], bool],
        google_poll_ms: int = POLL_INTERVAL_MS,
    ) -> None:
        super().__init__()
        tokens = THEMES[ThemeId(device.theme)]
        self.setMinimumSize(*MIN_WINDOW_SIZE)
        self.setWindowTitle("ClearRead")
        self.setStyleSheet(build_stylesheet(tokens))
        self.google = GoogleFlow(
            client, session, runner, open_page, google_poll_ms, parent=self
        )
        self.view = LoginView(
            client, session, runner, tokens, Language(device.ui_language), self.google
        )
        self.view.set_online(network.is_online)
        network.online_changed.connect(self.view.set_online)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_brand_bar())
        layout.addWidget(self.view, stretch=1)
        self.setCentralWidget(central)
        self._focus_ring = KeyboardFocusRing(self)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self._focus_ring)

    @staticmethod
    def _build_brand_bar() -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(TOP_BAR_HEIGHT)
        icon = QLabel()
        icon.setPixmap(load_app_icon().pixmap(BRAND_ICON_PX, BRAND_ICON_PX))
        brand = QLabel("ClearRead")
        brand.setObjectName("Brand")
        row = QHBoxLayout(bar)
        row.setContentsMargins(24, 0, 24, 0)
        row.setSpacing(10)
        row.addWidget(icon)
        row.addWidget(brand)
        row.addStretch(1)
        return bar

    def closeEvent(self, event: QCloseEvent) -> None:
        self.google.cancel()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self._focus_ring)
        event.accept()
