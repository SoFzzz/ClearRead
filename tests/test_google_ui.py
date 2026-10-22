"""Google in the screens: login button and waiting card, Settings card, controller wiring."""

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from app_fakes import GOOGLE_TEST_POLL_MS, Rig, make_rig, save_session
from backend_fakes import session_json
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QProgressBar, QPushButton
from pytestqt.qtbot import QtBot

from clearread.core.config import AppConfig
from clearread.services.account_client import AccountErrorKind
from clearread.services.syllabifier import SpanishSyllabifier
from clearread.ui.account_state import AccountInfo
from clearread.ui.app_controller import AppController
from clearread.ui.fonts import load_reading_font
from clearread.ui.google_flow import GoogleFlow
from clearread.ui.strings import Language, tr
from clearread.ui.theme import THEMES, ThemeId, build_stylesheet
from clearread.ui.views.login_view import LoginPage, LoginView
from clearread.ui.views.login_widgets import InlineMessage
from clearread.ui.views.settings_view import SettingsView

TIMEOUT_MS = 8000
SIGNED_IN = (200, {"status": "signed_in", "session": session_json(google_linked=True)})
LINKED = (200, {"status": "linked"})


@pytest.fixture
def rig(tmp_path: Path) -> Iterator[Rig]:
    rig = make_rig(tmp_path)
    yield rig
    rig.pool.waitForDone(TIMEOUT_MS)


@pytest.fixture
def controllers(qtbot: QtBot, rig: Rig) -> Iterator[list[AppController]]:
    load_reading_font()
    made: list[AppController] = []
    yield made
    for controller in made:
        controller.google.cancel()
        if controller.sync is not None:
            controller.sync.shutdown()
        for window in (controller.window, controller.login_window):
            if window is not None:
                window.close()
    rig.pool.waitForDone(TIMEOUT_MS)


def make_view(qtbot: QtBot, rig: Rig, language: Language = Language.ES) -> LoginView:
    services = rig.services
    flow = GoogleFlow(
        services.client,
        services.session,
        services.runner,
        services.open_page,
        GOOGLE_TEST_POLL_MS,
    )
    view = LoginView(
        services.client,
        services.session,
        services.runner,
        THEMES[ThemeId.LIGHT],
        language,
        flow,
    )
    view.setStyleSheet(build_stylesheet(THEMES[ThemeId.LIGHT]))
    qtbot.addWidget(view)
    view.resize(1024, 700)
    view.show()
    return view


def shown(view: LoginView) -> list[str]:
    return [
        m.text
        for m in view.findChildren(InlineMessage)
        if m.isVisibleTo(view) and m.text
    ]


def make_settings(qtbot: QtBot, linked: bool | None) -> SettingsView:
    account = AccountInfo("Ana", "ana@example.com", True, linked)
    view = SettingsView(AppConfig(), Language.ES, SpanishSyllabifier(), account)
    view.setStyleSheet(build_stylesheet(THEMES[ThemeId.LIGHT]))
    qtbot.addWidget(view)
    view.resize(1200, 800)
    view.show()
    return view


# ---- login screen -----------------------------------------------------------


@pytest.mark.parametrize("language", list(Language))
def test_the_google_button_sits_above_the_divider_and_the_email(
    qtbot: QtBot, rig: Rig, language: Language
) -> None:
    view = make_view(qtbot, rig, language)
    page = view.sign_in_page
    button = page.google_button
    assert button.text() == tr("auth.google_sign_in", language)
    assert button.accessibleName() in ("", button.text())
    assert not button.icon().isNull()
    labels = [lab for lab in page.findChildren(QLabel) if lab.isVisibleTo(page)]
    divider = next(
        lab for lab in labels if lab.text() == tr("auth.or_with_email", language)
    )

    def top(widget: object) -> int:
        return widget.mapTo(page, widget.rect().topLeft()).y()  # type: ignore[attr-defined]

    assert top(button) < top(divider) < top(page.email)


def test_tab_goes_from_the_google_button_to_the_email(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    page = view.sign_in_page
    page.google_button.setFocus()
    QTest.keyClick(page.google_button, Qt.Key.Key_Tab)
    assert view.focusWidget() is page.email.edit
    assert view.focusWidget() is page.email.edit  # the first field keeps the focus


def test_clicking_google_opens_the_browser_and_shows_the_waiting_card(
    qtbot: QtBot, rig: Rig
) -> None:
    view = make_view(qtbot, rig)
    view.sign_in_page.google_button.click()
    qtbot.waitUntil(
        lambda: view.current_page is LoginPage.GOOGLE_WAITING, timeout=TIMEOUT_MS
    )
    assert rig.browser.paths == ["/v1/auth/google/begin/att-1"]
    page = view.google_page
    assert page.cancel_button.hasFocus()
    texts = {lab.text() for lab in page.findChildren(QLabel)}
    assert tr("google.waiting_title", Language.ES) in texts
    assert tr("google.waiting_body", Language.ES) in texts
    bar = page.findChild(QProgressBar)
    assert bar is not None
    assert bar.accessibleName() == tr("google.waiting_title", Language.ES)
    assert page.cancel_button.text() == tr("google.waiting_cancel", Language.ES)
    view._google.cancel()


@pytest.mark.parametrize("close", ["button", "escape", "alt_left"])
def test_cancelling_stops_the_polling_and_goes_back(
    qtbot: QtBot, rig: Rig, close: str
) -> None:
    view = make_view(qtbot, rig)
    view.sign_in_page.google_button.click()
    qtbot.waitUntil(
        lambda: view.current_page is LoginPage.GOOGLE_WAITING, timeout=TIMEOUT_MS
    )
    if close == "button":
        view.google_page.cancel_button.click()
    elif close == "escape":
        QTest.keyClick(view.google_page.cancel_button, Qt.Key.Key_Escape)
    else:
        QTest.keyClick(
            view.google_page.cancel_button,
            Qt.Key.Key_Left,
            Qt.KeyboardModifier.AltModifier,
        )
    assert view.current_page is LoginPage.SIGN_IN
    assert view.focusWidget() is view.sign_in_page.email.edit
    rig.pool.waitForDone(TIMEOUT_MS)
    polls = rig.server.polls()
    qtbot.wait(5 * GOOGLE_TEST_POLL_MS)
    assert rig.server.polls() == polls


def test_a_google_error_shows_in_line_on_the_sign_in_card(
    qtbot: QtBot, rig: Rig
) -> None:
    rig.server.errors["POST /v1/auth/google/start"] = (503, "google_not_configured")
    view = make_view(qtbot, rig)
    view.sign_in_page.google_button.click()
    qtbot.waitUntil(lambda: bool(shown(view)), timeout=TIMEOUT_MS)
    assert shown(view) == [tr("auth.error.google_not_configured", Language.ES)]
    assert view.current_page is LoginPage.SIGN_IN
    assert view.sign_in_page.google_button.isEnabled()


def test_a_browser_that_will_not_open_shows_its_message(qtbot: QtBot, rig: Rig) -> None:
    rig.browser.opens = False
    view = make_view(qtbot, rig, Language.EN)
    view.sign_in_page.google_button.click()
    qtbot.waitUntil(lambda: bool(shown(view)), timeout=TIMEOUT_MS)
    assert shown(view) == [tr("auth.error.browser_unavailable", Language.EN)]
    assert view.current_page is LoginPage.SIGN_IN
    assert rig.server.polls() == 0


def test_the_google_button_is_blocked_while_the_attempt_starts(
    qtbot: QtBot, rig: Rig
) -> None:
    gate = threading.Event()
    rig.server.gates["POST /v1/auth/google/start"] = gate
    view = make_view(qtbot, rig)
    view.sign_in_page.google_button.click()
    qtbot.waitUntil(
        lambda: not view.sign_in_page.google_button.isEnabled(), timeout=TIMEOUT_MS
    )
    assert not view.sign_in_page.primary.isEnabled()
    gate.set()
    qtbot.waitUntil(
        lambda: view.current_page is LoginPage.GOOGLE_WAITING, timeout=TIMEOUT_MS
    )
    view._google.cancel()


# ---- sign in through the controller ----------------------------------------


def start(controllers: list[AppController], rig: Rig) -> AppController:
    controller = AppController(rig.services)
    controllers.append(controller)
    controller.start()
    return controller


def test_google_sign_in_saves_the_session_and_opens_the_profile(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    rig.server.google_answers = [SIGNED_IN]
    controller = start(controllers, rig)
    assert controller.login_window is not None
    controller.login_window.view.sign_in_page.google_button.click()
    qtbot.waitUntil(lambda: controller.window is not None, timeout=TIMEOUT_MS)
    stored = rig.store.load()
    assert stored is not None and stored.uid == "abc123"
    assert controller.login_window is None
    assert rig.server.count("GET /v1/profile") >= 1  # the same sync as an email sign in
    assert controller.window is not None
    assert controller.window.settings_view.account_card is not None
    assert not controller.google.active


# ---- Settings -> Account -----------------------------------------------------


def test_unlinked_account_shows_the_link_button_and_no_label(qtbot: QtBot) -> None:
    card = make_settings(qtbot, linked=False).account_card
    assert card is not None
    assert card.google_button.isVisibleTo(card)
    assert card.google_button.text() == tr("account.google_link", Language.ES)
    assert not card.google_button.icon().isNull()
    assert not card.google_label.isVisibleTo(card)


def test_linked_account_shows_the_label_and_no_button(qtbot: QtBot) -> None:
    card = make_settings(qtbot, linked=True).account_card
    assert card is not None
    assert not card.google_button.isVisibleTo(card)
    assert card.google_label.isVisibleTo(card)
    assert card.google_label.text() == f"✓ {tr('account.google_linked', Language.ES)}"


def test_unknown_link_state_shows_neither(qtbot: QtBot) -> None:
    card = make_settings(qtbot, linked=None).account_card
    assert card is not None
    assert not card.google_button.isVisibleTo(card)
    assert not card.google_label.isVisibleTo(card)


def test_the_row_follows_the_account_when_it_is_refreshed(qtbot: QtBot) -> None:
    view = make_settings(qtbot, linked=False)
    card = view.account_card
    assert card is not None
    view.set_account(AccountInfo("Ana", "ana@example.com", True, True))
    assert card.google_label.isVisibleTo(card)
    assert not card.google_button.isVisibleTo(card)


def test_the_link_button_is_in_the_tab_order_before_sign_out(qtbot: QtBot) -> None:
    card = make_settings(qtbot, linked=False).account_card
    assert card is not None
    chain: list[QPushButton] = []
    widget = card.google_button
    for _ in range(6):
        widget = widget.nextInFocusChain()  # type: ignore[assignment]
        if isinstance(widget, QPushButton) and widget.isVisibleTo(card):
            chain.append(widget)
    assert card.sign_out_button in chain


def make_profile_window(
    qtbot: QtBot, controllers: list[AppController], rig: Rig, linked: bool
) -> AppController:
    save_session(rig.store)
    rig.server.session_fields = {"google_linked": linked}
    controller = start(controllers, rig)
    qtbot.waitUntil(lambda: controller.window is not None, timeout=TIMEOUT_MS)
    assert controller.window is not None
    controller.window.set_account(AccountInfo("Ana", "ana@example.com", True, linked))
    return controller


def test_linking_shows_the_waiting_dialog_then_the_linked_label(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    controller = make_profile_window(qtbot, controllers, rig, linked=False)
    card = controller.window.settings_view.account_card  # type: ignore[union-attr]
    assert card is not None
    rig.server.google_answers = [(200, {"status": "pending"}), LINKED]
    card.google_button.click()
    qtbot.waitUntil(lambda: card.google_dialog is not None, timeout=TIMEOUT_MS)
    assert rig.server.start_bearers[0] is not None  # linking sends the Bearer
    qtbot.waitUntil(lambda: card.google_dialog is None, timeout=TIMEOUT_MS)
    assert card.google_label.isVisibleTo(card)
    assert not card.google_button.isVisibleTo(card)
    assert rig.browser.paths == ["/v1/auth/google/begin/att-1"]


def test_cancelling_the_link_dialog_stops_the_polling(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    controller = make_profile_window(qtbot, controllers, rig, linked=False)
    card = controller.window.settings_view.account_card  # type: ignore[union-attr]
    assert card is not None
    card.google_button.click()
    qtbot.waitUntil(lambda: card.google_dialog is not None, timeout=TIMEOUT_MS)
    dialog = card.google_dialog
    assert dialog is not None
    assert dialog.page.cancel_button.hasFocus()
    dialog.page.cancel_button.click()
    assert not controller.google.active
    rig.pool.waitForDone(TIMEOUT_MS)
    polls = rig.server.polls()
    qtbot.wait(5 * GOOGLE_TEST_POLL_MS)
    assert rig.server.polls() == polls
    assert card.google_button.isVisibleTo(card)  # still not linked


def test_a_link_error_shows_in_the_card_and_closes_the_dialog(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    controller = make_profile_window(qtbot, controllers, rig, linked=False)
    card = controller.window.settings_view.account_card  # type: ignore[union-attr]
    assert card is not None
    rig.server.google_answers = [(409, {"error": "google_already_linked"})]
    card.google_button.click()
    qtbot.waitUntil(lambda: card.error_message.text != "", timeout=TIMEOUT_MS)
    assert card.error_message.text == tr(
        "auth.error.google_already_linked", Language.ES
    )
    assert card.google_dialog is None
    assert card.google_button.isVisibleTo(card) and card.google_button.isEnabled()


def test_every_google_error_kind_has_a_message_in_both_languages() -> None:
    kinds = [k for k in AccountErrorKind if k.name.startswith("GOOGLE_")]
    kinds += [AccountErrorKind.BROWSER_UNAVAILABLE, AccountErrorKind.EMAIL_NOT_VERIFIED]
    for kind in kinds:
        for language in Language:
            assert tr(f"auth.error.{kind.name.lower()}", language)


def test_linking_refreshes_the_account_without_restarting(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    controller = make_profile_window(qtbot, controllers, rig, linked=False)
    card = controller.window.settings_view.account_card  # type: ignore[union-attr]
    assert card is not None
    rig.server.session_fields = {"google_linked": True, "email_verified": True}
    rig.server.google_answers = [LINKED]
    refreshes = rig.server.count("POST /v1/auth/refresh")
    card.google_button.click()
    qtbot.waitUntil(
        lambda: rig.server.count("POST /v1/auth/refresh") > refreshes,
        timeout=TIMEOUT_MS,
    )
    qtbot.waitUntil(lambda: card.google_label.isVisibleTo(card), timeout=TIMEOUT_MS)


def test_a_confirmed_email_links_without_a_hint(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    controller = make_profile_window(qtbot, controllers, rig, linked=False)
    card = controller.window.settings_view.account_card  # type: ignore[union-attr]
    assert card is not None
    assert not card.google_hint.isVisibleTo(card)
    rig.server.google_answers = [(200, {"status": "pending"})]
    card.google_button.click()
    qtbot.waitUntil(lambda: card.google_dialog is not None, timeout=TIMEOUT_MS)
    assert rig.server.count("POST /v1/auth/google/start") == 1
    assert rig.browser.paths == ["/v1/auth/google/begin/att-1"]


def test_an_email_confirmed_after_the_last_refresh_still_links(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    controller = make_profile_window(qtbot, controllers, rig, linked=False)
    card = controller.window.settings_view.account_card  # type: ignore[union-attr]
    assert card is not None
    controller.window.set_account(  # type: ignore[union-attr]
        AccountInfo("Ana", "ana@example.com", False, False)
    )
    assert card.google_hint.isVisibleTo(card)
    assert card.google_button.isEnabled()
    rig.server.google_answers = [(200, {"status": "pending"})]
    card.google_button.click()
    qtbot.waitUntil(lambda: card.google_dialog is not None, timeout=TIMEOUT_MS)
    assert rig.server.count("POST /v1/auth/google/start") == 1
    assert card.error_message.text == ""
    assert rig.browser.paths == ["/v1/auth/google/begin/att-1"]


def test_a_stale_session_gets_the_backend_refusal_mapped_and_refreshed(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    controller = make_profile_window(qtbot, controllers, rig, linked=False)
    card = controller.window.settings_view.account_card  # type: ignore[union-attr]
    assert card is not None
    rig.server.errors["POST /v1/auth/google/start"] = (403, "email_not_verified")
    rig.server.session_fields = {"google_linked": False, "email_verified": False}
    refreshes = rig.server.count("POST /v1/auth/refresh")
    card.google_button.click()
    qtbot.waitUntil(lambda: card.error_message.text != "", timeout=TIMEOUT_MS)
    assert card.error_message.text == tr("auth.error.email_not_verified", Language.ES)
    assert rig.server.count("POST /v1/auth/google/start") == 1
    assert rig.browser.paths == []
    assert card.google_dialog is None and not controller.google.active
    qtbot.waitUntil(
        lambda: rig.server.count("POST /v1/auth/refresh") > refreshes,
        timeout=TIMEOUT_MS,
    )
    qtbot.waitUntil(lambda: card.google_hint.isVisibleTo(card), timeout=TIMEOUT_MS)
