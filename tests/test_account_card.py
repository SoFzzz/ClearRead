"""Settings -> "Cuenta" card (A.4.12): identity, sync state, sign out and delete."""

import re

import pytest
from PySide6.QtWidgets import QAbstractButton, QLabel, QMessageBox
from pytestqt.qtbot import QtBot

from clearread.core.config import AppConfig
from clearread.services.account_client import AccountErrorKind
from clearread.services.syllabifier import SpanishSyllabifier
from clearread.ui.account_state import AccountInfo, SyncStatus
from clearread.ui.strings import Language, tr
from clearread.ui.theme import THEMES, ThemeId, build_stylesheet
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


def test_delete_explains_what_goes_and_cancel_is_the_safe_default(
    qtbot: QtBot,
) -> None:
    view = make_view(qtbot)
    assert view.account_card is not None
    requested: list[bool] = []
    view.delete_account_requested.connect(lambda: requested.append(True))
    view.account_card.delete_button.click()
    box = box_of(view)
    assert box.text() == tr("account.delete_title", Language.ES)
    assert box.informativeText() == tr("account.delete_body", Language.ES)
    default = box.defaultButton()
    assert isinstance(default, QAbstractButton)
    assert default.text() == tr("common.cancel", Language.ES)
    assert default.property("variant") == "primary"
    press(box, tr("common.cancel", Language.ES))
    assert requested == []
    view.account_card.delete_button.click()
    press(box_of(view), tr("account.delete_confirm", Language.ES))
    assert requested == [True]


def test_busy_state_blocks_both_buttons_and_says_deleting(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    card = view.account_card
    assert card is not None
    view.set_account_busy(True)
    assert not card.sign_out_button.isEnabled()
    assert not card.delete_button.isEnabled()
    assert tr("account.deleting", Language.ES) in labels(view)
    assert card.busy_label.isVisible()
    view.set_account_busy(False)
    assert card.sign_out_button.isEnabled()
    assert not card.busy_label.isVisible()


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
