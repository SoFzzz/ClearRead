"""Operating-system reachability without network traffic (AI-F03)."""

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QNetworkInformation

_OFFLINE = (
    QNetworkInformation.Reachability.Disconnected,
    QNetworkInformation.Reachability.Local,
)


class NetworkMonitor(QObject):
    online_changed = Signal(bool)

    def __init__(
        self,
        information: QNetworkInformation | None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._online = True
        if information is not None:
            self.set_reachability(information.reachability())
            information.reachabilityChanged.connect(self.set_reachability)

    @classmethod
    def from_system(cls, parent: QObject | None = None) -> "NetworkMonitor":
        """Use the OS backend, or behave as always online when there is none."""
        available = QNetworkInformation.loadDefaultBackend()
        return cls(QNetworkInformation.instance() if available else None, parent)

    @property
    def is_online(self) -> bool:
        return self._online

    def set_reachability(self, reachability: QNetworkInformation.Reachability) -> None:
        # Unknown counts as online: the first failed call reports the problem instead.
        online = reachability not in _OFFLINE
        if online != self._online:
            self._online = online
            self.online_changed.emit(online)
