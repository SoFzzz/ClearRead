"""ClearRead backend: accounts and synced profile (Firebase) and the AI proxy.

Composition root. Never logs request or response texts, emails, passwords, tokens or
profile contents (BE-F03): only our own error codes are logged.
"""

import logging
import secrets
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from clearread_backend.accounts import create_accounts_router
from clearread_backend.deepseek import DeepSeekGateway, ResponseCache, UpstreamError
from clearread_backend.errors import ApiError
from clearread_backend.firebase import FirebaseAuthGateway, FirestoreGateway
from clearread_backend.google_auth import (
    GoogleAttemptStore,
    RedactGoogleAccessLog,
    create_google_router,
)
from clearread_backend.google_oauth import GoogleOAuthGateway
from clearread_backend.profile import create_profile_router
from clearread_backend.prompts import (
    EXPLAIN_SYSTEM_PROMPTS,
    EXPLAIN_USER_TEMPLATES,
    SIMPLIFY_SYSTEM_PROMPTS,
)
from clearread_backend.quota import DailyQuota
from clearread_backend.sessions import Principal, TokenVerifier, bearer_token
from clearread_backend.settings import Settings, load_env_file

WORD_MAX_CHARS = 40
CONTEXT_MAX_CHARS = 300
TEXT_MAX_CHARS = 1500
EXPLAIN_MAX_TOKENS = 80
SIMPLIFY_MAX_TOKENS = 250

logger = logging.getLogger("clearread_backend")


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
    settings: Settings | None = None,
    gateway: DeepSeekGateway | None = None,
    auth: FirebaseAuthGateway | None = None,
    firestore: FirestoreGateway | None = None,
    google: GoogleOAuthGateway | None = None,
    attempts: GoogleAttemptStore | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    gateway = gateway or DeepSeekGateway(
        settings.deepseek_api_key,
        settings.deepseek_model,
        settings.deepseek_base_url,
    )
    auth = auth or FirebaseAuthGateway(settings.firebase_api_key)
    firestore = firestore or FirestoreGateway(settings.firebase_project_id)
    google = google or GoogleOAuthGateway(
        settings.google_client_id, settings.google_client_secret
    )
    attempts = attempts or GoogleAttemptStore()
    verifier = TokenVerifier(auth)
    quota = DailyQuota(settings.daily_call_limit)
    user_quota = DailyQuota(settings.user_daily_call_limit)
    cache = ResponseCache()
    app = FastAPI(title="ClearRead API", version="1.7.0")

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

    def require_auth_configured() -> None:
        if not settings.auth_configured:
            raise ApiError(503, "auth_not_configured")

    def require_google_configured() -> None:
        require_auth_configured()
        if not settings.google_configured:
            raise ApiError(503, "google_not_configured")

    async def current_principal(
        authorization: str = Header(default=""),
        _: None = Depends(require_auth_configured),
    ) -> Principal:
        token = bearer_token(authorization)
        return Principal(await verifier.verify(token), token)

    async def complete(
        uid: str, system_prompt: str, user_prompt: str, max_tokens: int
    ) -> str:
        key = (system_prompt, " ".join(user_prompt.lower().split()))
        cached = cache.get(key)
        if cached is not None:
            return cached
        # Reserved before awaiting: asyncio cannot interleave check and increment.
        if not user_quota.try_consume(uid):
            raise ApiError(429, "user_daily_limit_reached")
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
    async def explain(
        body: ExplainRequest,
        principal: Annotated[Principal, Depends(current_principal)],
    ) -> AIText:
        user_prompt = EXPLAIN_USER_TEMPLATES[body.lang].format(
            word=body.word, context=body.context_sentence
        )
        text = await complete(
            principal.info.uid,
            EXPLAIN_SYSTEM_PROMPTS[body.lang],
            user_prompt,
            EXPLAIN_MAX_TOKENS,
        )
        return AIText(text=text)

    @app.post("/v1/simplify", dependencies=[Depends(require_client_token)])
    async def simplify(
        body: SimplifyRequest,
        principal: Annotated[Principal, Depends(current_principal)],
    ) -> AIText:
        text = await complete(
            principal.info.uid,
            SIMPLIFY_SYSTEM_PROMPTS[body.lang],
            body.text,
            SIMPLIFY_MAX_TOKENS,
        )
        return AIText(text=text)

    app.include_router(
        create_accounts_router(
            auth, firestore, verifier, require_auth_configured, current_principal
        )
    )
    app.include_router(
        create_google_router(
            auth,
            firestore,
            google,
            attempts,
            verifier,
            settings.google_redirect_uri,
            require_google_configured,
        )
    )
    app.include_router(create_profile_router(firestore, current_principal))
    return app


def _create_default_app() -> FastAPI:
    load_env_file()
    # The access log would print attempt ids, codes and states from the Google routes.
    logging.getLogger("uvicorn.access").addFilter(RedactGoogleAccessLog())
    return create_app()


app = _create_default_app()
