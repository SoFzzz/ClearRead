"""Profile payload, remote application and the last-writer-wins decision."""

from dataclasses import asdict
from pathlib import Path

import httpx
import pytest
from backend_fakes import make_account_client

from clearread.core.config import DEFAULT_BACKEND_URL, AppConfig
from clearread.services.account_client import RemoteProfile
from clearread.services.glossary import MAX_ENTRIES, GlossaryEntry, GlossaryStore
from clearread.services.groups import Group, GroupStore
from clearread.services.profile_sync import (
    MACHINE_SPECIFIC_FIELDS,
    SyncAction,
    SyncResult,
    SyncStateStore,
    apply_profile,
    apply_sync_result,
    build_profile,
    decide_sync,
    run_sync,
    utc_timestamp,
)

OLD = "2026-10-19T10:00:00Z"
NEW = "2026-10-19T11:00:00.500000Z"
ENTRY = GlossaryEntry("casa", "Lugar donde se vive.", "libro.pdf", "2026-10-01", "t1")


def remote(updated_at: str = NEW, **settings: object) -> RemoteProfile:
    return RemoteProfile(
        dict(settings), [asdict(ENTRY)], [{"id": "t1", "name": "Vida"}], updated_at
    )


def test_payload_leaves_out_machine_specific_fields() -> None:
    config = AppConfig(
        theme="dark", voice_id="sapi-voice", backend_url="https://x.test"
    )

    profile = build_profile(config, [ENTRY], [Group("t1", "Vida")], OLD)

    assert profile.settings["theme"] == "dark"
    for name in MACHINE_SPECIFIC_FIELDS:
        assert name not in profile.settings
    assert profile.words == [asdict(ENTRY)]
    assert profile.topics == [{"id": "t1", "name": "Vida"}]
    assert profile.updated_at == OLD


def test_apply_keeps_local_machine_fields_and_validates_the_rest(
    tmp_path: Path,
) -> None:
    local = AppConfig(voice_id="local-voice", backend_url="https://mine.test")
    incoming = remote(
        theme="dark",
        font_size_pt=999,
        reading_font="Comic",
        voice_id="other-voice",
        backend_url="https://evil.test",
        future_setting=True,
    )
    glossary, topics = (
        GlossaryStore(tmp_path / "g.json"),
        GroupStore(tmp_path / "t.json"),
    )

    config = apply_profile(incoming, local, glossary, topics)

    assert config.theme == "dark"
    assert config.font_size_pt == 28
    assert config.reading_font == "Lexend"
    assert config.voice_id == "local-voice"
    assert config.backend_url == "https://mine.test"


def test_apply_replaces_words_and_topics_and_persists_them(tmp_path: Path) -> None:
    glossary, topics = (
        GlossaryStore(tmp_path / "g.json"),
        GroupStore(tmp_path / "t.json"),
    )
    glossary.add(GlossaryEntry("viejo", "x", "d", "2026-01-01"))

    apply_profile(remote(), AppConfig(), glossary, topics)

    assert glossary.entries() == [ENTRY]
    assert topics.groups() == [Group("t1", "Vida")]
    assert GlossaryStore(tmp_path / "g.json").entries() == [ENTRY]
    assert GroupStore(tmp_path / "t.json").groups() == [Group("t1", "Vida")]


def test_apply_skips_malformed_items_and_ignores_unknown_keys() -> None:
    glossary, topics = GlossaryStore(), GroupStore()
    words: list[object] = [
        {**asdict(ENTRY), "extra": 1},
        {"word": 5},
        "text",
        {"word": "a", "explanation": "b", "document": "c", "added_on": "d", "topic": 3},
    ]
    groups: list[object] = [
        {"id": "g", "name": "N"},
        {"id": 1, "name": "N"},
        None,
        {"id": "", "name": "x"},
    ]
    profile = RemoteProfile({}, words, groups, NEW)  # type: ignore[arg-type]

    apply_profile(profile, AppConfig(), glossary, topics)

    assert glossary.entries() == [ENTRY]
    assert topics.groups() == [Group("g", "N")]


def test_apply_caps_the_word_list() -> None:
    word = {"word": "w", "explanation": "e", "document": "d", "added_on": "a"}
    glossary = GlossaryStore()

    apply_profile(
        RemoteProfile({}, [word] * (MAX_ENTRIES + 50), [], NEW),
        AppConfig(),
        glossary,
        GroupStore(),
    )

    assert len(glossary.entries()) == MAX_ENTRIES


@pytest.mark.parametrize(
    ("local", "remote_time", "action"),
    [
        (OLD, NEW, SyncAction.PULL),
        (NEW, OLD, SyncAction.PUSH),
        (OLD, OLD, SyncAction.NONE),
        ("", NEW, SyncAction.PULL),
        (OLD, "garbage", SyncAction.PUSH),
        ("2026-10-19T12:00:00+02:00", "2026-10-19T09:30:00Z", SyncAction.PUSH),
        ("2026-10-19T10:00:00", "2026-10-19T10:00:00Z", SyncAction.NONE),
    ],
)
def test_last_writer_wins_by_updated_at(
    local: str, remote_time: str, action: SyncAction
) -> None:
    assert decide_sync(local, remote(remote_time)) is action


def test_missing_remote_profile_means_push() -> None:
    assert decide_sync(OLD, None) is SyncAction.PUSH
    assert decide_sync("", None) is SyncAction.PUSH


def profile_response(profile: RemoteProfile) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "settings": profile.settings,
            "words": profile.words,
            "topics": profile.topics,
            "updated_at": profile.updated_at,
        },
    )


def local_profile(updated_at: str) -> RemoteProfile:
    return RemoteProfile({"theme": "light"}, [], [], updated_at)


def test_run_sync_pulls_a_newer_remote() -> None:
    client, backend = make_account_client(lambda r: profile_response(remote(NEW)))

    result = run_sync(client, "id", local_profile(OLD), "now")

    assert result.action is SyncAction.PULL
    assert result.profile is not None and result.profile.updated_at == NEW
    assert [r.method for r in backend.requests] == ["GET"]


def test_run_sync_pushes_a_newer_local_profile() -> None:
    client, backend = make_account_client(
        lambda r: (
            profile_response(remote(OLD))
            if r.method == "GET"
            else profile_response(local_profile(NEW))
        )
    )

    result = run_sync(client, "id", local_profile(NEW), "now")

    assert result.action is SyncAction.PUSH
    assert [r.method for r in backend.requests] == ["GET", "PUT"]
    assert backend.bodies()[1]["updated_at"] == NEW  # type: ignore[index]


def test_run_sync_first_upload_is_stamped_with_now() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404, json={"error": "profile_not_found"})
        return profile_response(local_profile("now"))

    client, backend = make_account_client(handler)

    result = run_sync(client, "id", local_profile(""), "now")

    assert result.action is SyncAction.PUSH
    assert backend.bodies()[1]["updated_at"] == "now"  # type: ignore[index]


def test_run_sync_equal_times_do_nothing() -> None:
    client, backend = make_account_client(lambda r: profile_response(remote(OLD)))

    assert run_sync(client, "id", local_profile(OLD), "now") == SyncResult(
        SyncAction.NONE, None
    )
    assert len(backend.requests) == 1


def test_sync_state_round_trip_and_damaged_file(tmp_path: Path) -> None:
    state = SyncStateStore(tmp_path)
    assert state.updated_at() == ""

    state.mark(OLD)
    assert state.updated_at() == OLD

    (tmp_path / "sync_state.json").write_text("{broken", encoding="utf-8")
    assert state.updated_at() == ""


def test_touch_stamps_a_parseable_utc_time(tmp_path: Path) -> None:
    state = SyncStateStore(tmp_path)

    stamped = state.touch()

    assert stamped == state.updated_at()
    assert stamped.endswith("Z")
    assert decide_sync(OLD, remote(stamped)) is SyncAction.PULL


def test_utc_timestamp_format() -> None:
    assert utc_timestamp().endswith("Z")


def test_apply_sync_result_pull_applies_and_marks(tmp_path: Path) -> None:
    state = SyncStateStore(tmp_path)
    glossary, topics = GlossaryStore(), GroupStore()
    result = SyncResult(SyncAction.PULL, remote(NEW, theme="dark"))

    config = apply_sync_result(result, state, AppConfig(), glossary, topics)

    assert config.theme == "dark"
    assert glossary.entries() == [ENTRY]
    assert state.updated_at() == NEW


def test_apply_sync_result_push_only_marks(tmp_path: Path) -> None:
    state = SyncStateStore(tmp_path)
    glossary = GlossaryStore()
    original = AppConfig(theme="dark")

    config = apply_sync_result(
        SyncResult(SyncAction.PUSH, remote(NEW)),
        state,
        original,
        glossary,
        GroupStore(),
    )

    assert config is original
    assert glossary.entries() == []
    assert state.updated_at() == NEW


def test_apply_sync_result_none_changes_nothing(tmp_path: Path) -> None:
    state = SyncStateStore(tmp_path)
    original = AppConfig()

    config = apply_sync_result(
        SyncResult(SyncAction.NONE, None),
        state,
        original,
        GlossaryStore(),
        GroupStore(),
    )

    assert config is original
    assert state.updated_at() == ""


def test_default_backend_url_constant_is_untouched_by_apply() -> None:
    config = apply_profile(
        remote(backend_url="https://evil.test"),
        AppConfig(),
        GlossaryStore(),
        GroupStore(),
    )

    assert config.backend_url == DEFAULT_BACKEND_URL
