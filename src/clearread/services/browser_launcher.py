"""Opens the system browser on a page of our own backend (v1.7, design doc 4.14.11).

This is the only module that may import QDesktopServices. It refuses every address that
is not under the configured backend URL, so the app can never send a person to another
site by accident.
"""

from collections.abc import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


class BrowserLauncher:
    def __init__(
        self,
        backend_url: str,
        open_url: Callable[[QUrl], bool] = QDesktopServices.openUrl,
    ) -> None:
        self._backend_url = backend_url.rstrip("/")
        self._open_url = open_url

    def open_backend_page(self, path: str) -> bool:
        """Open ``backend_url + path``; False when refused or the system cannot open it."""
        if not _is_plain_path(path):
            return False
        address = f"{self._backend_url}{path}"
        url = QUrl(address, QUrl.ParsingMode.StrictMode)
        backend = QUrl(self._backend_url)
        if not url.isValid() or not _same_origin(url, backend):
            return False
        return self._open_url(url)


def _is_plain_path(path: str) -> bool:
    """An absolute path on the same host: no scheme-relative form, no way back up."""
    if not path.startswith("/") or path.startswith("//") or "\\" in path:
        return False
    decoded = QUrl.fromPercentEncoding(path.encode("utf-8"))
    return ".." not in decoded.split("/") and "\\" not in decoded


def _same_origin(url: QUrl, backend: QUrl) -> bool:
    return (
        url.scheme().lower() == backend.scheme().lower()
        and url.host().lower() == backend.host().lower()
        and url.port() == backend.port()
        and url.userInfo() == ""
    )
