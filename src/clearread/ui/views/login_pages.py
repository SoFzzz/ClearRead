"""The three cards of the login screen: sign in, create account, reset password (A.4.11).

Pages only collect and check what the person types; they never talk to the network. The
view that owns them sends the requests and tells each page how it went.
"""

import re

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from clearread.services.account_client import AccountErrorKind
from clearread.ui.account_state import error_text_key
from clearread.ui.strings import Language, tr
from clearread.ui.theme import ThemeTokens
from clearread.ui.views.login_widgets import (
    EMAIL_MAX_CHARS,
    NAME_MAX_CHARS,
    PASSWORD_MAX_CHARS,
    BusyStrip,
    ConsentRow,
    CurrentPageStack,
    FieldBlock,
    InlineMessage,
    WrappingColumn,
    chain_tab_order,
    divider_with_text,
    email_block,
    google_button,
    height_at_width,
    link_button,
    make_text_edit,
    password_block,
    plain,
    separator,
    set_variant,
    text_label,
)

CARD_WIDTH = 440
CARD_PADDING = 32
CARD_SPACING = 16
STEP_WIDTH = CARD_WIDTH - 2 * CARD_PADDING
PASSWORD_MIN_CHARS = 8
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_EMAIL_KINDS = (AccountErrorKind.INVALID_EMAIL, AccountErrorKind.EMAIL_TOO_LONG)
_PASSWORD_KINDS = (
    AccountErrorKind.PASSWORD_TOO_SHORT,
    AccountErrorKind.PASSWORD_TOO_LONG,
)
_RESET_STEPS = ("auth.reset_step_1", "auth.reset_step_2", "auth.reset_step_3")


def is_valid_email(text: str) -> bool:
    return _EMAIL.fullmatch(text.strip()) is not None


def email_problem_key(text: str) -> str | None:
    """Catalog key of what is wrong with an email, or None when it can be sent."""
    email = text.strip()
    if len(email) > EMAIL_MAX_CHARS:
        return "auth.validation.email_too_long"
    if not is_valid_email(email):
        return "auth.validation.email_invalid"
    return None


def is_valid_name(text: str) -> bool:
    return 1 <= len(text.strip()) <= NAME_MAX_CHARS


class CardPage(QFrame):
    """One 440 px card (A.3.14)."""

    def __init__(self, tokens: ThemeTokens, language: Language) -> None:
        super().__init__()
        self.setObjectName("LoginCard")
        self.setFixedWidth(CARD_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self._tokens = tokens
        self._language = language
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(*(CARD_PADDING,) * 4)
        self.column.setSpacing(CARD_SPACING)

    def _t(self, key: str, **params: object) -> str:
        return tr(key, self._language, **params)

    def sizeHint(self) -> QSize:
        # Wrapped text needs less height at this width than at its default one.
        return QSize(CARD_WIDTH, height_at_width(self.column, CARD_WIDTH))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def hasHeightForWidth(self) -> bool:
        return False  # the size hint already is the height at the card's fixed width

    def _show_problem(self, block: FieldBlock, text: str) -> None:
        block.message.show_message(text)
        block.edit.setFocus()


class FormPage(CardPage):
    """A card with a primary button, a general message and the busy strip."""

    cancel_requested = Signal()

    def __init__(
        self,
        tokens: ThemeTokens,
        language: Language,
        idle_key: str,
        busy_key: str,
    ) -> None:
        super().__init__(tokens, language)
        self._idle_key = idle_key
        self._busy_key = busy_key
        self._blocks: list[FieldBlock] = []
        self.general_message = InlineMessage()
        self.strip = BusyStrip(tokens, language)
        self.strip.cancel_requested.connect(self.cancel_requested)
        self.primary = set_variant(QPushButton(self._t(idle_key)), "primary")
        self.busy = False

    def _add_status_and_primary(self) -> None:
        self.column.addWidget(self.general_message)
        self.column.addWidget(self.strip)
        self.column.addWidget(self.primary)

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        for block in self._blocks:
            block.set_blocked(busy)
        self.primary.setText(self._t(self._busy_key if busy else self._idle_key))
        self._refresh_primary()
        self._set_other_controls_enabled(not busy)
        if busy:
            self.strip.show_busy(waking=False)
        else:
            self.strip.hide_busy()

    def show_waking(self) -> None:
        self.strip.show_busy(waking=True)

    def _refresh_primary(self) -> None:
        self.primary.setEnabled(not self.busy)

    def _set_other_controls_enabled(self, enabled: bool) -> None:
        """Hook for the buttons that must not be pressed while a request runs."""

    def clear_messages(self) -> None:
        self.general_message.clear()
        for block in self._blocks:
            block.message.clear()

    def _clear_on_edit(self, block: FieldBlock) -> None:
        block.edit.textChanged.connect(lambda _text: block.message.clear())


class SignInPage(FormPage):
    submitted = Signal(str, str)  # email, password
    register_requested = Signal()
    reset_requested = Signal()
    google_requested = Signal()
    privacy_requested = Signal()

    def __init__(self, tokens: ThemeTokens, language: Language) -> None:
        super().__init__(tokens, language, "auth.sign_in_button", "auth.signing_in")
        title = text_label(self._t("auth.sign_in_title"), "title")
        intro = text_label(self._t("auth.sign_in_intro"), "muted")
        self.google_button = google_button(self._t("auth.google_sign_in"))
        divider = divider_with_text(self._t("auth.or_with_email"))
        self.email = email_block(self._t("auth.email_label"))
        self.password, self.password_field = password_block(
            self._t("auth.password_label"), language
        )
        self._blocks = [self.email, self.password]
        self.forgot_button = link_button(self._t("auth.forgot_link"))
        self.offline_note = text_label(self._t("auth.need_internet"), "note")
        self.offline_note.hide()
        self.success_message = InlineMessage(mark="✓")
        no_account = text_label(self._t("auth.no_account"), "muted")
        self.create_button = QPushButton(self._t("auth.create_account_link"))
        self.create_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        switch_row = QHBoxLayout()
        switch_row.setSpacing(12)
        switch_row.addWidget(no_account, stretch=1)
        switch_row.addWidget(self.create_button)
        self.privacy_button = link_button(self._t("auth.privacy_link"))

        for widget in (title, intro, self.google_button, divider):
            self.column.addWidget(widget)
        self.column.addWidget(self.email)
        self.column.addWidget(self.password)
        self.column.addWidget(self.forgot_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.column.addWidget(self.offline_note)
        self.column.addWidget(self.success_message)
        self._add_status_and_primary()
        self.column.addWidget(separator())
        self.column.addLayout(switch_row)
        self.column.addWidget(self.privacy_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self._connect()
        self._set_tab_order()

    def _connect(self) -> None:
        for block in self._blocks:
            self._clear_on_edit(block)
            block.edit.returnPressed.connect(self._submit)
        self.primary.clicked.connect(self._submit)
        self.forgot_button.clicked.connect(self.reset_requested)
        self.create_button.clicked.connect(self.register_requested)
        self.google_button.clicked.connect(self._request_google)
        self.privacy_button.clicked.connect(self.privacy_requested)

    def _request_google(self) -> None:
        if not self.busy:
            self.clear_messages()
            self.google_requested.emit()

    def _set_tab_order(self) -> None:
        chain = (
            self.google_button,
            self.email.edit,
            self.password.edit,
            self.password_field.toggle,
            self.forgot_button,
            self.primary,
            self.create_button,
            self.privacy_button,
        )
        chain_tab_order(chain)

    def focus_first(self) -> None:
        self.email.edit.setFocus()

    def set_online(self, online: bool) -> None:
        self.offline_note.setVisible(not online)

    def _set_other_controls_enabled(self, enabled: bool) -> None:
        self.forgot_button.setEnabled(enabled)
        self.create_button.setEnabled(enabled)
        self.google_button.setEnabled(enabled)
        self.privacy_button.setEnabled(enabled)

    def set_google_starting(self, starting: bool) -> None:
        """Blocked while the Google attempt is created; the primary text stays as is."""
        for block in self._blocks:
            block.set_blocked(starting)
        self.primary.setEnabled(not starting)
        self._set_other_controls_enabled(not starting)
        if starting:
            self.strip.show_busy(waking=False)
        else:
            self.strip.hide_busy()

    def _submit(self) -> None:
        if self.busy:
            return
        self.clear_messages()
        email = self.email.edit.text().strip()
        password = self.password.edit.text()
        email_problem = email_problem_key(email)
        if email_problem is not None:
            self._show_problem(self.email, self._t(email_problem))
        elif not password:
            problem = self._t(error_text_key(AccountErrorKind.INVALID_REQUEST))
            self._show_problem(self.password, problem)
        else:
            self.submitted.emit(email, password)

    def show_error(self, kind: AccountErrorKind) -> None:
        self.clear_messages()
        text = self._t(error_text_key(kind))
        if kind is AccountErrorKind.INVALID_CREDENTIALS:
            self._show_problem(self.password, text)
        elif kind in _EMAIL_KINDS:
            self._show_problem(self.email, text)
        else:
            self.general_message.show_message(text)
            self.email.edit.setFocus()

    def show_session_ended(self) -> None:
        self.clear_messages()
        self.general_message.show_message(
            self._t(error_text_key(AccountErrorKind.SESSION_REVOKED))
        )

    def show_account_deleted(self) -> None:
        self.clear_messages()
        self.success_message.show_message(self._t("account.deleted"))

    def clear_messages(self) -> None:
        super().clear_messages()
        self.success_message.clear()


class RegisterPage(FormPage):
    submitted = Signal(str, str, str)  # name, email, password
    back_requested = Signal()
    privacy_requested = Signal()

    def __init__(self, tokens: ThemeTokens, language: Language) -> None:
        super().__init__(tokens, language, "auth.register_button", "auth.creating")
        self.back_button = set_variant(QPushButton(self._t("nav.back")), "ghost")
        self.back_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        title = text_label(self._t("auth.register_title"), "title")
        self.name = FieldBlock(
            self._t("auth.name_label"), make_text_edit(NAME_MAX_CHARS)
        )
        self.email = email_block(self._t("auth.email_label"))
        self.password, self.password_field = password_block(
            self._t("auth.password_label"), language
        )
        self.confirm, self.confirm_field = password_block(
            self._t("auth.confirm_label"), language
        )
        # One "Show" button reveals both fields, so the two can be compared by eye.
        self.confirm_field.toggle.hide()
        self.password_field.toggle.toggled.connect(self._reveal_confirm)
        self._blocks = [self.name, self.email, self.password, self.confirm]
        self._confirm_typed = False
        self.consent = ConsentRow(self._t("auth.privacy_consent"), tokens.primary_fg)
        self.privacy_button = link_button(self._t("auth.privacy_link"))
        note = text_label(self._t("auth.verify_note"), "note")
        self._was_short = False

        self.column.addWidget(self.back_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.column.addWidget(title)
        for block in self._blocks:
            self.column.addWidget(block)
        self.column.addWidget(self.consent)
        self.column.addWidget(self.privacy_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self._add_status_and_primary()
        self.column.addWidget(note)
        self._connect()
        self._set_tab_order()
        self._refresh_primary()

    def _connect(self) -> None:
        for block in self._blocks:
            block.edit.returnPressed.connect(self._submit)
        self._clear_on_edit(self.name)
        self._clear_on_edit(self.email)
        self.password.edit.textChanged.connect(self._on_password_changed)
        self.confirm.edit.textChanged.connect(self._on_confirm_changed)
        self.consent.toggled.connect(self._refresh_primary)
        self.primary.clicked.connect(self._submit)
        self.back_button.clicked.connect(self.back_requested)
        self.privacy_button.clicked.connect(self.privacy_requested)

    def _set_tab_order(self) -> None:
        chain = (
            self.back_button,
            self.name.edit,
            self.email.edit,
            self.password.edit,
            self.password_field.toggle,
            self.confirm.edit,
            self.consent.check,
            self.privacy_button,
            self.primary,
        )
        chain_tab_order(chain)

    def focus_first(self) -> None:
        self.name.edit.setFocus()

    def _set_other_controls_enabled(self, enabled: bool) -> None:
        self.back_button.setEnabled(enabled)
        self.consent.check.setEnabled(enabled)
        self.privacy_button.setEnabled(enabled)

    def _reveal_confirm(self, shown: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
        self.confirm.edit.setEchoMode(mode)

    @property
    def passwords_differ(self) -> bool:
        return self.password.edit.text() != self.confirm.edit.text()

    def _refresh_primary(self) -> None:
        accepted = self.consent.check.isChecked()
        differ = self.passwords_differ
        self.primary.setEnabled(accepted and not differ and not self.busy)
        tip = ""
        if not self.busy:
            if not accepted:
                tip = self._t("auth.register_disabled_tip")
            elif differ:
                tip = self._t("auth.validation.password_mismatch")
        self.primary.setToolTip(tip)

    def _on_confirm_changed(self, _text: str) -> None:
        self._confirm_typed = True
        self._show_match_state()

    def _show_match_state(self) -> None:
        if self._confirm_typed and self.passwords_differ:
            self.confirm.message.show_message(
                self._t("auth.validation.password_mismatch"), urgent=False
            )
        else:
            self.confirm.message.clear()
        self._refresh_primary()

    def _on_password_changed(self, text: str) -> None:
        self._show_match_state()
        length = len(text)
        short = 0 < length < PASSWORD_MIN_CHARS
        message = self.password.message
        if length > PASSWORD_MAX_CHARS:
            message.show_message(
                self._t("auth.validation.password_too_long"), urgent=False
            )
        elif short:
            # Announced when the rule first applies, not on every key.
            message.show_message(
                self._t("auth.password_count", count=length),
                announce=not self._was_short,
                urgent=False,
            )
        else:
            message.clear()
        self._was_short = short

    def _submit(self) -> None:
        if self.busy or not self.consent.check.isChecked() or self.passwords_differ:
            return
        self.clear_messages()
        name = self.name.edit.text().strip()
        email = self.email.edit.text().strip()
        password = self.password.edit.text()
        problem = self._first_problem(name, email, password)
        if problem is None:
            self.submitted.emit(name, email, password)
            return
        block, text = problem
        self._show_problem(block, text)

    def _first_problem(
        self, name: str, email: str, password: str
    ) -> tuple[FieldBlock, str] | None:
        if len(name) > NAME_MAX_CHARS:
            return self.name, self._t("auth.validation.name_too_long")
        if not is_valid_name(name):
            return self.name, self._t("auth.validation.name_required")
        email_problem = email_problem_key(email)
        if email_problem is not None:
            return self.email, self._t(email_problem)
        if len(password) < PASSWORD_MIN_CHARS:
            key = error_text_key(AccountErrorKind.PASSWORD_TOO_SHORT)
            return self.password, self._t(key)
        if len(password) > PASSWORD_MAX_CHARS:
            return self.password, self._t("auth.validation.password_too_long")
        return None

    def show_error(self, kind: AccountErrorKind) -> None:
        self.clear_messages()
        text = self._t(error_text_key(kind))
        if kind is AccountErrorKind.EMAIL_EXISTS or kind in _EMAIL_KINDS:
            self._show_problem(self.email, text)
        elif kind in _PASSWORD_KINDS:
            self._show_problem(self.password, text)
        elif kind is AccountErrorKind.NAME_TOO_LONG:
            self._show_problem(self.name, text)
        else:
            self.general_message.show_message(text)
            self.name.edit.setFocus()


class GoogleWaitingPage(CardPage):
    """Shown while the person chooses a Google account in the browser (A.4.13)."""

    cancel_requested = Signal()

    def __init__(self, tokens: ThemeTokens, language: Language) -> None:
        super().__init__(tokens, language)
        title_text = self._t("google.waiting_title")
        title = text_label(title_text, "title")
        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setTextVisible(False)
        bar.setProperty("compact", True)
        bar.setAccessibleName(title_text)
        body = text_label(self._t("google.waiting_body"))
        self.cancel_button = set_variant(
            QPushButton(self._t("google.waiting_cancel")), "ghost"
        )
        self.cancel_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        for widget in (title, bar, body):
            self.column.addWidget(widget)
        self.column.addWidget(self.cancel_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.cancel_button.clicked.connect(self.cancel_requested)

    def focus_first(self) -> None:
        self.cancel_button.setFocus()


class ResetPage(CardPage):
    """Two steps in one card: ask for the email, then tell what to do next."""

    send_requested = Signal(str)  # email
    back_requested = Signal()  # to the sign-in card
    cancel_requested = Signal()

    def __init__(self, tokens: ThemeTokens, language: Language) -> None:
        super().__init__(tokens, language)
        self.busy = False
        self.back_button = set_variant(QPushButton(self._t("nav.back")), "ghost")
        self.back_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.strip = BusyStrip(tokens, language)
        self.strip.cancel_requested.connect(self.cancel_requested)
        self.steps = plain(CurrentPageStack())
        self.steps.addWidget(self._build_ask_step())
        self.steps.addWidget(self._build_done_step())
        self.column.addWidget(self.back_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.column.addWidget(self.steps)
        self.column.addWidget(self.strip)
        self._connect()
        self._set_tab_order()

    def _build_ask_step(self) -> QWidget:
        step = WrappingColumn(STEP_WIDTH, CARD_SPACING)
        column = step.column
        self.ask_label = text_label(
            self._t("auth.reset_step", current=1, total=2), "step"
        )
        heading = text_label(self._t("auth.reset_heading"), "title")
        intro = text_label(self._t("auth.reset_intro"), "muted")
        self.email = email_block(self._t("auth.email_label"))
        self.send_button = set_variant(
            QPushButton(self._t("auth.reset_send")), "primary"
        )
        for widget in (self.ask_label, heading, intro, self.email, self.send_button):
            column.addWidget(widget)
        return step

    def _build_done_step(self) -> QWidget:
        step = WrappingColumn(STEP_WIDTH, CARD_SPACING)
        column = step.column
        step_label = text_label(self._t("auth.reset_step", current=2, total=2), "step")
        disc = QLabel("✓")
        disc.setObjectName("DoneDisc")
        disc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disc.setFixedSize(32, 32)
        title = text_label(self._t("auth.reset_done_title"), "heading")
        disc.setAccessibleName(self._t("auth.reset_done_title"))
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title_row.addWidget(disc)
        title_row.addWidget(title, stretch=1)
        self.done_body = text_label("")
        self.done_message = InlineMessage()
        self.resend_button = QPushButton(self._t("auth.reset_resend"))
        self.signin_button = set_variant(
            QPushButton(self._t("auth.reset_back")), "primary"
        )
        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addWidget(self.resend_button)
        buttons.addWidget(self.signin_button)
        column.addWidget(step_label)
        column.addLayout(title_row)
        column.addWidget(self.done_body)
        for number, key in enumerate(_RESET_STEPS, start=1):
            column.addWidget(text_label(f"{number}. {self._t(key)}"))
        column.addWidget(text_label(self._t("auth.reset_spam"), "note"))
        column.addWidget(self.done_message)
        column.addLayout(buttons)
        return step

    def _connect(self) -> None:
        self.email.edit.textChanged.connect(lambda _text: self.email.message.clear())
        self.email.edit.returnPressed.connect(self._submit)
        self.send_button.clicked.connect(self._submit)
        self.resend_button.clicked.connect(self._resend)
        self.back_button.clicked.connect(self.back_requested)
        self.signin_button.clicked.connect(self.back_requested)

    def _set_tab_order(self) -> None:
        ask = (self.back_button, self.email.edit, self.send_button)
        done = (self.resend_button, self.signin_button)
        chain_tab_order(ask)
        chain_tab_order(done)

    @property
    def on_done_step(self) -> bool:
        return self.steps.currentIndex() == 1

    def restart(self, email: str) -> None:
        """Back to the first step; a typed email is kept."""
        self.steps.setCurrentIndex(0)
        self.back_button.show()
        self.done_message.clear()
        self.email.message.clear()
        if email and not self.email.edit.text():
            self.email.edit.setText(email)

    def focus_first(self) -> None:
        if self.on_done_step:
            self.resend_button.setFocus()
        else:
            self.email.edit.setFocus()

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.email.set_blocked(busy)
        for button in (self.send_button, self.resend_button, self.signin_button):
            button.setEnabled(not busy)
        self.back_button.setEnabled(not busy)
        self.send_button.setText(self._t("auth.sending" if busy else "auth.reset_send"))
        self.resend_button.setText(
            self._t("auth.sending" if busy else "auth.reset_resend")
        )
        if busy:
            self.strip.show_busy(waking=False)
        else:
            self.strip.hide_busy()

    def show_waking(self) -> None:
        self.strip.show_busy(waking=True)

    def show_done(self, email: str) -> None:
        self.done_body.setText(self._t("auth.reset_done_body", email=email))
        self.done_message.clear()
        self.steps.setCurrentIndex(1)
        self.back_button.hide()
        self.resend_button.setFocus()

    def show_error(self, kind: AccountErrorKind) -> None:
        text = self._t(error_text_key(kind))
        if self.on_done_step:
            self.done_message.show_message(text)
        else:
            self._show_problem(self.email, text)

    def _submit(self) -> None:
        if self.busy:
            return
        email = self.email.edit.text().strip()
        problem = email_problem_key(email)
        if problem is None:
            self.send_requested.emit(email)
        else:
            self._show_problem(self.email, self._t(problem))

    def _resend(self) -> None:
        if not self.busy:
            self.send_requested.emit(self.email.edit.text().strip())
