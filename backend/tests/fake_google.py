"""A fake of Google's token endpoint and a controllable clock."""

from dataclasses import dataclass, field
from urllib.parse import parse_qs

import httpx

GOOGLE_CLIENT_ID = "fake-client-id.apps.googleusercontent.test"
GOOGLE_CLIENT_SECRET = "fake-google-client-secret"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass
class FakeGoogle:
    """Codes look like ``code-<who>`` and give the ID token ``<who>``; others fail."""

    requests: list[dict[str, str]] = field(default_factory=list)
    failure: httpx.Response | Exception | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.requests.append(form)
        if isinstance(self.failure, Exception):
            raise self.failure
        if self.failure is not None:
            return self.failure
        valid = (
            form["client_id"] == GOOGLE_CLIENT_ID
            and form["client_secret"] == GOOGLE_CLIENT_SECRET
            and form["grant_type"] == "authorization_code"
            and form["code"].startswith("code-")
        )
        if not valid:
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(
            200, json={"id_token": form["code"].removeprefix("code-")}
        )
