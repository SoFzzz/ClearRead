"""Endpoints to register, sign in, refresh, reset a password and delete an account."""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from clearread_backend.errors import ApiError
from clearread_backend.firebase import FirebaseAuthGateway, FirestoreGateway, Tokens
from clearread_backend.models import (
    PASSWORD_MIN_CHARS,
    LoginRequest,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    SessionResponse,
)
from clearread_backend.sessions import Principal, TokenVerifier, session_response

logger = logging.getLogger("clearread_backend")

CurrentPrincipal = Callable[..., Awaitable[Principal]]


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    first_hop = forwarded.split(",")[0].strip()
    if first_hop:
        return first_hop
    return request.client.host if request.client else ""


def create_accounts_router(
    auth: FirebaseAuthGateway,
    firestore: FirestoreGateway,
    verifier: TokenVerifier,
    require_configured: Callable[[], None],
    current_principal: CurrentPrincipal,
) -> APIRouter:
    router = APIRouter(dependencies=[Depends(require_configured)])

    async def session_for(tokens: Tokens) -> SessionResponse:
        return await session_response(verifier, tokens)

    async def send_verification_best_effort(id_token: str) -> None:
        # Verifying the email is not required to sign in, so a failure is not fatal.
        try:
            await auth.send_verification_email(id_token)
        except ApiError as exc:
            logger.warning("verification email not sent: %s", exc.code)

    async def name_best_effort(created: Tokens, display_name: str) -> Tokens:
        # The account already exists: failing here would block a retry (email_exists).
        try:
            return await auth.set_display_name(created.id_token, display_name)
        except ApiError as exc:
            logger.warning("display name not set: %s", exc.code)
            return created

    @router.post("/v1/auth/register", status_code=201)
    async def register(body: RegisterRequest) -> SessionResponse:
        if len(body.password) < PASSWORD_MIN_CHARS:
            raise ApiError(422, "password_too_short")
        created = await auth.sign_up(body.email, body.password)
        named = await name_best_effort(created, body.display_name)
        await send_verification_best_effort(named.id_token)
        return await session_for(named)

    @router.post("/v1/auth/login")
    async def login(body: LoginRequest) -> SessionResponse:
        return await session_for(await auth.sign_in(body.email, body.password))

    @router.post("/v1/auth/refresh")
    async def refresh(body: RefreshRequest) -> SessionResponse:
        return await session_for(await auth.refresh(body.refresh_token))

    @router.post("/v1/auth/password-reset", status_code=204)
    async def password_reset(body: PasswordResetRequest, request: Request) -> Response:
        await auth.send_password_reset(body.email, client_ip(request))
        return Response(status_code=204)

    @router.delete("/v1/account", status_code=204)
    async def delete_account(
        principal: Annotated[Principal, Depends(current_principal)],
    ) -> Response:
        await firestore.delete_profile(principal.info.uid, principal.id_token)
        await auth.delete_user(principal.id_token)
        verifier.forget(principal.id_token)
        return Response(status_code=204)

    return router
