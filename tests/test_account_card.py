"""Settings -> "Cuenta" card (A.4.12): identity, sync state, sign out and delete."""

import re

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractButton, QLabel, QLineEdit, QMessageBox
from pytestqt.qtbot import QtBot

from clearread.core.config import AppConfig
from clearread.services.account_client import AccountErrorKind
from clearread.services.syllabifier import SpanishSyllabifier
from clearread.ui.account_state import AccountBusy, AccountInfo, SyncStatus
from clearread.ui.strings import Language, tr
from clearread.ui.theme import THEMES, ThemeId, build_stylesheet
from clearread.ui.views.delete_account_dialog import DeleteAccountDialog
from clearread.ui.views.settings_view import SettingsView

SPANISH_CHARS = re.compile("[áéíóúñÁÉÍÓÚÑ¿¡]")
ANA = AccountInfo("Ana", "ana@example.com", True)


def make_view(
    qtbot: QtBot,
    language: Language = Language.ES,
    account: AccountInfo | None = ANA,
) -> SettingsView:
    view = SettingsView(AppConfig(), language, SpanishSyllabifier(), account)
    view.setStyleSheet(build_stylesheet(THEMES[ThemeId.LIGHT]))
    qtbot.addWidget(view)
    view.resize(1200, 800)
    view.show()
    return view


def labels(view: SettingsView) -> list[str]:
    assert view.account_card is not None
    return [label.text() for label in view.account_card.findChildren(QLabel)]


def box_of(view: SettingsView) -> QMessageBox:
    assert isinstance(view.dialog, QMessageBox)
    return view.dialog


def press(box: QMessageBox, text: str) -> None:
    next(b for b in box.buttons() if b.text() == text).click()


def test_no_card_without_an_account(qtbot: QtBot) -> None:
    view = make_view(qtbot, account=None)
    assert view.account_card is None
    view.set_sync_status(SyncStatus.OK)  # harmless
    view.set_online(False)


def test_the_card_comes_before_the_theme_section(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    assert view.account_card is not None
    card_top = view.account_card.mapTo(view, view.account_card.rect().topLeft()).y()
    theme = view.theme_buttons["light"]
    assert card_top < theme.mapTo(view, theme.rect().topLeft()).y()


@pytest.mark.parametrize("language", list(Language))
def test_identity_row(qtbot: QtBot, language: Language) -> None:
    view = make_view(qtbot, language)
    card = view.account_card
    assert card is not None
    assert card.name_label.full_text == "Ana"
    assert card.email_label.full_text == "ana@example.com"
    assert card.avatar.text() == "A"
    assert card.avatar.accessibleName() == tr(
        "account.avatar_a11y", language, name="Ana"
    )
    assert tr("account.verified", language) in card.badge.text()
    assert tr("account.title", language) in labels(view)


def test_unconfirmed_email_badge_uses_a_mark_and_text(qtbot: QtBot) -> None:
    view = make_view(qtbot, account=AccountInfo("Ana", "ana@example.com", False))
    assert view.account_card is not None
    assert view.account_card.badge.text() == (
        "! " + tr("account.not_verified", Language.ES)
    )


def test_badge_is_hidden_until_the_account_was_asked(qtbot: QtBot) -> None:
    view = make_view(qtbot, account=AccountInfo("Ana", "ana@example.com"))
    assert view.account_card is not None
    assert not view.account_card.badge.isVisible()
    view.set_account(ANA)
    assert view.account_card.badge.isVisible()


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize(
    ("status", "key"),
    [
        (SyncStatus.OK, "account.sync_ok"),
        (SyncStatus.PENDING, "account.sync_pending"),
        (SyncStatus.FAILED, "account.sync_failed"),
    ],
)
def test_sync_state_line(
    qtbot: QtBot, language: Language, status: SyncStatus, key: str
) -> None:
    view = make_view(qtbot, language)
    view.set_sync_status(status)
    assert tr(key, language) in labels(view)


def test_offline_note_follows_the_network(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    assert view.account_card is not None
    assert not view.account_card.offline_note.isVisible()
    view.set_online(False)
    assert view.account_card.offline_note.isVisible()
    view.set_online(True)
    assert not view.account_card.offline_note.isVisible()


def test_fixed_note_says_words_and_settings_are_in_the_account(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    assert tr("account.local_note", Language.ES) in labels(view)


def test_there_is_no_usage_meter(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    assert not [text for text in labels(view) if re.search(r"\d+ de \d+", text)]


def test_sign_out_asks_first_and_cancel_keeps_the_session(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    assert view.account_card is not None
    requested: list[bool] = []
    view.sign_out_requested.connect(lambda: requested.append(True))
    view.account_card.sign_out_button.click()
    box = box_of(view)
    assert box.text() == tr("account.sign_out_title", Language.ES)
    press(box, tr("common.cancel", Language.ES))
    assert requested == []
    view.account_card.sign_out_button.click()
    press(box_of(view), tr("account.sign_out", Language.ES))
    assert requested == [True]


def test_sign_out_warns_only_when_changes_are_unsaved(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    assert view.account_card is not None
    pending = tr("account.sign_out_pending", Language.ES)
    view.set_sync_status(SyncStatus.OK)
    view.account_card.sign_out_button.click()
    assert pending not in box_of(view).informativeText()
    box_of(view).close()
    for status in (SyncStatus.PENDING, SyncStatus.FAILED):
        view.set_sync_status(status)
        view.account_card.sign_out_button.click()
        assert pending in box_of(view).informativeText()
        box_of(view).close()


def open_delete_dialog(view: SettingsView) -> DeleteAccountDialog:
    assert view.account_card is not None
    view.account_card.delete_button.click()
    dialog = view.account_card.delete_dialog
    assert dialog is not None
    return dialog


@pytest.mark.parametrize("language", list(Language))
def test_delete_asks_for_the_password_and_cancel_is_the_safe_answer(
    qtbot: QtBot, language: Language
) -> None:
    view = make_view(qtbot, language)
    requested: list[str] = []
    view.delete_account_requested.connect(requested.append)
    dialog = open_delete_dialog(view)
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    for key in ("account.delete_title", "account.delete_body"):
        assert tr(key, language) in texts
    assert tr("account.delete_password_hint", language) in texts
    assert dialog.password_block.label.text() == tr(
        "account.delete_password_label", language
    )
    assert dialog.cancel_button.property("variant") == "primary"
    assert not dialog.cancel_button.autoDefault()
    assert not dialog.delete_button.autoDefault()
    dialog.cancel_button.click()
    assert requested == []
    assert view.account_card is not None
    assert view.account_card.delete_dialog is None


def test_the_password_field_is_hidden_limited_and_named(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    dialog = open_delete_dialog(view)
    edit = dialog.password_edit
    assert edit.echoMode() == QLineEdit.EchoMode.Password
    assert edit.maxLength() == 32
    assert edit.accessibleName() == tr("account.delete_password_label", Language.ES)
    toggle = dialog.password_field.toggle
    assert toggle.text() == tr("auth.show_password", Language.ES)
    toggle.click()
    assert edit.echoMode() == QLineEdit.EchoMode.Normal


def test_delete_stays_disabled_until_a_password_is_typed(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    requested: list[str] = []
    view.delete_account_requested.connect(requested.append)
    dialog = open_delete_dialog(view)
    assert not dialog.delete_button.isEnabled()
    dialog.delete_button.click()
    assert requested == []
    dialog.password_edit.setText("abc")
    assert dialog.delete_button.isEnabled()
    dialog.password_edit.clear()
    assert not dialog.delete_button.isEnabled()


def test_enter_never_deletes(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    requested: list[str] = []
    view.delete_account_requested.connect(requested.append)
    dialog = open_delete_dialog(view)
    dialog.password_edit.setText("abc")
    qtbot.keyClick(dialog.password_edit, Qt.Key.Key_Return)
    assert requested == []
    assert dialog.isVisible()


def test_confirming_sends_the_password_and_waits(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    requested: list[str] = []
    view.delete_account_requested.connect(requested.append)
    dialog = open_delete_dialog(view)
    dialog.password_edit.setText("my secret")
    dialog.delete_button.click()
    assert requested == ["my secret"]
    assert dialog.isVisible()
    assert dialog.busy_label.isVisible()
    assert not dialog.password_edit.isEnabled()
    assert not dialog.delete_button.isEnabled()
    assert dialog.password_edit.text() == ""
    dialog.reject()  # Escape while deleting does not hide the request
    assert dialog.isVisible()


@pytest.mark.parametrize("language", list(Language))
def test_a_wrong_password_is_said_inside_the_dialog(
    qtbot: QtBot, language: Language
) -> None:
    view = make_view(qtbot, language)
    dialog = open_delete_dialog(view)
    dialog.password_edit.setText("wrong")
    dialog.delete_button.click()
    view.show_wrong_delete_password()
    assert dialog.isVisible()
    assert dialog.wrong_password_text == tr("account.delete_wrong_password", language)
    assert dialog.password_edit.isEnabled()
    assert not dialog.busy_label.isVisible()
    assert dialog.cancel_button.isEnabled()


def test_another_error_closes_the_dialog_and_shows_it_in_the_card(
    qtbot: QtBot,
) -> None:
    view = make_view(qtbot)
    dialog = open_delete_dialog(view)
    dialog.password_edit.setText("abc")
    dialog.delete_button.click()
    view.show_account_error(AccountErrorKind.NO_NETWORK)
    assert view.account_card is not None
    assert not dialog.isVisible()
    assert view.account_card.delete_dialog is None
    assert view.account_card.error_message.isVisible()


def test_the_english_delete_dialog_has_no_spanish(qtbot: QtBot) -> None:
    view = make_view(qtbot, Language.EN)
    dialog = open_delete_dialog(view)
    view.show_wrong_delete_password()
    texts = [label.text() for label in dialog.findChildren(QLabel)] + [
        b.text() for b in dialog.findChildren(QAbstractButton)
    ]
    assert [text for text in texts if SPANISH_CHARS.search(text)] == []


def test_deleting_blocks_the_buttons_and_says_deleting(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    card = view.account_card
    assert card is not None
    view.set_account_busy(AccountBusy.DELETING)
    assert not card.sign_out_button.isEnabled()
    assert not card.delete_button.isEnabled()
    assert card.busy_label.isVisible()
    assert card.busy_label.text() == tr("account.deleting", Language.ES)
    view.set_account_busy(None)
    assert card.sign_out_button.isEnabled()
    assert not card.busy_label.isVisible()


@pytest.mark.parametrize("language", list(Language))
def test_signing_out_says_only_signing_out(qtbot: QtBot, language: Language) -> None:
    view = make_view(qtbot, language)
    card = view.account_card
    assert card is not None
    view.set_account_busy(AccountBusy.SIGNING_OUT)
    assert not card.sign_out_button.isEnabled()
    assert card.busy_label.isVisible()
    assert card.busy_label.text() == tr("account.signing_out", language)
    shown = [label.text() for label in card.findChildren(QLabel) if label.isVisible()]
    assert tr("account.deleting", language) not in shown


def test_the_busy_text_follows_the_latest_action(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    card = view.account_card
    assert card is not None
    view.set_account_busy(AccountBusy.DELETING)
    view.set_account_busy(None)
    view.set_account_busy(AccountBusy.SIGNING_OUT)
    assert card.busy_label.text() == tr("account.signing_out", Language.ES)


def test_the_card_offers_the_privacy_notice(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    card = view.account_card
    assert card is not None
    assert card.privacy_button.text() == tr("auth.privacy_link", Language.ES)
    card.privacy_button.click()
    dialog = card.privacy_dialog
    assert dialog is not None
    assert dialog.parent() is view.window()
    dialog.accept()


@pytest.mark.parametrize("language", list(Language))
def test_a_failed_delete_shows_its_error_inline(
    qtbot: QtBot, language: Language
) -> None:
    view = make_view(qtbot, language)
    card = view.account_card
    assert card is not None
    view.show_account_error(AccountErrorKind.NO_NETWORK)
    assert card.error_message.isVisible()
    assert card.error_message.text == tr("auth.error.no_network", language)


def test_english_card_has_no_spanish(qtbot: QtBot) -> None:
    view = make_view(qtbot, Language.EN)
    assert view.account_card is not None
    texts = labels(view) + [
        b.text() for b in view.account_card.findChildren(QAbstractButton)
    ]
    assert [text for text in texts if SPANISH_CHARS.search(text)] == []


def test_tab_visits_the_account_buttons_before_the_theme_options(
    qtbot: QtBot,
) -> None:
    view = make_view(qtbot)
    card = view.account_card
    assert card is not None
    order = [card.sign_out_button, card.delete_button, view.theme_buttons["light"]]
    widget = card.sign_out_button.nextInFocusChain()
    seen = [card.sign_out_button]
    while widget is not card.sign_out_button and len(seen) < len(order):
        if widget in order:
            seen.append(widget)
        widget = widget.nextInFocusChain()
    assert seen == order
