"""LoginView: validation, states, errors in both languages, privacy gating, Tab order."""

import re
import threading
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from app_fakes import GOOGLE_TEST_POLL_MS, Rig, make_rig
from backend_fakes import make_account_client, session_json
from PySide6.QtCore import Qt
from PySide6.QtGui import QAccessible, QKeySequence, QShortcut, QShortcutEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)
from pytestqt.qtbot import QtBot

from clearread.services.account_client import AccountErrorKind
from clearread.services.session_manager import SessionManager
from clearread.services.session_store import Session
from clearread.ui.google_flow import GoogleFlow
from clearread.ui.strings import CATALOG, Language, tr
from clearread.ui.theme import THEMES, ThemeId, build_stylesheet
from clearread.ui.views.login_pages import (
    RegisterPage,
    SignInPage,
    is_valid_email,
    is_valid_name,
)
from clearread.ui.views.login_view import LoginPage, LoginView
from clearread.ui.views.login_widgets import InlineMessage

TIMEOUT_MS = 5000
SPANISH_CHARS = re.compile("[áéíóúñÁÉÍÓÚÑ¿¡]")
EMAIL = "ana@example.com"
PASSWORD = "secret-pass"


@pytest.fixture
def rig(tmp_path: Path) -> Iterator[Rig]:
    rig = make_rig(tmp_path)
    yield rig
    rig.pool.waitForDone(TIMEOUT_MS)


def make_view(qtbot: QtBot, rig: Rig, language: Language = Language.ES) -> LoginView:
    services = rig.services
    view = LoginView(
        services.client,
        services.session,
        services.runner,
        THEMES[ThemeId.LIGHT],
        language,
        GoogleFlow(
            services.client,
            services.session,
            services.runner,
            services.open_page,
            poll_interval_ms=GOOGLE_TEST_POLL_MS,
        ),
    )
    view.setStyleSheet(build_stylesheet(THEMES[ThemeId.LIGHT]))
    qtbot.addWidget(view)
    view.resize(1024, 700)
    view.show()
    return view


def shown_messages(view: LoginView) -> list[str]:
    return [
        message.text
        for message in view.findChildren(InlineMessage)
        if message.isVisibleTo(view) and message.text
    ]


def fill_sign_in(view: LoginView, email: str = EMAIL, password: str = PASSWORD) -> None:
    page = view.sign_in_page
    page.email.edit.setText(email)
    page.password.edit.setText(password)


def fill_register(view: LoginView, password: str = PASSWORD) -> RegisterPage:
    view.show_page(LoginPage.REGISTER)
    page = view.register_page
    page.name.edit.setText("Ana")
    page.email.edit.setText(EMAIL)
    page.password.edit.setText(password)
    page.confirm.edit.setText(password)
    page.consent.check.setChecked(True)
    return page


def sign_in_and_wait(qtbot: QtBot, view: LoginView) -> Session:
    with qtbot.waitSignal(view.signed_in, timeout=TIMEOUT_MS) as blocker:
        view.sign_in_page.primary.click()
    return blocker.args[0]


# ---- validation helpers -----------------------------------------------------


@pytest.mark.parametrize(
    ("text", "valid"),
    [
        ("ana@example.com", True),
        (" ana@example.com ", True),
        ("ana@example", False),
        ("ana example.com", False),
        ("@example.com", False),
        ("", False),
    ],
)
def test_email_check(text: str, valid: bool) -> None:
    assert is_valid_email(text) is valid


def test_name_check() -> None:
    assert is_valid_name("Ana")
    assert not is_valid_name("   ")
    assert is_valid_name("x" * 32)
    assert not is_valid_name("x" * 33)


# ---- sign in ----------------------------------------------------------------


def test_starts_on_sign_in_with_the_email_field_ready(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    assert view.current_page is LoginPage.SIGN_IN
    assert view.focusWidget() is view.sign_in_page.email.edit


def test_bad_email_is_refused_before_sending(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    fill_sign_in(view, email="not-an-email")
    view.sign_in_page.primary.click()
    assert shown_messages(view) == [tr("auth.validation.email_invalid", Language.ES)]
    assert rig.server.calls == []
    assert view.focusWidget() is view.sign_in_page.email.edit


def test_empty_password_is_refused_before_sending(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    fill_sign_in(view, password="")
    view.sign_in_page.primary.click()
    assert shown_messages(view) == [tr("auth.error.invalid_request", Language.ES)]
    assert rig.server.calls == []


def test_sign_in_emits_the_session_and_keeps_it_in_the_manager(
    qtbot: QtBot, rig: Rig
) -> None:
    view = make_view(qtbot, rig)
    fill_sign_in(view)
    session = sign_in_and_wait(qtbot, view)
    assert isinstance(session, Session)
    assert session.email == EMAIL
    assert rig.services.session.identity is not None


def test_enter_submits_the_page(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    fill_sign_in(view)
    with qtbot.waitSignal(view.signed_in, timeout=TIMEOUT_MS):
        QTest.keyClick(view.sign_in_page.password.edit, Qt.Key.Key_Return)
    assert rig.server.count("POST /v1/auth/login") == 1


@pytest.mark.parametrize("language", list(Language))
def test_wrong_credentials_show_under_the_password(
    qtbot: QtBot, rig: Rig, language: Language
) -> None:
    rig.server.errors["POST /v1/auth/login"] = (401, "invalid_credentials")
    view = make_view(qtbot, rig, language)
    fill_sign_in(view)
    view.sign_in_page.primary.click()
    expected = tr("auth.error.invalid_credentials", language)
    qtbot.waitUntil(lambda: shown_messages(view) == [expected], timeout=TIMEOUT_MS)
    assert view.sign_in_page.password.message.text == expected
    assert not view.sign_in_page.busy
    assert rig.services.session.identity is None


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("kind", list(AccountErrorKind))
def test_each_error_kind_shows_its_own_text_on_every_card(
    qtbot: QtBot, rig: Rig, kind: AccountErrorKind, language: Language
) -> None:
    view = make_view(qtbot, rig, language)
    expected = tr(f"auth.error.{kind.name.lower()}", language)
    view.sign_in_page.show_error(kind)
    assert shown_messages(view) == [expected]
    view.show_page(LoginPage.REGISTER)
    view.register_page.show_error(kind)
    assert shown_messages(view) == [expected]
    view.show_page(LoginPage.RESET)
    view.reset_page.show_error(kind)
    assert shown_messages(view) == [expected]


@pytest.mark.parametrize("kind", list(AccountErrorKind))
def test_every_error_kind_has_both_texts(kind: AccountErrorKind) -> None:
    entry = CATALOG[f"auth.error.{kind.name.lower()}"]
    assert entry["es"] and entry["en"]


def test_english_login_has_no_spanish_text(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig, Language.EN)
    texts = [
        widget.text()
        for kind in (QLabel, QPushButton, QCheckBox)
        for widget in view.findChildren(kind)
    ]
    assert [text for text in texts if SPANISH_CHARS.search(text)] == []


def test_session_ended_notice_on_the_sign_in_card(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    view.show_session_ended()
    assert shown_messages(view) == [tr("auth.error.session_revoked", Language.ES)]


def test_deleted_account_notice_uses_a_success_row(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    view.show_account_deleted()
    assert shown_messages(view) == [tr("account.deleted", Language.ES)]


def test_password_can_be_shown_and_hidden_with_named_buttons(
    qtbot: QtBot, rig: Rig
) -> None:
    view = make_view(qtbot, rig)
    field = view.sign_in_page.password_field
    toggle = field.toggle
    assert toggle.text() == tr("auth.show_password", Language.ES)
    assert toggle.accessibleName() == tr("auth.show_password_a11y", Language.ES)
    toggle.click()
    assert field.revealed
    assert field.edit.echoMode().name == "Normal"
    assert toggle.text() == tr("auth.hide_password", Language.ES)
    assert toggle.accessibleName() == tr("auth.hide_password_a11y", Language.ES)
    toggle.click()
    assert field.edit.echoMode().name == "Password"


def test_fields_have_visible_labels_and_accessible_names(
    qtbot: QtBot, rig: Rig
) -> None:
    view = make_view(qtbot, rig)
    page = view.sign_in_page
    assert page.email.label.text() == tr("auth.email_label", Language.ES)
    assert page.email.label.buddy() is page.email.edit
    assert page.password.edit.accessibleName() == tr("auth.password_label", Language.ES)


def test_offline_shows_badge_and_note_but_keeps_the_button(
    qtbot: QtBot, rig: Rig
) -> None:
    view = make_view(qtbot, rig)
    view.set_online(False)
    assert view.offline_badge.isVisible()
    assert view.offline_badge.text() == tr("ai.offline_badge", Language.ES)
    assert view.sign_in_page.offline_note.isVisible()
    assert view.sign_in_page.primary.isEnabled()
    view.set_online(True)
    assert not view.offline_badge.isVisible()


def test_sign_in_card_is_one_card_of_440_px(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    qtbot.waitUntil(lambda: view.sign_in_page.width() == 440, timeout=TIMEOUT_MS)
    assert view.sign_in_page.objectName() == "LoginCard"


def test_no_horizontal_scroll_and_buttons_in_view_at_the_smallest_window(
    qtbot: QtBot, rig: Rig
) -> None:
    view = make_view(qtbot, rig)
    view.resize(1024, 700)
    for page in LoginPage:
        view.show_page(page)
        qtbot.wait(20)
        assert not view.scroll.horizontalScrollBar().isVisible()
        area = view.scroll.widget()
        for button in view.stack.currentWidget().findChildren(QPushButton):
            if button.isVisible():
                corner = button.mapTo(area, button.rect().bottomRight())
                assert corner.x() <= area.width()


# ---- busy and waking --------------------------------------------------------


class SlowLogin:
    """Backend whose sign-in waits for the test; the first health probe says asleep."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.probes = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            self.probes += 1
            return httpx.Response(200 if self.probes > 1 else 503, json={})
        self.release.wait(timeout=10)
        return httpx.Response(200, json=session_json())


def make_slow_rig(tmp_path: Path) -> tuple[Rig, SlowLogin]:
    rig = make_rig(tmp_path)
    slow = SlowLogin()
    client, _ = make_account_client(slow)
    session = SessionManager(client, rig.store)
    services = replace(rig.services, client=client, session=session)
    return replace(rig, services=services), slow


def test_busy_state_and_waking_line_then_success(qtbot: QtBot, tmp_path: Path) -> None:
    rig, slow = make_slow_rig(tmp_path)
    view = make_view(qtbot, rig)
    fill_sign_in(view)
    view.sign_in_page.primary.click()
    page = view.sign_in_page
    qtbot.waitUntil(lambda: page.strip.waking_visible, timeout=TIMEOUT_MS)
    assert page.primary.text() == tr("auth.signing_in", Language.ES)
    assert not page.primary.isEnabled()
    assert not page.email.edit.isEnabled()
    assert not page.password.edit.isEnabled()
    assert not page.create_button.isEnabled()
    assert page.strip.isVisible()
    with qtbot.waitSignal(view.signed_in, timeout=TIMEOUT_MS):
        slow.release.set()
    assert page.primary.isEnabled()
    assert page.primary.text() == tr("auth.sign_in_button", Language.ES)


def test_cancel_stops_waiting_and_undoes_a_late_sign_in(
    qtbot: QtBot, tmp_path: Path
) -> None:
    rig, slow = make_slow_rig(tmp_path)
    view = make_view(qtbot, rig)
    fill_sign_in(view)
    view.sign_in_page.primary.click()
    qtbot.waitUntil(lambda: view.sign_in_page.strip.waking_visible, timeout=TIMEOUT_MS)
    QTest.mouseClick(
        view.sign_in_page.strip.findChildren(QPushButton)[0], Qt.MouseButton.LeftButton
    )
    assert view.sign_in_page.primary.isEnabled()
    signed: list[object] = []
    view.signed_in.connect(signed.append)
    slow.release.set()
    qtbot.waitUntil(lambda: rig.pool.activeThreadCount() == 0, timeout=TIMEOUT_MS)
    qtbot.waitUntil(lambda: rig.services.session.identity is None, timeout=TIMEOUT_MS)
    assert signed == []


# ---- create account ---------------------------------------------------------


def test_create_button_waits_for_the_privacy_checkbox(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.REGISTER)
    page = view.register_page
    assert not page.primary.isEnabled()
    assert page.primary.toolTip() == tr("auth.register_disabled_tip", Language.ES)
    page.consent.check.setChecked(True)
    assert page.primary.isEnabled()
    assert page.primary.toolTip() == ""
    page.consent.check.setChecked(False)
    assert not page.primary.isEnabled()


def test_enter_does_not_create_an_account_without_the_checkbox(
    qtbot: QtBot, rig: Rig
) -> None:
    view = make_view(qtbot, rig)
    page = fill_register(view)
    page.consent.check.setChecked(False)
    QTest.keyClick(page.password.edit, Qt.Key.Key_Return)
    assert rig.server.calls == []


def test_clicking_the_sentence_ticks_the_box(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.REGISTER)
    sentence = next(
        label
        for label in view.register_page.consent.findChildren(QLabel)
        if label.text() == tr("auth.privacy_consent", Language.ES)
    )
    QTest.mouseClick(sentence, Qt.MouseButton.LeftButton)
    assert view.register_page.consent.check.isChecked()


def test_privacy_link_opens_the_notice_in_a_dialog(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.REGISTER)
    view.register_page.privacy_button.click()
    dialog = view.privacy_dialog
    assert dialog is not None
    assert dialog.windowTitle() == tr("auth.privacy_title", Language.ES)
    bodies = [label.text() for label in dialog.findChildren(QLabel)]
    assert tr("auth.privacy_body", Language.ES) in bodies
    dialog.accept()


@pytest.mark.parametrize(
    ("name", "email", "password", "expected_key"),
    [
        ("", EMAIL, PASSWORD, "auth.validation.name_required"),
        ("   ", EMAIL, PASSWORD, "auth.validation.name_required"),
        ("Ana", "ana@", PASSWORD, "auth.validation.email_invalid"),
        ("Ana", EMAIL, "short", "auth.error.password_too_short"),
        ("Ana", EMAIL, "x" * 33, "auth.validation.password_too_long"),
        ("x" * 33, EMAIL, PASSWORD, "auth.validation.name_too_long"),
        ("Ana", "a" * 60 + "@example.com", PASSWORD, "auth.validation.email_too_long"),
    ],
)
def test_register_checks_fields_before_sending(
    qtbot: QtBot, rig: Rig, name: str, email: str, password: str, expected_key: str
) -> None:
    view = make_view(qtbot, rig)
    page = fill_register(view, password)
    lift_the_limits(page)
    page.name.edit.setText(name)
    page.email.edit.setText(email)
    page.password.edit.setText(password)
    page.confirm.edit.setText(password)
    page.primary.click()
    assert shown_messages(view)[-1] == tr(expected_key, Language.ES)
    assert rig.server.calls == []


def lift_the_limits(page: RegisterPage) -> None:
    """The fields stop typing at their limit; this reaches the checks behind them."""
    for block in (page.name, page.email, page.password, page.confirm):
        block.edit.setMaxLength(1000)


def test_password_help_counts_and_goes_away_at_eight(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.REGISTER)
    edit = view.register_page.password.edit
    edit.setText("abcdef")
    assert shown_messages(view) == [tr("auth.password_count", Language.ES, count=6)]
    edit.setText("abcdefgh")
    assert shown_messages(view) == []
    edit.setMaxLength(1000)
    edit.setText("x" * 33)
    assert tr("auth.validation.password_too_long", Language.ES) in shown_messages(view)


def test_register_sends_the_name_and_emits_the_session(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    page = fill_register(view)
    with qtbot.waitSignal(view.signed_in, timeout=TIMEOUT_MS):
        page.primary.click()
    assert rig.server.count("POST /v1/auth/register") == 1


def test_email_in_use_shows_under_the_email_field(qtbot: QtBot, rig: Rig) -> None:
    rig.server.errors["POST /v1/auth/register"] = (409, "email_exists")
    view = make_view(qtbot, rig)
    page = fill_register(view)
    page.primary.click()
    expected = tr("auth.error.email_exists", Language.ES)
    qtbot.waitUntil(lambda: page.email.message.text == expected, timeout=TIMEOUT_MS)
    assert view.focusWidget() is page.email.edit


# ---- reset password ---------------------------------------------------------


def test_reset_goes_to_step_two_and_says_the_same_for_any_email(
    qtbot: QtBot, rig: Rig
) -> None:
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.RESET)
    page = view.reset_page
    page.email.edit.setText("nadie@example.com")
    page.send_button.click()
    expected = tr("auth.reset_done_body", Language.ES, email="nadie@example.com")
    qtbot.waitUntil(lambda: page.on_done_step, timeout=TIMEOUT_MS)
    assert page.done_body.text() == expected
    assert rig.server.count("POST /v1/auth/password-reset") == 1


def test_reset_refuses_a_bad_email_and_resend_sends_again(
    qtbot: QtBot, rig: Rig
) -> None:
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.RESET)
    page = view.reset_page
    page.email.edit.setText("mal")
    page.send_button.click()
    assert shown_messages(view) == [tr("auth.validation.email_invalid", Language.ES)]
    assert rig.server.calls == []
    page.email.edit.setText(EMAIL)
    page.send_button.click()
    qtbot.waitUntil(lambda: page.on_done_step, timeout=TIMEOUT_MS)
    page.resend_button.click()
    qtbot.waitUntil(
        lambda: rig.server.count("POST /v1/auth/password-reset") == 2,
        timeout=TIMEOUT_MS,
    )


def test_reset_failure_is_shown_on_the_first_step(qtbot: QtBot, rig: Rig) -> None:
    rig.server.errors["POST /v1/auth/password-reset"] = (429, "too_many_attempts")
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.RESET)
    page = view.reset_page
    page.email.edit.setText(EMAIL)
    page.send_button.click()
    expected = tr("auth.error.too_many_attempts", Language.ES)
    qtbot.waitUntil(lambda: shown_messages(view) == [expected], timeout=TIMEOUT_MS)
    assert not page.on_done_step


def test_back_to_sign_in_ends_the_second_step(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.RESET)
    view.reset_page.email.edit.setText(EMAIL)
    view.reset_page.send_button.click()
    qtbot.waitUntil(lambda: view.reset_page.on_done_step, timeout=TIMEOUT_MS)
    view.reset_page.signin_button.click()
    assert view.current_page is LoginPage.SIGN_IN
    view.show_page(LoginPage.RESET)
    assert not view.reset_page.on_done_step


# ---- navigation and keyboard ------------------------------------------------


def press_shortcut(view: LoginView, text: str) -> None:
    """Fire the QShortcut bound to ``text`` through Qt's own shortcut event.

    Real key presses reach a QShortcut only while the window is the active one, which
    the offscreen platform does not guarantee (same approach as test_reading_view).
    """
    sequence = QKeySequence(text)
    shortcut = next(s for s in view.findChildren(QShortcut) if s.key() == sequence)
    assert shortcut.context() is Qt.ShortcutContext.WidgetWithChildrenShortcut
    QApplication.sendEvent(shortcut, QShortcutEvent(sequence, shortcut.id()))


@pytest.mark.filterwarnings("ignore:Function.*QShortcut.id:DeprecationWarning")
@pytest.mark.parametrize("page", [LoginPage.REGISTER, LoginPage.RESET])
@pytest.mark.parametrize("sequence", ["Esc", "Alt+Left"])
def test_escape_and_alt_left_go_back_and_keep_the_email(
    qtbot: QtBot, rig: Rig, page: LoginPage, sequence: str
) -> None:
    view = make_view(qtbot, rig)
    view.sign_in_page.email.edit.setText(EMAIL)
    view.show_page(page)
    press_shortcut(view, sequence)
    assert view.current_page is LoginPage.SIGN_IN
    assert view.sign_in_page.email.edit.text() == EMAIL


@pytest.mark.filterwarnings("ignore:Function.*QShortcut.id:DeprecationWarning")
def test_escape_does_not_leave_the_first_page(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    press_shortcut(view, "Esc")
    assert view.current_page is LoginPage.SIGN_IN


def test_register_and_reset_copy_the_typed_email(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    view.sign_in_page.email.edit.setText(EMAIL)
    view.sign_in_page.create_button.click()
    assert view.register_page.email.edit.text() == EMAIL
    view.go_back()
    view.sign_in_page.forgot_button.click()
    assert view.reset_page.email.edit.text() == EMAIL


def focus_order(view: LoginView, first: QWidget, last: QWidget) -> list[QWidget]:
    """Widgets Tab visits from ``first`` to ``last``, skipping hidden and disabled ones."""
    order = [first]
    widget = first.nextInFocusChain()
    while widget is not first and order[-1] is not last:
        usable = (
            widget.isVisibleTo(view)
            and widget.isEnabled()
            and widget.focusPolicy() != Qt.FocusPolicy.NoFocus
        )
        if usable:
            order.append(widget)
        widget = widget.nextInFocusChain()
    return order


def test_tab_order_of_the_sign_in_card(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    page: SignInPage = view.sign_in_page
    expected = [
        page.email.edit,
        page.password.edit,
        page.password_field.toggle,
        page.forgot_button,
        page.primary,
        page.create_button,
        page.privacy_button,
    ]
    assert focus_order(view, page.email.edit, page.privacy_button) == expected


def test_tab_order_of_the_create_card(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.REGISTER)
    page = view.register_page
    page.consent.check.setChecked(True)
    expected = [
        page.back_button,
        page.name.edit,
        page.email.edit,
        page.password.edit,
        page.password_field.toggle,
        page.confirm.edit,
        page.consent.check,
        page.privacy_button,
        page.primary,
    ]
    assert focus_order(view, page.back_button, page.primary) == expected


def test_tab_order_of_the_reset_card_in_both_steps(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.RESET)
    page = view.reset_page
    ask = [page.back_button, page.email.edit, page.send_button]
    assert focus_order(view, page.back_button, page.send_button) == ask
    page.show_done(EMAIL)
    done = [page.resend_button, page.signin_button]
    assert focus_order(view, page.resend_button, page.signin_button) == done


def test_primary_disabled_style_is_dashed_in_the_stylesheet() -> None:
    sheet = build_stylesheet(THEMES[ThemeId.DARK])
    rule = sheet[sheet.index('QPushButton[variant="primary"]:disabled') :]
    assert "dashed" in rule.split("}")[0]


@pytest.mark.parametrize(
    ("field", "limit"),
    [("name", 32), ("email", 64), ("password", 32), ("confirm", 32)],
)
def test_the_register_fields_stop_at_their_limit(
    qtbot: QtBot, rig: Rig, field: str, limit: int
) -> None:
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.REGISTER)
    edit = getattr(view.register_page, field).edit
    edit.setText("x" * 100)
    assert len(edit.text()) == limit


def test_the_sign_in_fields_stop_at_their_limit(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    page = view.sign_in_page
    page.email.edit.setText("x" * 100)
    page.password.edit.setText("x" * 100)
    assert len(page.email.edit.text()) == 64
    assert len(page.password.edit.text()) == 32


# ---- repeat the password ----------------------------------------------------


def test_the_create_card_asks_to_repeat_the_password(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.REGISTER)
    page = view.register_page
    assert page.confirm.label.text() == tr("auth.confirm_label", Language.ES)
    assert page.confirm.edit.accessibleName() == tr("auth.confirm_label", Language.ES)
    assert page.confirm.edit.echoMode() == QLineEdit.EchoMode.Password


def test_differing_passwords_disable_create_and_never_send(
    qtbot: QtBot, rig: Rig
) -> None:
    view = make_view(qtbot, rig)
    page = fill_register(view)
    assert page.primary.isEnabled()
    page.confirm.edit.setText("other-pass")
    assert not page.primary.isEnabled()
    assert shown_messages(view) == [
        tr("auth.validation.password_mismatch", Language.ES)
    ]
    page.primary.click()
    page.name.edit.returnPressed.emit()
    page.confirm.edit.returnPressed.emit()
    assert rig.server.calls == []


def test_the_mismatch_message_waits_for_the_confirm_field(
    qtbot: QtBot, rig: Rig
) -> None:
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.REGISTER)
    page = view.register_page
    page.password.edit.setText("abcdefgh")
    assert shown_messages(view) == []
    page.confirm.edit.setText("abc")
    assert shown_messages(view) == [
        tr("auth.validation.password_mismatch", Language.ES)
    ]


def test_matching_again_clears_the_message_and_allows_creating(
    qtbot: QtBot, rig: Rig
) -> None:
    view = make_view(qtbot, rig)
    page = fill_register(view)
    page.confirm.edit.setText("other-pass")
    page.confirm.edit.setText(PASSWORD)
    assert shown_messages(view) == []
    assert page.primary.isEnabled()
    with qtbot.waitSignal(view.signed_in, timeout=TIMEOUT_MS):
        page.primary.click()
    assert rig.server.count("POST /v1/auth/register") == 1


def test_changing_the_password_after_confirming_shows_the_mismatch(
    qtbot: QtBot, rig: Rig
) -> None:
    view = make_view(qtbot, rig)
    page = fill_register(view)
    page.password.edit.setText(PASSWORD + "x")
    assert not page.primary.isEnabled()
    assert tr("auth.validation.password_mismatch", Language.ES) in shown_messages(view)


def test_show_password_reveals_both_fields(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.REGISTER)
    page = view.register_page
    page.password_field.toggle.click()
    assert page.confirm.edit.echoMode() == QLineEdit.EchoMode.Normal
    page.password_field.toggle.click()
    assert page.confirm.edit.echoMode() == QLineEdit.EchoMode.Password


# ---- email format and the new backend codes ---------------------------------


@pytest.mark.parametrize(
    ("email", "key"),
    [
        ("ana@", "auth.validation.email_invalid"),
        ("ana example.com", "auth.validation.email_invalid"),
        ("ana@example", "auth.validation.email_invalid"),
    ],
)
def test_sign_in_checks_the_email_before_sending(
    qtbot: QtBot, rig: Rig, email: str, key: str
) -> None:
    view = make_view(qtbot, rig)
    fill_sign_in(view, email=email)
    view.sign_in_page.primary.click()
    assert shown_messages(view) == [tr(key, Language.ES)]
    assert rig.server.calls == []


def test_sign_in_trims_the_email_before_sending(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    fill_sign_in(view, email=f"  {EMAIL}  ")
    sign_in_and_wait(qtbot, view)
    assert rig.server.count("POST /v1/auth/login") == 1


def test_reset_checks_the_email_before_sending(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.RESET)
    page = view.reset_page
    page.email.edit.setText("ana@")
    page.send_button.click()
    assert shown_messages(view) == [tr("auth.validation.email_invalid", Language.ES)]
    assert rig.server.calls == []


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize(
    ("kind", "field"),
    [
        (AccountErrorKind.INVALID_EMAIL, "email"),
        (AccountErrorKind.EMAIL_TOO_LONG, "email"),
        (AccountErrorKind.PASSWORD_TOO_LONG, "password"),
        (AccountErrorKind.NAME_TOO_LONG, "name"),
    ],
)
def test_the_new_backend_codes_show_next_to_their_field(
    qtbot: QtBot, rig: Rig, language: Language, kind: AccountErrorKind, field: str
) -> None:
    view = make_view(qtbot, rig, language)
    view.show_page(LoginPage.REGISTER)
    view.register_page.show_error(kind)
    block = getattr(view.register_page, field)
    assert block.message.text == tr(f"auth.error.{kind.value}", language)


@pytest.mark.parametrize(
    ("code", "kind"),
    [
        ("invalid_email", AccountErrorKind.INVALID_EMAIL),
        ("email_too_long", AccountErrorKind.EMAIL_TOO_LONG),
        ("password_too_long", AccountErrorKind.PASSWORD_TOO_LONG),
        ("name_too_long", AccountErrorKind.NAME_TOO_LONG),
    ],
)
def test_the_new_backend_codes_become_account_errors(
    qtbot: QtBot, rig: Rig, code: str, kind: AccountErrorKind
) -> None:
    rig.server.errors["POST /v1/auth/login"] = (422, code)
    view = make_view(qtbot, rig)
    fill_sign_in(view)
    view.sign_in_page.primary.click()
    expected = tr(f"auth.error.{kind.value}", Language.ES)
    qtbot.waitUntil(lambda: expected in shown_messages(view), timeout=TIMEOUT_MS)


# ---- privacy notice ---------------------------------------------------------


@pytest.mark.parametrize("language", list(Language))
def test_the_notice_has_no_internal_references(language: Language) -> None:
    body = tr("auth.privacy_body", language)
    assert "§" not in body
    assert "Borrador" not in body
    assert "Draft" not in body


def test_the_sign_in_page_links_to_the_notice(qtbot: QtBot, rig: Rig) -> None:
    view = make_view(qtbot, rig)
    page = view.sign_in_page
    assert page.privacy_button.text() == tr("auth.privacy_link", Language.ES)
    page.privacy_button.click()
    assert view.privacy_dialog is not None
    view.privacy_dialog.accept()


def test_the_notice_scrolls_and_is_centered_over_the_window(
    qtbot: QtBot, rig: Rig
) -> None:
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.REGISTER)
    view.register_page.privacy_button.click()
    dialog = view.privacy_dialog
    assert dialog is not None
    qtbot.waitUntil(dialog.isVisible, timeout=TIMEOUT_MS)
    assert dialog.parent() is view.window()
    assert dialog.scroll.widget() is not None
    owner = view.window().frameGeometry().center()
    assert abs(dialog.frameGeometry().center().x() - owner.x()) <= 2
    assert abs(dialog.frameGeometry().center().y() - owner.y()) <= 2
    dialog.accept()


def record_accessibility_events(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    events: list[object] = []
    monkeypatch.setattr(
        "clearread.ui.views.login_widgets.QAccessible.updateAccessibility",
        lambda event: events.append(event.type()),
    )
    return events


def test_typing_while_the_passwords_differ_never_raises_an_alert(
    qtbot: QtBot, rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = make_view(qtbot, rig)
    view.show_page(LoginPage.REGISTER)
    page = view.register_page
    events = record_accessibility_events(monkeypatch)
    for text in ("a", "ab", "abc", "abcd"):
        page.password.edit.setText(text)
    page.confirm.edit.setText("x")
    for text in ("xy", "xyz", "xyzw"):
        page.confirm.edit.setText(text)
    for text in ("abcde", "abcdef", "abcdefg"):
        page.password.edit.setText(text)
    assert QAccessible.Event.Alert not in events
    assert events.count(QAccessible.Event.NameChanged) == 2


def test_a_repeated_message_is_announced_once(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    message = InlineMessage()
    qtbot.addWidget(message)
    events = record_accessibility_events(monkeypatch)
    for _ in range(5):
        message.show_message("same")
    assert events == [QAccessible.Event.Alert]
    message.show_message("other")
    assert events == [QAccessible.Event.Alert] * 2
