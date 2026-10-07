"""Call to DeepSeek's chat completions API and translation of its failures."""

import re
from collections import OrderedDict

import httpx

TIMEOUT_S = 20.0
CACHE_MAX_ENTRIES = 500
_SENTENCE_END = re.compile(r"[.!?…]+[\"'”’»)\]]*")


class UpstreamError(Exception):
    """A DeepSeek failure as a stable code of ours; never carries upstream text."""

    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code


def trim_to_last_sentence(text: str) -> str:
    """Cut a reply that hit the token limit after its last complete sentence."""
    ends = list(_SENTENCE_END.finditer(text))
    return text[: ends[-1].end()] if ends else text


class ResponseCache:
    """Bounded in-memory cache; the oldest entry is dropped first."""

    def __init__(self, max_entries: int = CACHE_MAX_ENTRIES) -> None:
        self._max_entries = max_entries
        self._entries: OrderedDict[tuple[str, str], str] = OrderedDict()

    def get(self, key: tuple[str, str]) -> str | None:
        return self._entries.get(key)

    def put(self, key: tuple[str, str], text: str) -> None:
        self._entries[key] = text
        if len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)


class DeepSeekGateway:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._transport = transport

    async def complete(
        self, system_prompt: str, user_prompt: str, max_tokens: int
    ) -> str:
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "stream": False,
            # On by default, its reasoning tokens would use up max_tokens (real check).
            "thinking": {"type": "disabled"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT_S, transport=self._transport
            ) as client:
                response = await client.post(self._url, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise UpstreamError(504, "upstream_timeout") from None
        except httpx.HTTPError:
            raise UpstreamError(502, "upstream_bad_response") from None
        return self._text_of(response)

    @staticmethod
    def _text_of(response: httpx.Response) -> str:
        if response.status_code == 401:
            raise UpstreamError(502, "upstream_auth_failed")
        if response.status_code == 402:
            raise UpstreamError(502, "upstream_no_balance")
        if response.status_code != 200:
            raise UpstreamError(502, "upstream_bad_response")
        try:
            choice = response.json()["choices"][0]
            text = choice["message"]["content"]
            finish_reason = choice.get("finish_reason")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise UpstreamError(502, "upstream_bad_response") from None
        if not isinstance(text, str):
            raise UpstreamError(502, "upstream_bad_response")
        if finish_reason == "length":
            text = trim_to_last_sentence(text)
        if not text.strip():
            raise UpstreamError(502, "upstream_bad_response")
        return text.strip()
