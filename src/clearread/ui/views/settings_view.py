"""Settings view (CFG-F01, CFG-F02, I18N-F01; design system 4.5 and 5.3)."""

from dataclasses import dataclass, replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from clearread.core.config import (
    FONT_SIZE_RANGE_PT,
    LETTER_SPACING_RANGE_EM,
    LINE_SPACING_RANGE,
    READING_FONTS,
    READING_SPEED_RANGE_WPM,
    UI_LANGUAGES,
    WORD_SPACING_RANGE_EM,
    AppConfig,
)
from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import (
    ReadingStyle,
    SyllablePalette,
    TextFormatter,
)
from clearread.services.tts_controller import VoiceInfo
from clearread.ui.strings import Language, tr
from clearread.ui.theme import THEMES, ThemeId, syllable_palette
from clearread.ui.views.reading_view import ReaderWidget

CACHE_FOLDER_LABEL = "%APPDATA%\\ClearRead\\cache"
CONTENT_WIDTH = 1120
PREVIEW_WIDTH = 420
PREVIEW_HEIGHT = 230
PREVIEW_MAX_HEIGHT = 360
PREVIEW_CARD_MARGIN = 20
PREVIEW_VIEW_MARGIN_X = 16
PREVIEW_VIEW_MARGIN_Y = 8
PREVIEW_TEXT_WIDTH = PREVIEW_WIDTH - 2 * (PREVIEW_CARD_MARGIN + PREVIEW_VIEW_MARGIN_X)
PREVIEW_WORD_INDEX = 5
SLIDER_WIDTH = 300
THEME_CARD_HEIGHT = 84
FONT_KEYS = {
    "Lexend": "settings.font.lexend",
    "Atkinson Hyperlegible": "settings.font.atkinson",
    "OpenDyslexic": "settings.font.opendyslexic",
}


@dataclass(frozen=True)
class SliderSpec:
    """A numeric setting shown as a slider; the slider works on integers."""

    field: str
    label_key: str
    low: float
    high: float
    steps_per_unit: int  # slider ticks per 1.0 of the setting
    value_key: str | None  # catalog key of the value label; None shows the number
    integer: bool


SLIDERS = (
    SliderSpec(
        "font_size_pt",
        "settings.font_size",
        FONT_SIZE_RANGE_PT[0],
        FONT_SIZE_RANGE_PT[1],
        1,
        "settings.value.points",
        True,
    ),
    SliderSpec(
        "line_spacing",
        "settings.line_spacing",
        LINE_SPACING_RANGE[0],
        LINE_SPACING_RANGE[1],
        10,
        None,
        False,
    ),
    SliderSpec(
        "letter_spacing_em",
        "settings.letter_spacing",
        LETTER_SPACING_RANGE_EM[0],
        LETTER_SPACING_RANGE_EM[1],
        100,
        "settings.value.em",
        False,
    ),
    SliderSpec(
        "word_spacing_em",
        "settings.word_spacing",
        WORD_SPACING_RANGE_EM[0],
        WORD_SPACING_RANGE_EM[1],
        100,
        "settings.value.em",
        False,
    ),
)
SPEED_SPEC = SliderSpec(
    "reading_speed_wpm",
    "settings.speed",
    READING_SPEED_RANGE_WPM[0],
    READING_SPEED_RANGE_WPM[1],
    1,
    "reading.speed_value",
    True,
)


def format_number(value: float, language: Language) -> str:
    text = f"{value:g}"
    return text.replace(".", ",") if language is Language.ES else text


class SettingsView(QWidget):
    """Every control applies at once: the view emits the new validated config."""

    config_changed = Signal(object)  # AppConfig
    clear_recents_requested = Signal()
    back_requested = Signal()

    def __init__(
        self,
        config: AppConfig,
        language: Language,
        syllabifier: SpanishSyllabifier,
    ) -> None:
        super().__init__()
        self._config = config
        self._language = language
        self._syllabifier = syllabifier
        self.dialog: QMessageBox | None = None
        self.sliders: dict[str, QSlider] = {}
        self._value_labels: dict[str, QLabel] = {}
        self._specs: dict[str, SliderSpec] = {}
        self._build_ui()
        self._sync_controls()
        escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(self.back_requested)

    @property
    def config(self) -> AppConfig:
        return replace(self._config)

    def _t(self, key: str, **params: object) -> str:
        return tr(key, self._language, **params)

    # ---- construction -------------------------------------------------

    def _build_ui(self) -> None:
        title = QLabel(self._t("settings.title"))
        title.setProperty("role", "title")
        hint = QLabel(self._t("settings.autosave_hint"))
        hint.setProperty("role", "muted")
        header = QHBoxLayout()
        header.addWidget(title)
        header.addWidget(hint, stretch=1, alignment=Qt.AlignmentFlag.AlignBottom)

        left = QVBoxLayout()
        left.setSpacing(12)
        left.addLayout(header)
        left.addWidget(self._heading("settings.section.theme"))
        left.addLayout(self._build_theme_cards())
        left.addWidget(self._heading("settings.section.text"))
        left.addLayout(self._build_font_row())
        font_note = QLabel(self._t("settings.font_note"))
        font_note.setProperty("role", "muted")
        font_note.setWordWrap(True)
        left.addWidget(font_note)
        for spec in SLIDERS:
            left.addLayout(self._slider_row(spec))
        left.addLayout(self._build_syllables_row())
        left.addWidget(self._heading("settings.section.voice"))
        left.addLayout(self._slider_row(SPEED_SPEC))
        left.addLayout(self._build_voice_row())
        left.addWidget(self._heading("settings.section.language"))
        left.addLayout(self._build_language_row())
        left.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(16)
        right.addWidget(self._build_preview_card())
        self.reset_button = QPushButton(self._t("settings.reset"))
        self.reset_button.clicked.connect(self.reset_to_defaults)
        right.addWidget(self.reset_button, alignment=Qt.AlignmentFlag.AlignLeft)
        right.addWidget(self._build_privacy_card())
        right.addStretch(1)

        body = QWidget()
        body.setFixedWidth(CONTENT_WIDTH)
        columns = QHBoxLayout(body)
        columns.setContentsMargins(0, 24, 0, 24)
        columns.setSpacing(40)
        columns.addLayout(left, stretch=1)
        columns.addLayout(right)
        columns.setStretch(1, 0)

        centered = QWidget()
        row = QHBoxLayout(centered)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(body)
        row.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(centered)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _heading(self, key: str) -> QLabel:
        label = QLabel(self._t(key))
        label.setProperty("role", "heading")
        return label

    def _build_theme_cards(self) -> QHBoxLayout:
        self.theme_buttons: dict[str, QRadioButton] = {}
        self._theme_cards: dict[str, QFrame] = {}
        group = QButtonGroup(self)
        row = QHBoxLayout()
        row.setSpacing(16)
        for theme in ThemeId:
            card = QFrame()
            card.setObjectName("ThemeCard")
            card.setFixedHeight(THEME_CARD_HEIGHT)
            tokens = THEMES[theme]
            swatch = QLabel("Aa")
            swatch.setFixedSize(52, 52)
            swatch.setAlignment(Qt.AlignmentFlag.AlignCenter)
            swatch.setStyleSheet(
                f"background: {tokens.bg}; color: {tokens.text}; font-weight: 700; "
                f"border: 1px solid {tokens.border}; border-radius: 8px;"
            )
            button = QRadioButton(self._t(f"settings.theme.{theme.value}"))
            button.toggled.connect(
                lambda checked, value=theme.value: self._on_theme_toggled(
                    checked, value
                )
            )
            group.addButton(button)
            layout = QHBoxLayout(card)
            layout.setContentsMargins(16, 0, 16, 0)
            layout.addWidget(button)
            layout.addWidget(swatch)
            row.addWidget(card, stretch=1)
            self.theme_buttons[theme.value] = button
            self._theme_cards[theme.value] = card
        return row

    def _slider_row(self, spec: SliderSpec) -> QHBoxLayout:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(
            round(spec.low * spec.steps_per_unit),
            round(spec.high * spec.steps_per_unit),
        )
        slider.setFixedWidth(SLIDER_WIDTH)
        slider.valueChanged.connect(
            lambda raw, current=spec: self._on_slider(current, raw)
        )
        value = QLabel()
        value.setMinimumWidth(130)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.sliders[spec.field] = slider
        self._value_labels[spec.field] = value
        self._specs[spec.field] = spec
        row = QHBoxLayout()
        row.addWidget(QLabel(self._t(spec.label_key)), stretch=1)
        row.addWidget(slider)
        row.addWidget(value)
        return row

    def _build_syllables_row(self) -> QHBoxLayout:
        self.syllables_check = QCheckBox()
        self.syllables_check.setAccessibleName(self._t("settings.syllables"))
        self.syllables_check.toggled.connect(self._on_syllables)
        row = QHBoxLayout()
        row.addWidget(QLabel(self._t("settings.syllables")), stretch=1)
        row.addWidget(self.syllables_check)
        return row

    def _build_voice_row(self) -> QHBoxLayout:
        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumWidth(SLIDER_WIDTH + 130)
        self.voice_combo.addItem(self._t("settings.no_voices"), "")
        self.voice_combo.setEnabled(False)
        self.voice_combo.currentIndexChanged.connect(self._on_voice)
        row = QHBoxLayout()
        row.addWidget(QLabel(self._t("settings.voice")), stretch=1)
        row.addWidget(self.voice_combo)
        return row

    def _build_font_row(self) -> QHBoxLayout:
        self.font_combo = QComboBox()
        self.font_combo.setMinimumWidth(SLIDER_WIDTH + 130)
        for family in READING_FONTS:
            self.font_combo.addItem(self._t(FONT_KEYS[family]), family)
        self.font_combo.currentIndexChanged.connect(self._on_font)
        row = QHBoxLayout()
        row.addWidget(QLabel(self._t("settings.font")), stretch=1)
        row.addWidget(self.font_combo)
        return row

    def _build_language_row(self) -> QHBoxLayout:
        self.language_combo = QComboBox()
        self.language_combo.setMinimumWidth(SLIDER_WIDTH + 130)
        for code in UI_LANGUAGES:
            self.language_combo.addItem(self._t(f"settings.language.{code}"), code)
        self.language_combo.currentIndexChanged.connect(self._on_language)
        row = QHBoxLayout()
        row.addWidget(QLabel(self._t("settings.language.label")), stretch=1)
        row.addWidget(self.language_combo)
        return row

    def _build_preview_card(self) -> QFrame:
        self.preview = ReaderWidget(THEMES[ThemeId(self._config.theme)])
        self.preview.setViewportMargins(
            PREVIEW_VIEW_MARGIN_X,
            PREVIEW_VIEW_MARGIN_Y,
            PREVIEW_VIEW_MARGIN_X,
            PREVIEW_VIEW_MARGIN_Y,
        )
        self.preview.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview.setFixedHeight(PREVIEW_HEIGHT)
        self.preview.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        caption = QLabel(self._t("settings.preview_caption"))
        caption.setProperty("role", "muted")
        caption.setWordWrap(True)
        card = QFrame()
        card.setObjectName("PreviewCard")
        card.setFixedWidth(PREVIEW_WIDTH)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(PREVIEW_CARD_MARGIN, 16, PREVIEW_CARD_MARGIN, 16)
        layout.addWidget(self._heading("settings.preview_title"))
        layout.addWidget(self.preview)
        layout.addWidget(caption)
        return card

    def _build_privacy_card(self) -> QFrame:
        assistant = QLabel(self._t("settings.privacy.assistant"))
        cache = QLabel(self._t("settings.privacy.cache", path=CACHE_FOLDER_LABEL))
        for label in (assistant, cache):
            label.setWordWrap(True)
            label.setProperty("role", "muted")
        self.clear_button = QPushButton(self._t("settings.clear_recents"))
        self.clear_button.clicked.connect(self._confirm_clear_recents)
        self.clear_status_label = QLabel()
        self.clear_status_label.setWordWrap(True)
        self.save_error_label = QLabel(self._t("settings.save_failed"))
        self.save_error_label.setProperty("role", "error")
        self.save_error_label.setWordWrap(True)
        self.save_error_label.hide()
        card = QFrame()
        card.setObjectName("PreviewCard")
        card.setFixedWidth(PREVIEW_WIDTH)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        layout.addWidget(self._heading("settings.privacy.title"))
        layout.addWidget(assistant)
        layout.addWidget(cache)
        layout.addWidget(self.clear_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.clear_status_label)
        layout.addWidget(self.save_error_label)
        return card

    # ---- state <-> controls -------------------------------------------

    def set_config(self, config: AppConfig) -> None:
        """Show ``config`` without emitting changes (the caller already applied it)."""
        self._config = config
        self._sync_controls()

    def set_speed(self, wpm: int) -> None:
        self._config.reading_speed_wpm = wpm
        self._sync_controls()

    def set_voices(self, voices: list[VoiceInfo]) -> None:
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        for voice in voices:
            self.voice_combo.addItem(voice.name, voice.id)
        if not voices:
            self.voice_combo.addItem(self._t("settings.no_voices"), "")
        self.voice_combo.setEnabled(bool(voices))
        index = self.voice_combo.findData(self._config.voice_id)
        self.voice_combo.setCurrentIndex(max(index, 0))
        self.voice_combo.blockSignals(False)

    def show_save_error(self, failed: bool) -> None:
        self.save_error_label.setVisible(failed)

    def show_recents_cleared(self) -> None:
        self.clear_status_label.setText(self._t("settings.recents_cleared"))

    def _sync_controls(self) -> None:
        config = self._config
        for field, slider in self.sliders.items():
            spec = self._specs[field]
            slider.blockSignals(True)
            slider.setValue(round(getattr(config, field) * spec.steps_per_unit))
            slider.blockSignals(False)
            self._show_value(spec, getattr(config, field))
        self.theme_buttons[config.theme].blockSignals(True)
        self.theme_buttons[config.theme].setChecked(True)
        self.theme_buttons[config.theme].blockSignals(False)
        self._mark_selected_card(config.theme)
        self.syllables_check.blockSignals(True)
        self.syllables_check.setChecked(config.syllables_enabled)
        self.syllables_check.blockSignals(False)
        self._show_syllables_text(config.syllables_enabled)
        self.language_combo.blockSignals(True)
        self.language_combo.setCurrentIndex(
            max(self.language_combo.findData(config.ui_language), 0)
        )
        self.language_combo.blockSignals(False)
        index = self.voice_combo.findData(config.voice_id)
        self.voice_combo.blockSignals(True)
        self.voice_combo.setCurrentIndex(max(index, 0))
        self.voice_combo.blockSignals(False)
        self.font_combo.blockSignals(True)
        self.font_combo.setCurrentIndex(
            max(self.font_combo.findData(config.reading_font), 0)
        )
        self.font_combo.blockSignals(False)
        self._refresh_preview()

    def _show_value(self, spec: SliderSpec, value: float) -> None:
        number = format_number(value, self._language)
        text = (
            number
            if spec.value_key is None
            else self._t(spec.value_key, **{self._value_param(spec): number})
        )
        self._value_labels[spec.field].setText(text)

    @staticmethod
    def _value_param(spec: SliderSpec) -> str:
        return "wpm" if spec.value_key == "reading.speed_value" else "value"

    def _show_syllables_text(self, enabled: bool) -> None:
        self.syllables_check.setText(
            self._t("settings.on" if enabled else "settings.off")
        )

    def _mark_selected_card(self, theme: str) -> None:
        for value, card in self._theme_cards.items():
            card.setProperty("selected", value == theme)
            card.style().unpolish(card)
            card.style().polish(card)

    def _refresh_preview(self) -> None:
        config = self._config
        tokens = THEMES[ThemeId(config.theme)]
        style = ReadingStyle(
            font_family=config.reading_font,
            font_size_pt=config.font_size_pt,
            letter_spacing_em=config.letter_spacing_em,
            word_spacing_em=config.word_spacing_em,
        )
        palette: SyllablePalette = syllable_palette(tokens)
        formatter = TextFormatter(self._syllabifier, palette, style)
        document = formatter.format_document(
            self._t("settings.preview_sample"), config.syllables_enabled
        )
        self.preview.apply_theme(tokens)
        self.preview.set_reading_font(QFont(style.font_family, style.font_size_pt))
        self.preview.set_line_spacing(config.line_spacing)
        self.preview.set_content(document.html_content)
        self.preview.fit_height(PREVIEW_TEXT_WIDTH, PREVIEW_HEIGHT, PREVIEW_MAX_HEIGHT)
        self.preview.highlight_token(document.token_map[PREVIEW_WORD_INDEX])

    # ---- user actions -------------------------------------------------

    def _commit(self) -> None:
        self._config = self._config.validated(self._config)
        self._sync_controls()
        self.config_changed.emit(replace(self._config))

    def _on_slider(self, spec: SliderSpec, raw: int) -> None:
        value = raw / spec.steps_per_unit
        setattr(self._config, spec.field, round(value) if spec.integer else value)
        self._commit()

    def _on_theme_toggled(self, checked: bool, theme: str) -> None:
        if checked and theme != self._config.theme:
            self._config.theme = theme
            self._commit()

    def _on_syllables(self, enabled: bool) -> None:
        self._config.syllables_enabled = enabled
        self._commit()

    def _on_font(self, index: int) -> None:
        family = self.font_combo.itemData(index)
        if family and family != self._config.reading_font:
            self._config.reading_font = family
            self._commit()

    def _on_voice(self, index: int) -> None:
        voice_id = self.voice_combo.itemData(index)
        if voice_id and voice_id != self._config.voice_id:
            self._config.voice_id = voice_id
            self._commit()

    def _on_language(self, index: int) -> None:
        code = self.language_combo.itemData(index)
        if code == self._config.ui_language:
            return
        self._config.ui_language = code
        self._commit()
        self._notify_restart(Language(code))

    def _notify_restart(self, new_language: Language) -> None:
        box = QMessageBox(
            QMessageBox.Icon.Information,
            tr("settings.language.restart_title", new_language),
            tr("settings.language.restart_message", new_language),
            parent=self,
        )
        box.addButton(
            tr("common.understood", new_language), QMessageBox.ButtonRole.AcceptRole
        )
        self._show_dialog(box)

    def reset_to_defaults(self) -> None:
        """Back to the default look and speed; voice and language stay."""
        defaults = AppConfig()
        for field in (
            "theme",
            "reading_font",
            "font_size_pt",
            "line_spacing",
            "letter_spacing_em",
            "word_spacing_em",
            "syllables_enabled",
            "reading_speed_wpm",
        ):
            setattr(self._config, field, getattr(defaults, field))
        self._commit()

    def _confirm_clear_recents(self) -> None:
        box = QMessageBox(
            QMessageBox.Icon.Question,
            self._t("settings.clear_confirm.title"),
            self._t("settings.clear_confirm.message"),
            parent=self,
        )
        yes = box.addButton(
            self._t("settings.clear_confirm.yes"), QMessageBox.ButtonRole.AcceptRole
        )
        cancel = box.addButton(
            self._t("common.cancel"), QMessageBox.ButtonRole.RejectRole
        )
        box.setDefaultButton(cancel)
        box.buttonClicked.connect(
            lambda clicked: self._on_clear_answered(clicked is yes)
        )
        self._show_dialog(box)

    def _on_clear_answered(self, confirmed: bool) -> None:
        if confirmed:
            self.clear_recents_requested.emit()

    def _show_dialog(self, box: QMessageBox) -> None:
        self.dialog = box
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.finished.connect(lambda: self._forget_dialog(box))
        box.open()

    def _forget_dialog(self, box: QMessageBox) -> None:
        if self.dialog is box:
            self.dialog = None
