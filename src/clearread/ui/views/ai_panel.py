"""Side panel of the assistant (design system 4.4): one page per state, no logic of its own."""

from enum import Enum

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAccessible, QAccessibleEvent, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from clearread.services.ai_client import AIErrorKind
from clearread.ui.fonts import READING_FONT_FAMILY
from clearread.ui.icons import load_icon
from clearread.ui.strings import CATALOG, Language, tr
from clearread.ui.theme import ThemeTokens

PANEL_WIDTH = 360
PANEL_PADDING = 20
PANEL_SPACING = 16
ANSWER_FONT_PX = 17
MARK_SIZE = 40
_NO_RETRY = (
    AIErrorKind.SESSION_LIMIT,
    AIErrorKind.DAILY_LIMIT,
    AIErrorKind.INPUT_TOO_LONG,
)


class PanelState(Enum):
    EMPTY = "empty"
    PRIVACY = "privacy"
    LOADING = "loading"
    WAKING = "waking"
    ANSWER = "answer"
    ERROR = "error"
    OFFLINE = "offline"


class AIMode(Enum):
    EXPLAIN = "explain"
    SIMPLIFY = "simplify"


def can_retry(kind: AIErrorKind) -> bool:
    return kind not in _NO_RETRY


def _label(text: str = "", wrap: bool = True, role: str | None = None) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(wrap)
    if role:
        label.setProperty("role", role)
    return label


def _card(object_name: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName(object_name)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(
        PANEL_SPACING, PANEL_SPACING, PANEL_SPACING, PANEL_SPACING
    )
    layout.setSpacing(12)
    return card, layout


class AIPanel(QFrame):
    explain_clicked = Signal()
    simplify_clicked = Signal()
    cancel_clicked = Signal()
    retry_clicked = Signal()
    privacy_accepted = Signal()
    privacy_declined = Signal()
    listen_clicked = Signal()
    close_clicked = Signal()

    def __init__(self, tokens: ThemeTokens, language: Language = Language.ES) -> None:
        super().__init__()
        self._tokens = tokens
        self._language = language
        self._online = True
        self._listening = False
        self._mode: AIMode | None = None
        self.state = PanelState.EMPTY
        self.setObjectName("AIPanel")
        self.setFixedWidth(PANEL_WIDTH)
        self._build_ui()
        self._pages = {
            PanelState.EMPTY: self._empty_page,
            PanelState.PRIVACY: self._privacy_page,
            PanelState.LOADING: self._loading_page,
            PanelState.WAKING: self._loading_page,
            PanelState.ANSWER: self._answer_page,
            PanelState.ERROR: self._error_page,
            PanelState.OFFLINE: self._offline_page,
        }
        self._refresh_texts()
        self._set_state(PanelState.EMPTY)

    def _t(self, key: str, **params: object) -> str:
        return tr(key, self._language, **params)

    def _build_ui(self) -> None:
        self.title_label = _label(role="heading", wrap=False)
        self.close_button = QPushButton()
        self.close_button.setProperty("variant", "ghost")
        self.close_button.clicked.connect(self.close_clicked)
        header = QHBoxLayout()
        header.addWidget(self.title_label, stretch=1)
        header.addWidget(self.close_button)

        self.chosen_caption = _label(role="muted", wrap=False)
        self.chip = QLabel()
        self.chip.setObjectName("WordChip")
        self.chip.setMaximumWidth(PANEL_WIDTH - 2 * PANEL_PADDING)
        self.chosen_box = QWidget()
        self.chosen_box.setObjectName("AIPage")
        chosen = QVBoxLayout(self.chosen_box)
        chosen.setContentsMargins(0, 0, 0, 0)
        chosen.setSpacing(4)
        chosen.addWidget(self.chosen_caption)
        chosen.addWidget(self.chip, alignment=Qt.AlignmentFlag.AlignLeft)
        self.chosen_box.hide()

        self.explain_button = QPushButton()
        self.simplify_button = QPushButton()
        self.explain_button.clicked.connect(self.explain_clicked)
        self.simplify_button.clicked.connect(self.simplify_clicked)
        modes = QHBoxLayout()
        modes.setSpacing(8)
        modes.addWidget(self.explain_button)
        modes.addWidget(self.simplify_button)

        self._stack = QStackedWidget()
        self._stack.setObjectName("AIPage")
        self._build_pages()

        self.privacy_note = _label(role="muted")
        self.counter_label = _label(role="muted")
        lock = QLabel()
        self._lock_icon = lock
        note = QHBoxLayout()
        note.setSpacing(8)
        note.addWidget(lock, alignment=Qt.AlignmentFlag.AlignTop)
        note.addWidget(self.privacy_note, stretch=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            PANEL_PADDING, PANEL_PADDING, PANEL_PADDING, PANEL_PADDING
        )
        layout.setSpacing(PANEL_SPACING)
        layout.addLayout(header)
        layout.addWidget(self.chosen_box)
        layout.addLayout(modes)
        layout.addWidget(self._stack, stretch=1)
        layout.addLayout(note)
        layout.addWidget(self.counter_label)

    def _build_pages(self) -> None:
        self._empty_page, empty = self._page()
        self.empty_title = _label(role="heading")
        self.empty_body = _label()
        self.empty_shortcut = _label(role="muted")
        for widget in (self.empty_title, self.empty_body, self.empty_shortcut):
            empty.addWidget(widget)
        empty.addStretch(1)

        self._privacy_page, privacy = self._page()
        card, card_layout = _card("PrivacyCard")
        self.privacy_icon = QLabel()
        self.privacy_title = _label(role="heading")
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addWidget(self.privacy_icon)
        title_row.addWidget(self.privacy_title, stretch=1)
        self.privacy_body = _label()
        self.privacy_destination = _label()
        self.decline_button = QPushButton()
        self.accept_button = QPushButton()
        self.accept_button.setProperty("variant", "primary")
        self.accept_button.setDefault(True)
        self.decline_button.clicked.connect(self.privacy_declined)
        self.accept_button.clicked.connect(self.privacy_accepted)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.decline_button)
        buttons.addWidget(self.accept_button)
        card_layout.addLayout(title_row)
        card_layout.addWidget(self.privacy_body)
        card_layout.addWidget(self.privacy_destination)
        card_layout.addLayout(buttons)
        privacy.addWidget(card)
        privacy.addStretch(1)

        self._loading_page, loading = self._page()
        card, card_layout = _card("AICard")
        self.status_icon = QLabel()
        self.status_title = _label(role="heading")
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_row.addWidget(self.status_icon)
        status_row.addWidget(self.status_title, stretch=1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.status_detail = _label(role="muted")
        card_layout.addLayout(status_row)
        card_layout.addWidget(self.progress)
        card_layout.addWidget(self.status_detail)
        self.cancel_button = QPushButton()
        self.cancel_button.clicked.connect(self.cancel_clicked)
        loading.addWidget(card)
        loading.addStretch(1)
        loading.addWidget(self.cancel_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self._answer_page, answer = self._page()
        card, card_layout = _card("AICard")
        self.answer_title = _label(role="heading")
        self.answer_title.setStyleSheet("font-size: 15px;")
        self.answer_body = _label()
        self.answer_body.setObjectName("AnswerBody")
        self.answer_body.setFont(QFont(READING_FONT_FAMILY))
        self.answer_body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.answer_footer = _label(role="muted")
        card_layout.addWidget(self.answer_title)
        card_layout.addWidget(self.answer_body)
        card_layout.addWidget(self.answer_footer)
        self.listen_button = QPushButton()
        self.listen_button.clicked.connect(self.listen_clicked)
        answer.addWidget(card)
        answer.addWidget(self.listen_button, alignment=Qt.AlignmentFlag.AlignLeft)
        answer.addStretch(1)

        self._error_page, error = self._page()
        card, card_layout = _card("AICard")
        self.error_mark = QLabel("!")
        self.error_mark.setObjectName("ErrorMark")
        self.error_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_mark.setFixedSize(MARK_SIZE, MARK_SIZE)
        self.error_message = _label(role="heading")
        self.error_message.setStyleSheet("font-size: 15px;")
        error_row = QHBoxLayout()
        error_row.setSpacing(12)
        error_row.addWidget(self.error_mark, alignment=Qt.AlignmentFlag.AlignTop)
        error_row.addWidget(self.error_message, stretch=1)
        self.error_hint = _label()
        self.retry_button = QPushButton()
        self.retry_button.clicked.connect(self.retry_clicked)
        card_layout.addLayout(error_row)
        card_layout.addWidget(self.error_hint)
        card_layout.addWidget(self.retry_button, alignment=Qt.AlignmentFlag.AlignLeft)
        error.addWidget(card)
        error.addStretch(1)

        self._offline_page, offline = self._page()
        card, card_layout = _card("AICard")
        self.offline_icon = QLabel()
        self.offline_title = _label(role="heading")
        offline_row = QHBoxLayout()
        offline_row.setSpacing(8)
        offline_row.addWidget(self.offline_icon)
        offline_row.addWidget(self.offline_title, stretch=1)
        self.offline_body = _label()
        card_layout.addLayout(offline_row)
        card_layout.addWidget(self.offline_body)
        offline.addWidget(card)
        offline.addStretch(1)

    def _page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("AIPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(PANEL_SPACING)
        self._stack.addWidget(page)
        return page, layout

    def _refresh_texts(self) -> None:
        self.title_label.setText(self._t("nav.assistant"))
        self.close_button.setToolTip(self._t("ai.close"))
        self.close_button.setAccessibleName(self._t("ai.close"))
        self.chosen_caption.setText(self._t("ai.chosen"))
        self.explain_button.setText(self._t("ai.explain_word"))
        self.simplify_button.setText(self._t("ai.simplify_paragraph"))
        self.empty_title.setText(self._t("ai.empty.title"))
        self.empty_body.setText(self._t("ai.empty.body"))
        self.empty_shortcut.setText(self._t("ai.empty.shortcut"))
        self.privacy_title.setText(self._t("privacy.title"))
        self.privacy_body.setText(self._t("privacy.body"))
        self.privacy_destination.setText(self._t("privacy.destination"))
        self.decline_button.setText(self._t("common.not_now"))
        self.accept_button.setText(self._t("common.understood"))
        self.cancel_button.setText(self._t("common.cancel"))
        self.answer_footer.setText(self._t("ai.answer_footer"))
        self.retry_button.setText(self._t("common.retry"))
        self.offline_title.setText(self._t("ai.offline_title"))
        self.offline_body.setText(self._t("ai.offline_tooltip"))
        self.privacy_note.setText(self._t("privacy.footer"))
        self._refresh_listen()
        self.apply_theme(self._tokens)

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self.close_button.setIcon(load_icon("close", tokens.secondary))
        self._lock_icon.setPixmap(load_icon("lock", tokens.text_muted).pixmap(16, 16))
        self.privacy_icon.setPixmap(load_icon("lock", tokens.text).pixmap(20, 20))
        self.status_icon.setPixmap(load_icon("clock", tokens.text).pixmap(20, 20))
        self.offline_icon.setPixmap(load_icon("wifi-off", tokens.text).pixmap(20, 20))
        self.retry_button.setIcon(load_icon("retry", tokens.secondary))
        self._refresh_listen()

    def _refresh_listen(self) -> None:
        key = "ai.listen_stop" if self._listening else "ai.listen"
        icon = "stop" if self._listening else "speaker"
        self.listen_button.setText(self._t(key))
        self.listen_button.setIcon(load_icon(icon, self._tokens.secondary))

    def _set_state(self, state: PanelState) -> None:
        self.state = state
        self._stack.setCurrentWidget(self._pages[state])
        busy = state in (PanelState.LOADING, PanelState.WAKING)
        usable = self._online and not busy and state is not PanelState.PRIVACY
        self.explain_button.setEnabled(usable)
        self.simplify_button.setEnabled(usable)
        self._refresh_mode_buttons()

    def _refresh_mode_buttons(self) -> None:
        for button, mode in (
            (self.explain_button, AIMode.EXPLAIN),
            (self.simplify_button, AIMode.SIMPLIFY),
        ):
            primary = self._mode is mode and self.state is not PanelState.EMPTY
            button.setProperty("variant", "primary" if primary else "")
            button.style().unpolish(button)
            button.style().polish(button)

    def set_chosen(self, text: str, mode: AIMode | None) -> None:
        self._mode = mode
        self.chip.setText(text)
        self.chip.setAccessibleName(text)
        self.chosen_box.setVisible(bool(text))
        self._refresh_mode_buttons()

    def set_counter(self, used: int, limit: int) -> None:
        self.counter_label.setVisible(limit > 0)
        self.counter_label.setText(
            self._t("ai.session_counter", used=used, limit=limit)
        )

    def set_online(self, online: bool) -> None:
        self._online = online
        if not online and self.state in (PanelState.EMPTY, PanelState.ANSWER):
            self.show_offline()
        elif online and self.state is PanelState.OFFLINE:
            self.show_empty()
        else:
            self._set_state(self.state)

    def set_listening(self, listening: bool) -> None:
        self._listening = listening
        self._refresh_listen()

    def show_empty(self) -> None:
        self._set_state(PanelState.EMPTY if self._online else PanelState.OFFLINE)

    def show_offline(self) -> None:
        self._set_state(PanelState.OFFLINE)

    def show_privacy(self) -> None:
        self._set_state(PanelState.PRIVACY)
        self.accept_button.setFocus()

    def show_loading(self) -> None:
        self.status_icon.hide()
        self.status_title.setText(self._t("ai.loading"))
        self.status_detail.setText(self._t("ai.loading_hint"))
        self._set_state(PanelState.LOADING)

    def show_waking(self) -> None:
        self.status_icon.show()
        self.status_title.setText(self._t("ai.waking.title"))
        self.status_detail.setText(self._t("ai.waking.detail"))
        self._set_state(PanelState.WAKING)

    def show_answer(self, text: str, mode: AIMode) -> None:
        key = (
            "ai.answer_title_word"
            if mode is AIMode.EXPLAIN
            else "ai.answer_title_paragraph"
        )
        self.answer_title.setText(self._t(key))
        self.answer_body.setText(text)
        self.set_listening(False)
        self._set_state(PanelState.ANSWER)
        self.answer_body.setAccessibleName(text)
        QAccessible.updateAccessibility(
            QAccessibleEvent(self.answer_body, QAccessible.Event.NameChanged)
        )

    def show_error(self, kind: AIErrorKind) -> None:
        self.error_message.setText(self._t(f"ai.error.{kind.name.lower()}"))
        hint_key = f"ai.hint.{kind.name.lower()}"
        hint = self._t(hint_key) if hint_key in CATALOG else ""
        self.error_hint.setText(hint)
        self.error_hint.setVisible(bool(hint))
        self.retry_button.setVisible(can_retry(kind))
        self._set_state(PanelState.ERROR)
        if can_retry(kind):
            self.retry_button.setFocus()
