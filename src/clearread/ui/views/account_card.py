"""The "Account" card of Settings (design system A.4.12)."""

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from clearread.services.account_client import AccountErrorKind
from clearread.ui.account_state import (
    AccountBusy,
    AccountInfo,
    SyncStatus,
    error_text_key,
)
from clearread.ui.dialogs import PrivacyNoticeDialog, make_confirm_box
from clearread.ui.icons import load_icon
from clearread.ui.strings import Language, tr
from clearread.ui.theme import ThemeTokens
from clearread.ui.views.delete_account_dialog import DeleteAccountDialog
from clearread.ui.views.flow_layout import FlowLayout
from clearread.ui.views.home_view import ElidedLabel, fit_button
from clearread.ui.views.login_pages import GoogleWaitingPage
from clearread.ui.views.login_widgets import (
    InlineMessage,
    google_button,
    link_button,
    text_label,
)

AVATAR_SIZE = 56
BADGE_HEIGHT = 24
MARK_WIDTH = 18
_SYNC_TEXT = {
    SyncStatus.OK: "account.sync_ok",
    SyncStatus.PENDING: "account.sync_pending",
    SyncStatus.FAILED: "account.sync_failed",
}
_SYNC_MARK = {SyncStatus.OK: "✓", SyncStatus.FAILED: "!"}
_BUSY_TEXT = {
    AccountBusy.SIGNING_OUT: "account.signing_out",
    AccountBusy.DELETING: "account.deleting",
}


class GoogleWaitingDialog(QDialog):
    """The waiting card of the login screen, as a modal dialog (A.4.13)."""

    cancelled = Signal()

    def __init__(
        self, parent: QWidget, tokens: ThemeTokens, language: Language
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(tr("google.waiting_title", language))
        self.page = GoogleWaitingPage(tokens, language)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.page)
        self.page.cancel_requested.connect(self.reject)
        shortcut = QShortcut(QKeySequence("Alt+Left"), self)
        shortcut.activated.connect(self.reject)

    def reject(self) -> None:
        self.cancelled.emit()
        super().reject()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.page.focus_first()


class AccountCard(QFrame):
    sign_out_requested = Signal()
    delete_requested = Signal(str)  # the password
    google_link_requested = Signal()
    google_cancel_requested = Signal()

    def __init__(
        self,
        info: AccountInfo,
        tokens: ThemeTokens,
        language: Language,
        show_dialog: Callable[[QMessageBox], None],
    ) -> None:
        super().__init__()
        self.setObjectName("Card")
        self._tokens = tokens
        self._language = language
        self._show_dialog = show_dialog
        self._status = SyncStatus.PENDING
        self.google_dialog: GoogleWaitingDialog | None = None
        self.privacy_dialog: PrivacyNoticeDialog | None = None
        self.delete_dialog: DeleteAccountDialog | None = None
        self._build_ui()
        self.set_info(info)
        self.set_sync_status(self._status)

    def _t(self, key: str, **params: object) -> str:
        return tr(key, self._language, **params)

    @property
    def status(self) -> SyncStatus:
        return self._status

    def _build_ui(self) -> None:
        title = QLabel(self._t("account.title"))
        title.setProperty("role", "heading")
        self.avatar = QLabel()
        self.avatar.setObjectName("Avatar")
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setFixedSize(AVATAR_SIZE, AVATAR_SIZE)
        self.name_label = ElidedLabel(role="name")
        self.email_label = ElidedLabel(role="muted")
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(self.name_label)
        texts.addWidget(self.email_label)
        self.badge = QLabel()
        self.badge.setObjectName("AccountBadge")
        self.badge.setFixedHeight(BADGE_HEIGHT)
        identity = QHBoxLayout()
        identity.setSpacing(12)
        identity.addWidget(self.avatar)
        identity.addLayout(texts, stretch=1)
        identity.addWidget(self.badge, alignment=Qt.AlignmentFlag.AlignTop)

        self.sync_mark = QLabel()
        self.sync_mark.setFixedWidth(MARK_WIDTH)
        self.sync_label = text_label("", "note")
        sync_row = QHBoxLayout()
        sync_row.setSpacing(6)
        sync_row.addWidget(self.sync_mark, alignment=Qt.AlignmentFlag.AlignTop)
        sync_row.addWidget(self.sync_label, stretch=1)
        self.offline_note = text_label(self._t("account.offline_note"), "note")
        self.offline_note.hide()
        self.busy_label = text_label("", "note")
        self.busy_label.hide()
        self.error_message = InlineMessage()

        self.google_button = google_button(self._t("account.google_link"))
        self.google_button.clicked.connect(self.google_link_requested)
        fit_button(self.google_button)
        self.google_label = QLabel(f"✓ {self._t('account.google_linked')}")
        self.google_label.setObjectName("AccountBadge")
        self.google_label.setFixedHeight(BADGE_HEIGHT)
        self.google_hint = text_label(
            self._t("account.google_needs_confirmation"), "note"
        )
        self.google_hint.hide()
        google_row = QHBoxLayout()
        google_row.addWidget(self.google_button)
        google_row.addWidget(self.google_label)
        google_row.addStretch(1)

        self.sign_out_button = QPushButton(self._t("account.sign_out"))
        self.sign_out_button.clicked.connect(self._confirm_sign_out)
        self.delete_button = link_button(self._t("account.delete"))
        self.delete_button.clicked.connect(self._confirm_delete)
        fit_button(self.sign_out_button)
        buttons = QWidget()
        buttons.setProperty("role", "plain")
        row = FlowLayout(buttons, spacing=12)
        row.addWidget(self.sign_out_button)
        row.addWidget(self.delete_button)
        local_note = text_label(self._t("account.local_note"), "note")
        self.privacy_button = link_button(self._t("auth.privacy_link"))
        self.privacy_button.clicked.connect(self.show_privacy_notice)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addLayout(identity)
        layout.addLayout(sync_row)
        layout.addWidget(self.offline_note)
        layout.addWidget(self.busy_label)
        layout.addWidget(self.error_message)
        layout.addLayout(google_row)
        layout.addWidget(self.google_hint)
        layout.addWidget(buttons)
        layout.addWidget(local_note)
        layout.addWidget(self.privacy_button, alignment=Qt.AlignmentFlag.AlignLeft)

    # ---- what is shown -------------------------------------------------

    def set_info(self, info: AccountInfo) -> None:
        self.name_label.set_full_text(info.name)
        self.email_label.set_full_text(info.email)
        initial = info.name.strip()[:1].upper()
        self.avatar.setText(initial or "?")
        self.avatar.setAccessibleName(self._t("account.avatar_a11y", name=info.name))
        self.badge.setVisible(info.verified is not None)
        if info.verified is not None:
            key, mark = (
                ("account.verified", "✓")
                if info.verified
                else ("account.not_verified", "!")
            )
            self.badge.setText(f"{mark} {self._t(key)}")
        self.google_button.setVisible(info.google_linked is False)
        self.google_label.setVisible(info.google_linked is True)
        self.google_hint.setVisible(
            info.google_linked is False and info.verified is False
        )

    def set_sync_status(self, status: SyncStatus) -> None:
        self._status = status
        self.sync_label.setText(self._t(_SYNC_TEXT[status]))
        self._show_sync_mark()

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self._show_sync_mark()

    def _show_sync_mark(self) -> None:
        mark = _SYNC_MARK.get(self._status)
        if mark is None:
            icon = load_icon("clock", self._tokens.text_muted)
            self.sync_mark.setPixmap(icon.pixmap(16, 16))
        else:
            self.sync_mark.setText(mark)

    def set_online(self, online: bool) -> None:
        self.offline_note.setVisible(not online)

    def set_busy(self, busy: AccountBusy | None) -> None:
        idle = busy is None
        self.sign_out_button.setEnabled(idle)
        self.google_button.setEnabled(idle)
        self.delete_button.setEnabled(idle)
        self.busy_label.setVisible(not idle)
        if busy is not None:
            self.busy_label.setText(self._t(_BUSY_TEXT[busy]))
            self.error_message.clear()

    def show_privacy_notice(self) -> None:
        dialog = PrivacyNoticeDialog(self, self._language)
        dialog.finished.connect(lambda: self._forget_privacy(dialog))
        self.privacy_dialog = dialog
        dialog.open()

    def _forget_privacy(self, dialog: PrivacyNoticeDialog) -> None:
        dialog.deleteLater()
        if self.privacy_dialog is dialog:
            self.privacy_dialog = None

    def show_error(self, kind: AccountErrorKind) -> None:
        self._close_delete_dialog()
        self.error_message.show_message(self._t(error_text_key(kind)))

    def show_wrong_delete_password(self) -> None:
        if self.delete_dialog is not None:
            self.delete_dialog.show_wrong_password()

    def set_google_starting(self, starting: bool) -> None:
        self.google_button.setEnabled(not starting)

    def show_google_waiting(self) -> None:
        self.error_message.clear()
        dialog = GoogleWaitingDialog(self.window(), self._tokens, self._language)
        dialog.cancelled.connect(self.google_cancel_requested)
        self.google_dialog = dialog
        dialog.open()

    def close_google_waiting(self) -> None:
        dialog, self.google_dialog = self.google_dialog, None
        if dialog is not None:
            dialog.cancelled.disconnect(self.google_cancel_requested)
            dialog.close()
            dialog.deleteLater()

    # ---- confirmations -------------------------------------------------

    def _confirm_sign_out(self) -> None:
        detail = self._t("account.sign_out_body")
        if self._status is not SyncStatus.OK:
            detail = f"{detail}\n\n{self._t('account.sign_out_pending')}"
        box, confirm = make_confirm_box(
            self,
            self._t("account.sign_out_title"),
            detail,
            self._t("account.sign_out"),
            self._language,
        )
        box.buttonClicked.connect(
            lambda clicked: (
                self.sign_out_requested.emit() if clicked is confirm else None
            )
        )
        self._show_dialog(box)

    def _confirm_delete(self) -> None:
        # Cancel is the highlighted answer and Enter never deletes (A.4.12).
        dialog = DeleteAccountDialog(self.window(), self._language)
        dialog.submitted.connect(self.delete_requested)
        dialog.finished.connect(lambda: self._forget_delete_dialog(dialog))
        self.delete_dialog = dialog
        dialog.open()

    def _forget_delete_dialog(self, dialog: DeleteAccountDialog) -> None:
        dialog.deleteLater()
        if self.delete_dialog is dialog:
            self.delete_dialog = None

    def _close_delete_dialog(self) -> None:
        dialog = self.delete_dialog
        if dialog is not None:
            dialog.dismiss()
