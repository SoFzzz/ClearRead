"""BrowserLauncher: opens our backend's pages and refuses anything else."""

import pytest
from PySide6.QtCore import QUrl

from clearread.core.config import BACKEND_URL_ENV_VAR, resolve_backend_url
from clearread.services.browser_launcher import BrowserLauncher

BACKEND = "https://backend.example.com"


class Recorder:
    def __init__(self, succeeds: bool = True) -> None:
        self.succeeds = succeeds
        self.urls: list[str] = []

    def __call__(self, url: QUrl) -> bool:
        self.urls.append(url.toString())
        return self.succeeds


def test_opens_a_page_under_the_backend_url() -> None:
    recorder = Recorder()
    launcher = BrowserLauncher(BACKEND, recorder)
    assert launcher.open_backend_page("/v1/auth/google/begin/abc_-123")
    assert recorder.urls == [f"{BACKEND}/v1/auth/google/begin/abc_-123"]


def test_a_trailing_slash_on_the_backend_url_is_ignored() -> None:
    recorder = Recorder()
    BrowserLauncher(BACKEND + "/", recorder).open_backend_page("/x")
    assert recorder.urls == [f"{BACKEND}/x"]


@pytest.mark.parametrize(
    "path",
    [
        "https://evil.example.com/x",
        "http://backend.example.com/x",
        "//evil.example.com/x",
        ".evil.com/x",
        "@evil.com/x",
        "v1/auth/google/begin/abc",
        "",
        "/../secret",
        "/a/../b",
        "/%2e%2e/secret",
        "/a%2F..%2Fb",
        "\\evil.com",
        "/a\\b",
    ],
)
def test_refuses_anything_that_is_not_a_plain_path_on_the_backend(path: str) -> None:
    recorder = Recorder()
    assert BrowserLauncher(BACKEND, recorder).open_backend_page(path) is False
    assert recorder.urls == []


def test_a_path_cannot_turn_the_backend_host_into_another_one() -> None:
    recorder = Recorder()
    launcher = BrowserLauncher("https://backend.example.com", recorder)
    assert launcher.open_backend_page(".evil.com/x") is False
    assert recorder.urls == []


def test_reports_false_when_the_system_cannot_open_it() -> None:
    launcher = BrowserLauncher(BACKEND, Recorder(succeeds=False))
    assert launcher.open_backend_page("/x") is False


def test_opens_a_page_under_an_overridden_local_backend_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(BACKEND_URL_ENV_VAR, "http://localhost:8000/")
    recorder = Recorder()
    launcher = BrowserLauncher(resolve_backend_url(), recorder)
    assert launcher.open_backend_page("/v1/auth/google/begin/abc")
    assert recorder.urls == ["http://localhost:8000/v1/auth/google/begin/abc"]
