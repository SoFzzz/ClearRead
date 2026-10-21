"""Sign out and delete account through the real controller, client and transport.

Only the HTTP server is a double (``FakeAccountServer`` behind ``httpx.MockTransport``);
the profile folders are real folders in a temporary directory.
"""

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from app_fakes import UID, Rig, make_rig, save_session
from PySide6.QtWidgets import QLabel, QMessageBox
from pytestqt.qtbot import QtBot

from clearread.services.session_manager import SessionManager
from clearread.services.session_store import SessionStore
from clearread.ui.app_controller import AppController, remove_profile_folder
from clearread.ui.fonts import load_reading_font
from clearread.ui.main_window import MainWindow
from clearread.ui.strings import Language, tr
from clearread.ui.views.login_widgets import InlineMessage

TIMEOUT_MS = 8000
OTHER_UID = "other9"


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


def profile_path(rig: Rig, uid: str) -> Path:
    """Where a profile lives; unlike ``profile_dir_for`` it never creates it."""
    return rig.services.data_dir / "profiles" / uid


def main_window(controller: AppController) -> MainWindow:
    assert controller.window is not None
    return controller.window


def press(box: QMessageBox, text: str) -> None:
    next(b for b in box.buttons() if b.text() == text).click()


def wait_synced(qtbot: QtBot, controller: AppController) -> None:
    assert controller.sync is not None
    sync = controller.sync
    qtbot.waitUntil(lambda: not sync.has_unsaved_changes, timeout=TIMEOUT_MS)


def confirm_from_settings(controller: AppController, which: str, answer: str) -> None:
    window = main_window(controller)
    card = window.settings_view.account_card
    assert card is not None
    getattr(card, which).click()
    box = window.settings_view.dialog
    assert isinstance(box, QMessageBox)
    press(box, answer)


def delete_account(controller: AppController, password: str = "secret-pass") -> None:
    window = main_window(controller)
    card = window.settings_view.account_card
    assert card is not None
    card.delete_button.click()
    dialog = card.delete_dialog
    assert dialog is not None
    dialog.password_edit.setText(password)
    dialog.delete_button.click()


def sign_in_as(qtbot: QtBot, controller: AppController, rig: Rig, uid: str) -> None:
    rig.server.session_fields = {"uid": uid, "email": f"{uid}@example.com"}
    rig.server.profile = None
    assert controller.login_window is not None
    page = controller.login_window.view.sign_in_page
    page.email.edit.setText(f"{uid}@example.com")
    page.password.edit.setText("secret-pass")
    page.primary.click()
    qtbot.waitUntil(lambda: controller.window is not None, timeout=TIMEOUT_MS)


def login_messages(controller: AppController) -> list[str]:
    assert controller.login_window is not None
    view = controller.login_window.view
    return [m.text for m in view.sign_in_page.findChildren(InlineMessage) if m.text]


# ---- 3: sign out shows only its own text ------------------------------------


def test_signing_out_never_says_deleting(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    gate = threading.Event()
    rig.server.gates["PUT /v1/profile"] = gate  # keeps the sign out waiting a moment
    window = main_window(controller)
    window.settings_view.theme_buttons["dark"].setChecked(True)
    confirm_from_settings(
        controller, "sign_out_button", tr("account.sign_out", Language.ES)
    )
    card = window.settings_view.account_card
    assert card is not None
    assert controller.window is window  # still waiting for the profile to upload
    assert not card.busy_label.isHidden()
    assert card.busy_label.text() == tr("account.signing_out", Language.ES)
    shown = [
        label.text() for label in card.findChildren(QLabel) if not label.isHidden()
    ]
    assert tr("account.deleting", Language.ES) not in shown
    gate.set()
    qtbot.waitUntil(lambda: controller.window is None, timeout=TIMEOUT_MS)
    assert "DELETE /v1/account" not in rig.server.calls


def test_deleting_says_deleting(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    gate = threading.Event()
    rig.server.gates["DELETE /v1/account"] = gate
    card = main_window(controller).settings_view.account_card
    assert card is not None
    delete_account(controller)
    assert not card.busy_label.isHidden()
    assert card.busy_label.text() == tr("account.deleting", Language.ES)
    gate.set()
    qtbot.waitUntil(lambda: controller.window is None, timeout=TIMEOUT_MS)


# ---- 4: the whole delete flow -----------------------------------------------


def test_delete_goes_through_every_step_and_leaves_the_other_profile_alone(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    other = profile_path(rig, OTHER_UID)
    other.mkdir(parents=True)
    (other / "glossary.json").write_text("[]", encoding="utf-8")
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    mine = profile_path(rig, UID)
    (mine / "cache").mkdir(exist_ok=True)
    (mine / "cache" / "page.txt").write_text("x", encoding="utf-8")

    delete_account(controller)
    qtbot.waitUntil(lambda: controller.window is None, timeout=TIMEOUT_MS)

    assert rig.server.calls.count("DELETE /v1/account") == 1
    assert rig.server.authorizations["DELETE /v1/account"] == "Bearer id-1"
    assert rig.server.delete_passwords == ["secret-pass"]
    assert not mine.exists()
    assert (other / "glossary.json").read_text(encoding="utf-8") == "[]"
    assert rig.store.load() is None
    assert rig.services.session.identity is None
    login = controller.login_window
    assert login is not None
    assert login.isVisible()
    assert tr("account.deleted", Language.ES) in login_messages(controller)
    qtbot.wait(300)  # nothing from the closed window may bring the folder back
    assert not mine.exists()


def test_a_wrong_password_deletes_nothing_and_keeps_the_dialog_open(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    window = main_window(controller)
    mine = profile_path(rig, UID)
    delete_account(controller, "not-my-password")
    card = window.settings_view.account_card
    assert card is not None
    dialog = card.delete_dialog
    assert dialog is not None
    expected = tr("account.delete_wrong_password", Language.ES)
    qtbot.waitUntil(lambda: dialog.wrong_password_text == expected, timeout=TIMEOUT_MS)
    assert dialog.isVisible()
    assert dialog.password_edit.isEnabled()
    assert dialog.password_edit.text() == ""
    assert not dialog.delete_button.isEnabled()
    assert controller.window is window
    assert mine.is_dir()
    assert rig.store.load() is not None
    assert card.delete_button.isEnabled()
    assert card.error_message.isHidden()

    dialog.password_edit.setText("secret-pass")
    dialog.delete_button.click()
    qtbot.waitUntil(lambda: controller.window is None, timeout=TIMEOUT_MS)
    assert rig.server.delete_passwords == ["not-my-password", "secret-pass"]
    assert not mine.exists()


def test_another_failure_while_deleting_closes_the_dialog_and_shows_the_error(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    rig.server.errors["DELETE /v1/account"] = (429, "too_many_attempts")
    card = main_window(controller).settings_view.account_card
    assert card is not None
    delete_account(controller)
    expected = tr("auth.error.too_many_attempts", Language.ES)
    qtbot.waitUntil(lambda: card.error_message.text == expected, timeout=TIMEOUT_MS)
    qtbot.waitUntil(lambda: card.delete_dialog is None, timeout=TIMEOUT_MS)
    assert profile_path(rig, UID).is_dir()


def test_deleting_the_second_profile_leaves_the_first_gone_and_nothing_else(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    delete_account(controller)
    qtbot.waitUntil(lambda: controller.window is None, timeout=TIMEOUT_MS)

    sign_in_as(qtbot, controller, rig, OTHER_UID)
    wait_synced(qtbot, controller)
    assert profile_path(rig, OTHER_UID).is_dir()
    delete_account(controller)
    qtbot.waitUntil(lambda: controller.window is None, timeout=TIMEOUT_MS)

    assert not profile_path(rig, OTHER_UID).exists()
    assert not profile_path(rig, UID).exists()
    assert (rig.services.data_dir / "profiles").is_dir()
    assert controller.login_window is not None


def test_signing_out_keeps_both_profiles(
    qtbot: QtBot, controllers: list[AppController], rig: Rig
) -> None:
    other = profile_path(rig, OTHER_UID)
    other.mkdir(parents=True)
    save_session(rig.store)
    controller = start(controllers, rig)
    wait_synced(qtbot, controller)
    confirm_from_settings(
        controller, "sign_out_button", tr("account.sign_out", Language.ES)
    )
    qtbot.waitUntil(lambda: controller.window is None, timeout=TIMEOUT_MS)
    assert profile_path(rig, UID).is_dir()
    assert other.is_dir()


def test_sign_out_survives_a_locked_session_file(tmp_path: Path, rig: Rig) -> None:
    class LockedStore(SessionStore):
        def clear(self) -> None:
            raise PermissionError("locked")

    store = LockedStore(tmp_path / "x.bin", lambda d: d, lambda d: d)
    manager = SessionManager(rig.services.client, store)
    manager.sign_out()
    assert manager.identity is None


# ---- folder removal ---------------------------------------------------------


def test_remove_profile_folder_deletes_read_only_files(tmp_path: Path) -> None:
    folder = tmp_path / "profiles" / "abc"
    (folder / "cache").mkdir(parents=True)
    locked = folder / "cache" / "readonly.txt"
    locked.write_text("x", encoding="utf-8")
    locked.chmod(0o444)
    sibling = tmp_path / "profiles" / "keep"
    sibling.mkdir()
    remove_profile_folder(folder)
    assert not folder.exists()
    assert sibling.is_dir()
