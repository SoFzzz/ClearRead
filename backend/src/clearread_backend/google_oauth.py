"""Google OAuth 2.0 (web server flow with PKCE); only the backend knows these URLs."""

import logging
from urllib.parse import urlencode

import httpx

from clearread_backend.errors import ApiError
from clearread_backend.firebase import json_object, send_request

AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "openid email profile"

logger = logging.getLogger("clearread_backend")


class GoogleOAuthGateway:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._transport = transport

    def authorization_url(
        self, redirect_uri: str, state: str, code_challenge: str
    ) -> str:
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": SCOPE,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )
        return f"{AUTHORIZATION_URL}?{query}"

    async def exchange_code(
        self, code: str, code_verifier: str, redirect_uri: str
    ) -> str:
        """Trade the code for Google's ID token; neither is stored."""
        response = await send_request(
            self._transport,
            "POST",
            TOKEN_URL,
            data={
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if not response.is_success:
            # invalid_grant and redirect_uri_mismatch end here; the body is not read.
            logger.warning("google failure: auth_upstream_error")
            raise ApiError(502, "auth_upstream_error")
        id_token = json_object(response).get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise ApiError(502, "auth_upstream_error")
        return id_token
