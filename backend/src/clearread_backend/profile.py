"""Endpoints of the synced profile (settings, "Mis palabras" and topics)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from clearread_backend.accounts import CurrentPrincipal
from clearread_backend.errors import ApiError
from clearread_backend.firebase import FirestoreGateway
from clearread_backend.models import Profile
from clearread_backend.sessions import Principal

PROFILE_MAX_BYTES = 900_000
PROFILE_MAX_WORDS = 2000


def check_profile_size(profile: Profile) -> None:
    too_many_words = len(profile.words) > PROFILE_MAX_WORDS
    too_big = len(profile.model_dump_json().encode()) > PROFILE_MAX_BYTES
    if too_many_words or too_big:
        raise ApiError(413, "profile_too_large")


def create_profile_router(
    firestore: FirestoreGateway, current_principal: CurrentPrincipal
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/profile")
    async def get_profile(
        principal: Annotated[Principal, Depends(current_principal)],
    ) -> Profile:
        return await firestore.get_profile(principal.info.uid, principal.id_token)

    @router.put("/v1/profile")
    async def put_profile(
        body: Profile, principal: Annotated[Principal, Depends(current_principal)]
    ) -> Profile:
        check_profile_size(body)
        await firestore.put_profile(principal.info.uid, principal.id_token, body)
        return body

    return router
