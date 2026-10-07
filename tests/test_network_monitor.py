"""NetworkMonitor: OS reachability turned into online/offline, with fallback (AI-F03)."""

import pytest
from PySide6.QtNetwork import QNetworkInformation
from pytestqt.qtbot import QtBot

from clearread.services.network_monitor import NetworkMonitor

Reachability = QNetworkInformation.Reachability


def test_without_backend_it_stays_online() -> None:
    assert NetworkMonitor(None).is_online


@pytest.mark.parametrize(
    ("reachability", "online"),
    [
        (Reachability.Online, True),
        (Reachability.Site, True),
        (Reachability.Unknown, True),
        (Reachability.Local, False),
        (Reachability.Disconnected, False),
    ],
)
def test_reachability_to_online(
    qtbot: QtBot, reachability: Reachability, online: bool
) -> None:
    monitor = NetworkMonitor(None)

    monitor.set_reachability(reachability)

    assert monitor.is_online is online


def test_signal_only_on_change(qtbot: QtBot) -> None:
    monitor = NetworkMonitor(None)
    changes: list[bool] = []
    monitor.online_changed.connect(changes.append)

    monitor.set_reachability(Reachability.Online)
    monitor.set_reachability(Reachability.Disconnected)
    monitor.set_reachability(Reachability.Disconnected)
    monitor.set_reachability(Reachability.Online)

    assert changes == [False, True]


def test_from_system_never_fails(qtbot: QtBot) -> None:
    monitor = NetworkMonitor.from_system()
    assert isinstance(monitor.is_online, bool)
