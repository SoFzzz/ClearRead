"""ClearRead backend: proxies AI requests to DeepSeek with cost guards.

Never logs request or response texts (BE-F03): only our own error codes are logged.
"""

import logging
import secrets
from typing import Literal

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from clearread_backend.deepseek import DeepSeekGateway, ResponseCache, UpstreamError
from clearread_backend.prompts import (
    EXPLAIN_SYSTEM_PROMPTS,
    EXPLAIN_USER_TEMPLATES,
    SIMPLIFY_SYSTEM_PROMPTS,
)
from clearread_backend.quota import DailyQuota
from clearread_backend.settings import Settings, load_env_file

WORD_MAX_CHARS = 40
CONTEXT_MAX_CHARS = 300
TEXT_MAX_CHARS = 1500
EXPLAIN_MAX_TOKENS = 80
SIMPLIFY_MAX_TOKENS = 250

logger = logging.getLogger("clearread_backend")


class ApiError(Exception):
    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code


class _Request(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class ExplainRequest(_Request):
    word: str = Field(min_length=1, max_length=WORD_MAX_CHARS)
    context_sentence: str = Field(min_length=1, max_length=CONTEXT_MAX_CHARS)
    lang: Literal["es", "en"]


class SimplifyRequest(_Request):
    text: str = Field(min_length=1, max_length=TEXT_MAX_CHARS)
    lang: Literal["es", "en"]


class AIText(BaseModel):
    text: str


def _error_response(status_code: int, code: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": code})


def create_app(
    settings: Settings | None = None, gateway: DeepSeekGateway | None = None
) -> FastAPI:
    settings = settings or Settings.from_env()
    gateway = gateway or DeepSeekGateway(
        settings.deepseek_api_key,
        settings.deepseek_model,
        settings.deepseek_base_url,
    )
    quota = DailyQuota(settings.daily_call_limit)
    cache = ResponseCache()
    app = FastAPI(title="ClearRead API", version="1.5.0")

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Over-length input is 413 (BE-F02); any other defect is a malformed request.
        if all(err["type"] == "string_too_long" for err in exc.errors()):
            return _error_response(413, "input_too_long")
        return _error_response(422, "invalid_request")

    def require_client_token(x_client_token: str = Header(default="")) -> None:
        expected = settings.client_token
        if not expected or not secrets.compare_digest(
            x_client_token.encode(), expected.encode()
        ):
            raise ApiError(401, "invalid_client_token")

    async def complete(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        key = (system_prompt, " ".join(user_prompt.lower().split()))
        cached = cache.get(key)
        if cached is not None:
            return cached
        # Reserved before awaiting: asyncio cannot interleave check and increment.
        if not quota.try_consume():
            raise ApiError(429, "daily_limit_reached")
        try:
            text = await gateway.complete(system_prompt, user_prompt, max_tokens)
        except UpstreamError as exc:
            logger.warning("upstream failure: %s", exc.code)
            raise ApiError(exc.status_code, exc.code) from None
        cache.put(key, text)
        return text

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/explain", dependencies=[Depends(require_client_token)])
    async def explain(body: ExplainRequest) -> AIText:
        user_prompt = EXPLAIN_USER_TEMPLATES[body.lang].format(
            word=body.word, context=body.context_sentence
        )
        text = await complete(
            EXPLAIN_SYSTEM_PROMPTS[body.lang], user_prompt, EXPLAIN_MAX_TOKENS
        )
        return AIText(text=text)

    @app.post("/v1/simplify", dependencies=[Depends(require_client_token)])
    async def simplify(body: SimplifyRequest) -> AIText:
        text = await complete(
            SIMPLIFY_SYSTEM_PROMPTS[body.lang], body.text, SIMPLIFY_MAX_TOKENS
        )
        return AIText(text=text)

    return app


def _create_default_app() -> FastAPI:
    load_env_file()
    return create_app()


app = _create_default_app()
