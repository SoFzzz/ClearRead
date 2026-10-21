"""AppController: startup with and without a session, sign in, sync, sign out, delete."""

import json
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from app_fakes import UID, Rig, make_rig, save_session
from PySide6.QtNetwork import QNetworkInformation
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from clearread.core.config import AppConfig
from clearread.core.device_settings import DeviceSettings
from clearread.services.glossary import GlossaryEntry, GlossaryStore
from clearread.ui.app_controller import AppController
from clearread.ui.fonts import load_reading_font
from clearread.ui.main_window import MainWindow
from clearread.ui.strings import Language, tr
from clearread.ui.views.login_view import LoginPage
from clearread.ui.views.login_widgets import InlineMessage

TIMEOUT_MS = 8000
FUTURE = "2030-01-01T00:00:00Z"
DISCONNECTED = QNetworkInformation.Reachability.Disconnected


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return make_rig(tmp_path)


@pytest.fixture
def controllers(qtbot: QtBot, rig: Rig) -> Iterator[list[AppController]]:
    load_reading_font()
    made: list[AppController] = []
    yield made
    for controller in made:
        if controller.sync is not None:
            controller.sync.shutdown()
        for window in (controller.window, controller.login_window):
            if window is not None:
                window.close()
    rig.pool.waitForDone(TIMEOUT_MS)


def start(controllers: list[AppController], rig: Rig) -> AppController:
    controller = AppController(rig.services)
    controllers.append(controller)
    controller.start()
    return controller


def profile_dir(rig: Rig) -> Path:
    """Where the profile's files are; unlike ``profile_dir_for`` it never creates it."""
    return rig.services.data_dir / "profiles" / UID


def main_window(controller: AppController) -> MainWindow:
    assert controller.window is not None
    return controller.window


def press(box: QMessageBox, text: str) -> None:
    next(b for b in box.buttons() if b.text() == text).click()


def sign_in_through_the_login(qtbot: QtBot, controller: AppController) -> None:
    assert controller.login_window is not None
    view = controller.login_window.view
    page = view.sign_in_page
    page.email.edit.setText("ana@example.com")
    page.password.edit.setText("secret-pass")
    page.primary.click()
    qtbot.waitUntil(lambda: controller.window is not None, timeout=TIMEOUT_MS)


def login_messages(controller: AppController) -> list[str]:
    assert controller.login_window is not None
    view = controller.login_window.view
    return [m.text for m in view.sign_in_page.findChildren(InlineMessage) if m.text]


def wait_synced(qtbot: QtBot, controller: AppController) -> None:
    assert controller.sync is not None
    sync = controller.sync
    qtbot.waitUntil(lambda: not sync.has_unsaved_changes, timeout=TIMEOUT_MS)


def remote_profile(**settings: object) -> dict[str, object]:
    return {"settings": settings, "words": [], "topics": [], "updated_at": FUTURE}


# ---- startup ----------------------------------------------------------------


def test_without_a_stored_session_the_login_shows(
    controllers: list[AppController], rig: Rig
) -> None:
    controller = start(controllers, rig)
    assert controller.login_window is not None
    assert controller.window is None
    assert controller.login_window.view.current_page is LoginPage.SIGN_IN
    assert rig.server.calls == []


def test_a_damaged_session_file_also_shows_the_login(
    controllers: list[AppController], rig: Rig, tmp_path: Path
) -> None:
    (tmp_path / "session.bin").write_bytes(b"\x00not a session")
    controller = start(controllers, rig)
    assert controller.login_window is not None
    assert controller.window is None


def test_with_a_stored_session_the_main_window_opens_at_once(
    controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    gate = threading.Event()
    rig.server.gates["POST /v1/auth/refresh"] = gate
    controller = start(controllers, rig)
    assert controller.login_window is None
    window = main_window(controller)
    assert window.isVisible()
    assert window.settings_view.account_card is not None
    assert window.settings_view.account_card.name_label.full_text == "Ana"
    gate.set()


def test_offline_start_opens_the_profile_and_makes_no_calls(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    rig.network.set_reachability(DISCONNECTED)
    controller = start(controllers, rig)
    window = main_window(controller)
    qtbot.wait(150)
    assert rig.server.calls == []
    assert window.settings_view.account_card is not None
    assert window.settings_view.account_card.offline_note.isHidden() is False
    assert controller.sync is not None
    assert controller.sync.has_unsaved_changes


def test_back_online_refreshes_the_account_and_syncs(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    rig.network.set_reachability(DISCONNECTED)
    controller = start(controllers, rig)
    rig.network.set_reachability(QNetworkInformation.Reachability.Online)
    wait_synced(qtbot, controller)
    assert rig.server.count("POST /v1/auth/refresh") >= 1
    assert rig.server.count("PUT /v1/profile") == 1  # no remote profile yet: push


def test_online_start_refreshes_in_the_background_then_syncs(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    assert rig.server.calls[0] == "POST /v1/auth/refresh"
    assert "GET /v1/profile" in rig.server.calls
    card = main_window(controller).settings_view.account_card
    assert card is not None
    assert tr("account.not_verified", Language.ES) in card.badge.text()


def test_a_revoked_session_at_startup_returns_to_the_login_keeping_the_data(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    AppConfig(font_size_pt=22).save(profile_dir(rig))
    rig.server.errors["POST /v1/auth/refresh"] = (401, "session_revoked")
    controller = start(controllers, rig)
    qtbot.waitUntil(lambda: controller.window is None, timeout=TIMEOUT_MS)
    assert controller.login_window is not None
    assert tr("auth.error.session_revoked", Language.ES) in login_messages(controller)
    assert rig.store.load() is None
    assert AppConfig.load(profile_dir(rig)).font_size_pt == 22


# ---- sign in ----------------------------------------------------------------


def test_signing_in_opens_the_profile_and_closes_the_login(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    controller = start(controllers, rig)
    login = controller.login_window
    sign_in_through_the_login(qtbot, controller)
    assert controller.login_window is None
    assert login is not None
    assert not login.isVisible()
    assert main_window(controller).isVisible()
    assert rig.store.load() is not None
    assert profile_dir(rig).is_dir()


def test_first_sign_in_adopts_the_old_files_and_says_so(
    qtbot: QtBot, controllers: list[AppController], rig: Rig, tmp_path: Path
) -> None:
    AppConfig(theme="dark", font_size_pt=24).save(tmp_path)
    GlossaryStore(tmp_path / "glossary.json").add(
        GlossaryEntry("casa", "Un lugar.", "doc", "2026-10-19")
    )
    controller = start(controllers, rig)
    sign_in_through_the_login(qtbot, controller)
    window = main_window(controller)
    assert window.config.theme == "dark"
    assert window.config.font_size_pt == 24
    assert not (tmp_path / "config.json").exists()
    assert (profile_dir(rig) / "glossary.json").exists()
    assert window.notice_box is not None
    assert window.notice_box.text() == tr("profile.migrated", Language.ES)


def test_stores_live_inside_the_profile_folder(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    controller = start(controllers, rig)
    sign_in_through_the_login(qtbot, controller)
    window = main_window(controller)
    window.settings_view.font_combo.setCurrentIndex(1)
    assert AppConfig.load(profile_dir(rig)).reading_font == "Atkinson Hyperlegible"
    window._on_word_explained("casa", "Un lugar.")
    assert (profile_dir(rig) / "glossary.json").exists()


def test_a_new_account_pushes_its_profile(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    controller = start(controllers, rig)
    sign_in_through_the_login(qtbot, controller)
    wait_synced(qtbot, controller)
    assert rig.server.profile is not None
    assert rig.server.count("POST /v1/auth/refresh") == 0  # just signed in


# ---- sync after changes -----------------------------------------------------


def test_a_setting_change_is_pushed_after_the_debounce(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    pushes = rig.server.count("PUT /v1/profile")
    main_window(controller).settings_view.theme_buttons["dark"].setChecked(True)
    assert controller.sync is not None
    assert controller.sync.has_unsaved_changes
    qtbot.waitUntil(
        lambda: rig.server.count("PUT /v1/profile") == pushes + 1, timeout=TIMEOUT_MS
    )
    assert rig.server.profile is not None
    assert rig.server.profile["settings"]["theme"] == "dark"  # type: ignore[index]


def test_a_new_word_is_pushed(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    main_window(controller)._on_word_explained("casa", "Un lugar.")
    qtbot.waitUntil(
        lambda: (
            rig.server.profile is not None
            and [w["word"] for w in rig.server.profile["words"]] == ["casa"]
        ),  # type: ignore[index]
        timeout=TIMEOUT_MS,
    )


def test_a_topic_change_is_pushed(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    window = main_window(controller)
    window._topics.create("Biologia")
    window._library_controller.refresh_after_change()
    qtbot.waitUntil(
        lambda: (
            rig.server.profile is not None
            and [t["name"] for t in rig.server.profile["topics"]] == ["Biologia"]
        ),  # type: ignore[index]
        timeout=TIMEOUT_MS,
    )


def test_changes_made_offline_go_out_when_the_network_returns(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    rig.network.set_reachability(DISCONNECTED)
    pushes = rig.server.count("PUT /v1/profile")
    main_window(controller).settings_view.theme_buttons["dark"].setChecked(True)
    qtbot.wait(300)
    assert rig.server.count("PUT /v1/profile") == pushes
    rig.network.set_reachability(QNetworkInformation.Reachability.Online)
    qtbot.waitUntil(
        lambda: rig.server.count("PUT /v1/profile") == pushes + 1, timeout=TIMEOUT_MS
    )


def test_a_pulled_profile_is_applied_without_being_pushed_back(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    rig.server.profile = remote_profile(theme="dark", font_size_pt=26)
    save_session(rig.store)
    controller = start(controllers, rig)
    window = main_window(controller)
    qtbot.waitUntil(lambda: window.config.theme == "dark", timeout=TIMEOUT_MS)
    assert window.config.font_size_pt == 26
    assert window.settings_view.config.font_size_pt == 26
    wait_synced(qtbot, controller)
    qtbot.wait(300)
    assert rig.server.count("PUT /v1/profile") == 0
    assert AppConfig.load(profile_dir(rig)).theme == "dark"


def test_a_pulled_language_waits_for_the_next_start_and_says_so(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    rig.server.profile = remote_profile(ui_language="en")
    save_session(rig.store)
    controller = start(controllers, rig)
    window = main_window(controller)
    qtbot.waitUntil(lambda: window.notice_box is not None, timeout=TIMEOUT_MS)
    assert window.notice_box is not None
    assert window.notice_box.text() == tr("profile.language_pending", Language.ES)
    assert window.config.ui_language == "en"
    assert window.settings_view._language is Language.ES  # no restart by itself
    assert not window.restart_requested


def test_no_language_notice_when_the_language_is_the_same(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    rig.server.profile = remote_profile(theme="dark", ui_language="es")
    save_session(rig.store)
    controller = start(controllers, rig)
    window = main_window(controller)
    qtbot.waitUntil(lambda: window.config.theme == "dark", timeout=TIMEOUT_MS)
    assert window.notice_box is None


# ---- device.json ------------------------------------------------------------


def test_device_file_follows_the_profile_look(
    qtbot: QtBot, controllers: list[AppController], rig: Rig, tmp_path: Path
) -> None:
    AppConfig(theme="dark", ui_language="en").save(profile_dir(rig))
    save_session(rig.store)
    controller = start(controllers, rig)
    store = rig.services.device
    assert store.load() == DeviceSettings("dark", "en")
    main_window(controller).settings_view.theme_buttons["light"].setChecked(True)
    assert store.load() == DeviceSettings("light", "en")
    assert json.loads((tmp_path / "device.json").read_text("utf-8")) == {
        "theme": "light",
        "ui_language": "en",
    }


def test_a_pulled_language_is_remembered_for_the_login_screens(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    rig.server.profile = remote_profile(ui_language="en")
    save_session(rig.store)
    start(controllers, rig)
    qtbot.waitUntil(
        lambda: rig.services.device.load().ui_language == "en", timeout=TIMEOUT_MS
    )


def test_the_login_uses_the_device_theme_and_language(
    controllers: list[AppController], rig: Rig
) -> None:
    rig.services.device.save(DeviceSettings("dark", "en"))
    controller = start(controllers, rig)
    assert controller.login_window is not None
    page = controller.login_window.view.sign_in_page
    assert page.primary.text() == tr("auth.sign_in_button", Language.EN)
    assert "#392F5A" in controller.login_window.styleSheet()  # the dark bg token


# ---- sign out, delete, revocation ------------------------------------------


def open_sign_out(controller: AppController) -> None:
    window = main_window(controller)
    card = window.settings_view.account_card
    assert card is not None
    card.sign_out_button.click()
    box = window.settings_view.dialog
    assert isinstance(box, QMessageBox)
    press(box, tr("account.sign_out", Language.ES))


def test_sign_out_returns_to_the_login_and_keeps_the_profile_data(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    window = main_window(controller)
    open_sign_out(controller)
    qtbot.waitUntil(lambda: controller.window is None, timeout=TIMEOUT_MS)
    assert controller.login_window is not None
    assert controller.login_window.isVisible()
    assert not window.isVisible()
    assert rig.store.load() is None
    assert rig.services.session.identity is None
    assert profile_dir(rig).is_dir()


def test_sign_out_pushes_pending_changes_first_when_online(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    pushes = rig.server.count("PUT /v1/profile")
    assert controller.sync is not None
    controller.sync.suspend()  # keep the change pending until the sign out asks for it
    main_window(controller).settings_view.theme_buttons["dark"].setChecked(True)
    controller.sync.resume()
    open_sign_out(controller)
    qtbot.waitUntil(lambda: controller.window is None, timeout=TIMEOUT_MS)
    assert rig.server.count("PUT /v1/profile") == pushes + 1


def test_sign_out_offline_does_not_wait_for_the_network(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    rig.network.set_reachability(DISCONNECTED)
    controller = start(controllers, rig)
    open_sign_out(controller)
    qtbot.waitUntil(lambda: controller.window is None, timeout=TIMEOUT_MS)
    assert controller.login_window is not None
    assert "PUT /v1/profile" not in rig.server.calls


def test_a_new_person_after_sign_out_starts_with_an_empty_profile(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    main_window(controller)._on_word_explained("casa", "Un lugar.")
    open_sign_out(controller)
    qtbot.waitUntil(lambda: controller.window is None, timeout=TIMEOUT_MS)
    rig.server.session_fields = {"uid": "other9", "email": "otra@example.com"}
    rig.server.profile = None
    sign_in_through_the_login(qtbot, controller)
    window = main_window(controller)
    assert window._glossary.entries() == []
    assert (rig.services.data_dir / "profiles" / "other9").is_dir()
    assert (profile_dir(rig) / "glossary.json").exists()


def test_delete_removes_the_account_and_the_profile_folder(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    window = main_window(controller)
    (profile_dir(rig) / "marker.txt").write_text("x", encoding="utf-8")
    card = window.settings_view.account_card
    assert card is not None
    card.delete_button.click()
    dialog = card.delete_dialog
    assert dialog is not None
    dialog.password_edit.setText("secret-pass")
    dialog.delete_button.click()
    qtbot.waitUntil(lambda: controller.window is None, timeout=TIMEOUT_MS)
    assert "DELETE /v1/account" in rig.server.calls
    assert not profile_dir(rig).exists()
    assert rig.store.load() is None
    assert controller.login_window is not None
    assert tr("account.deleted", Language.ES) in login_messages(controller)


def test_a_failed_delete_keeps_everything_and_shows_the_error(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    rig.server.errors["DELETE /v1/account"] = (502, "auth_upstream_error")
    window = main_window(controller)
    card = window.settings_view.account_card
    assert card is not None
    card.delete_button.click()
    dialog = card.delete_dialog
    assert dialog is not None
    dialog.password_edit.setText("secret-pass")
    dialog.delete_button.click()
    expected = tr("auth.error.service_unavailable", Language.ES)
    qtbot.waitUntil(lambda: card.error_message.text == expected, timeout=TIMEOUT_MS)
    assert controller.window is window
    assert profile_dir(rig).is_dir()
    assert card.delete_button.isEnabled()
    assert rig.store.load() is not None


def test_the_assistant_asking_to_sign_in_checks_the_session(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    refreshes = rig.server.count("POST /v1/auth/refresh")
    window = main_window(controller)
    window.session_check_requested.emit()
    qtbot.waitUntil(
        lambda: rig.server.count("POST /v1/auth/refresh") == refreshes + 1,
        timeout=TIMEOUT_MS,
    )
    qtbot.wait(100)
    assert controller.window is window  # the session is fine: stay signed in


def test_the_assistant_finding_the_session_revoked_returns_to_the_login(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    rig.server.errors["POST /v1/auth/refresh"] = (401, "session_revoked")
    main_window(controller).session_check_requested.emit()
    qtbot.waitUntil(lambda: controller.window is None, timeout=TIMEOUT_MS)
    assert controller.login_window is not None
    assert rig.store.load() is None


def test_ending_the_session_twice_is_harmless(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    controller._on_session_ended()
    controller._on_session_ended()
    assert controller.window is None
    assert controller.login_window is not None


# ---- language restart -------------------------------------------------------


def test_a_language_restart_keeps_the_session_and_reopens_signed_in(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    first = start(controllers, rig)
    wait_synced(qtbot, first)
    window = main_window(first)
    window._restart()
    assert first.restart_requested
    assert rig.store.load() is not None
    second = start(controllers, rig)
    assert second.login_window is None
    assert second.window is not None
    assert second.window is not window
