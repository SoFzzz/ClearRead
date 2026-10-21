"""Login screen: sign in, create account, reset password (design system A.4.11, A.5.4).

It sends the requests through the account workers and reports a successful sign in with
``signed_in``; it knows nothing about the window that comes next.
"""

from collections.abc import Callable
from enum import Enum
from functools import partial

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from clearread.services.account_client import (
    AccountClient,
    AccountErrorKind,
    GoogleMode,
)
from clearread.services.session_manager import SessionManager
from clearread.services.session_store import Session
from clearread.ui.dialogs import PrivacyNoticeDialog
from clearread.ui.google_flow import GoogleFlow
from clearread.ui.strings import Language, tr
from clearread.ui.theme import ThemeTokens
from clearread.ui.views.login_pages import (
    CARD_WIDTH,
    FormPage,
    GoogleWaitingPage,
    RegisterPage,
    ResetPage,
    SignInPage,
)
from clearread.ui.views.login_widgets import CurrentPageStack, plain
from clearread.workers.account_tasks import AccountTaskRunner
from clearread.workers.account_worker import (
    PasswordResetWorker,
    RegisterWorker,
    SignInWorker,
)

PAGE_MARGIN = 32


class LoginPage(Enum):
    SIGN_IN = 0
    REGISTER = 1
    RESET = 2
    GOOGLE_WAITING = 3


class LoginView(QWidget):
    signed_in = Signal(object)  # Session

    def __init__(
        self,
        client: AccountClient,
        session: SessionManager,
        runner: AccountTaskRunner,
        tokens: ThemeTokens,
        language: Language,
        google: GoogleFlow,
    ) -> None:
        super().__init__()
        self._client = client
        self._google = google
        self._session = session
        self._runner = runner
        self._language = language
        self._request = 0  # identifies the request whose answer is still wanted
        self._busy = False
        self.privacy_dialog: PrivacyNoticeDialog | None = None
        self.sign_in_page = SignInPage(tokens, language)
        self.register_page = RegisterPage(tokens, language)
        self.reset_page = ResetPage(tokens, language)
        self.google_page = GoogleWaitingPage(tokens, language)
        self._pages = (
            self.sign_in_page,
            self.register_page,
            self.reset_page,
            self.google_page,
        )
        self.stack = CurrentPageStack()
        for page in self._pages:
            self.stack.addWidget(page)
        self.offline_badge = QLabel(tr("ai.offline_badge", language))
        self.offline_badge.setObjectName("OfflineBadge")
        self.offline_badge.hide()
        self._build_layout()
        self._connect_pages()
        self._add_shortcuts()

    @property
    def current_page(self) -> LoginPage:
        return LoginPage(self.stack.currentIndex())

    def _build_layout(self) -> None:
        column = plain(QWidget())
        column.setFixedWidth(CARD_WIDTH)
        inner = QVBoxLayout(column)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(8)
        inner.addWidget(self.offline_badge, alignment=Qt.AlignmentFlag.AlignRight)
        inner.addWidget(self.stack)

        centered = QHBoxLayout()
        centered.addStretch(1)
        centered.addWidget(column)
        centered.addStretch(1)
        holder = QWidget()
        outer = QVBoxLayout(holder)
        outer.setContentsMargins(*(PAGE_MARGIN,) * 4)
        outer.addStretch(1)
        outer.addLayout(centered)
        outer.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(holder)
        self.scroll = scroll
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def _connect_pages(self) -> None:
        self.sign_in_page.submitted.connect(self._sign_in)
        self.sign_in_page.register_requested.connect(
            lambda: self.show_page(LoginPage.REGISTER)
        )
        self.sign_in_page.reset_requested.connect(
            lambda: self.show_page(LoginPage.RESET)
        )
        self.register_page.submitted.connect(self._register)
        self.register_page.back_requested.connect(self.go_back)
        self.register_page.privacy_requested.connect(self.show_privacy_notice)
        self.sign_in_page.privacy_requested.connect(self.show_privacy_notice)
        self.reset_page.send_requested.connect(self._send_reset)
        self.reset_page.back_requested.connect(self.go_back)
        for page in (self.sign_in_page, self.register_page, self.reset_page):
            page.cancel_requested.connect(self._cancel_request)
        self.sign_in_page.google_requested.connect(self._start_google)
        self.google_page.cancel_requested.connect(self._cancel_google)
        self._google.starting.connect(self._on_google_starting)
        self._google.waking.connect(self.sign_in_page.show_waking)
        self._google.waiting.connect(self._on_google_waiting)
        self._google.signed_in.connect(self.signed_in)
        self._google.failed.connect(self._on_google_failed)

    def _add_shortcuts(self) -> None:
        for sequence in ("Esc", "Alt+Left"):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(self.go_back)

    # ---- navigation ----------------------------------------------------

    def show_page(self, page: LoginPage) -> None:
        typed = self.sign_in_page.email.edit.text().strip()
        if page is LoginPage.RESET:
            self.reset_page.restart(typed)
        elif (
            page is LoginPage.REGISTER
            and typed
            and not self.register_page.email.edit.text()
        ):
            self.register_page.email.edit.setText(typed)
        self.stack.setCurrentIndex(page.value)
        self._pages[page.value].focus_first()

    def go_back(self) -> None:
        """Esc and Alt+Left: no way back from the first page (the account is required)."""
        if self.current_page is LoginPage.GOOGLE_WAITING:
            self._cancel_google()
        elif not self._busy and self.current_page is not LoginPage.SIGN_IN:
            self.show_page(LoginPage.SIGN_IN)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._pages[self.stack.currentIndex()].focus_first()

    def show_privacy_notice(self) -> None:
        dialog = PrivacyNoticeDialog(self, self._language)
        dialog.finished.connect(lambda: self._forget_privacy(dialog))
        self.privacy_dialog = dialog
        dialog.open()

    def _forget_privacy(self, dialog: PrivacyNoticeDialog) -> None:
        dialog.deleteLater()
        if self.privacy_dialog is dialog:
            self.privacy_dialog = None

    # ---- state shown from outside --------------------------------------

    def set_online(self, online: bool) -> None:
        self.offline_badge.setVisible(not online)
        self.sign_in_page.set_online(online)

    def show_session_ended(self) -> None:
        self.show_page(LoginPage.SIGN_IN)
        self.sign_in_page.show_session_ended()

    def show_account_deleted(self) -> None:
        self.show_page(LoginPage.SIGN_IN)
        self.sign_in_page.show_account_deleted()

    # ---- requests ------------------------------------------------------

    def _sign_in(self, email: str, password: str) -> None:
        worker = SignInWorker(self._client, self._session, email, password)
        self._start(worker, self.sign_in_page, self.signed_in.emit)

    def _register(self, name: str, email: str, password: str) -> None:
        worker = RegisterWorker(self._client, self._session, email, password, name)
        self._start(worker, self.register_page, self.signed_in.emit)

    def _send_reset(self, email: str) -> None:
        worker = PasswordResetWorker(self._client, email)
        self._start(
            worker, self.reset_page, lambda _result: self.reset_page.show_done(email)
        )

    def _start(
        self,
        worker: SignInWorker | RegisterWorker | PasswordResetWorker,
        page: FormPage | ResetPage,
        on_done: Callable[[object], None],
    ) -> None:
        self._request += 1
        request = self._request
        self._busy = True
        page.set_busy(True)
        self._runner.run(
            worker,
            on_finished=partial(self._on_finished, request, page, on_done),
            on_failed=partial(self._on_failed, request, page),
            on_waking=partial(self._on_waking, request, page),
        )

    def _cancel_request(self) -> None:
        """Stop waiting: the worker ends by itself and its answer is dropped."""
        self._request += 1
        self._busy = False
        self._google.cancel()
        self.sign_in_page.set_google_starting(False)
        for page in (self.sign_in_page, self.register_page, self.reset_page):
            page.set_busy(False)

    # ---- Google --------------------------------------------------------

    def _start_google(self) -> None:
        self._google.start(GoogleMode.SIGN_IN)

    def _on_google_starting(self) -> None:
        self._busy = True
        self.sign_in_page.set_google_starting(True)

    def _on_google_waiting(self) -> None:
        self._busy = False
        self.sign_in_page.set_google_starting(False)
        self.show_page(LoginPage.GOOGLE_WAITING)

    def _cancel_google(self) -> None:
        self._google.cancel()
        self._busy = False
        self.sign_in_page.set_google_starting(False)
        self.show_page(LoginPage.SIGN_IN)

    def _on_google_failed(self, kind: AccountErrorKind) -> None:
        self._busy = False
        self.sign_in_page.set_google_starting(False)
        self.show_page(LoginPage.SIGN_IN)
        self.sign_in_page.show_error(kind)

    def _on_waking(self, request: int, page: FormPage | ResetPage) -> None:
        if request == self._request:
            page.show_waking()

    def _on_finished(
        self,
        request: int,
        page: FormPage | ResetPage,
        on_done: Callable[[object], None],
        result: object,
    ) -> None:
        if request != self._request:
            self._forget_stray_session(result)
            return
        self._busy = False
        page.set_busy(False)
        on_done(result)

    def _on_failed(
        self, request: int, page: FormPage | ResetPage, kind: AccountErrorKind
    ) -> None:
        if request != self._request:
            return
        self._busy = False
        page.set_busy(False)
        self._forget_stray_session(None)
        page.show_error(kind)

    def _forget_stray_session(self, result: object) -> None:
        """A request the person gave up on signed in anyway: undo it.

        This screen only shows while nobody is signed in, so any identity held while no
        request is wanted comes from such an abandoned request.
        """
        abandoned = result is None or isinstance(result, Session)
        if abandoned and not self._busy and self._session.identity is not None:
            self._session.sign_out()
