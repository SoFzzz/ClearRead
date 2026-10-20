"""Synced profile: settings, "Mis palabras" and topics (v1.6).

Conflict rule: last writer wins on the whole profile, by ``updated_at``. Known
limitation: two computers edited offline at the same time keep only the newest save.
The functions here are pure or take their stores by argument; the network part runs in
a worker, and the result is applied on the main thread.
"""

import json
from dataclasses import asdict, fields
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, NamedTuple

from clearread.core.config import AppConfig
from clearread.services.account_client import AccountClient, RemoteProfile
from clearread.services.atomic_json import write_json_atomic
from clearread.services.glossary import MAX_ENTRIES, GlossaryEntry, GlossaryStore
from clearread.services.groups import MAX_GROUPS, Group, GroupStore

SYNC_STATE_FILE = "sync_state.json"
# Belong to this computer, not to the person: another PC has other voices and URLs.
MACHINE_SPECIFIC_FIELDS = ("backend_url", "voice_id")
_EPOCH = datetime.fromtimestamp(0, UTC)


class SyncAction(Enum):
    NONE = "none"
    PUSH = "push"
    PULL = "pull"


class SyncResult(NamedTuple):
    action: SyncAction
    profile: RemoteProfile | None  # the profile now shared by both sides, if any


def utc_timestamp(moment: datetime | None = None) -> str:
    return (
        (moment or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )


def _parse_time(text: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return _EPOCH
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class SyncStateStore:
    """Remembers the ``updated_at`` of the local profile, inside the profile folder."""

    def __init__(self, profile_dir: Path) -> None:
        self._path = profile_dir / SYNC_STATE_FILE

    def updated_at(self) -> str:
        """Empty when this profile was never saved or synced."""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ""
        value = data.get("updated_at") if isinstance(data, dict) else None
        return value if isinstance(value, str) else ""

    def mark(self, updated_at: str) -> None:
        try:
            write_json_atomic(self._path, {"updated_at": updated_at})
        except OSError:
            pass  # a lost mark only makes the next sync compare against an older time

    def touch(self) -> str:
        """Call after any local change to the synced data; returns the new time."""
        now = utc_timestamp()
        self.mark(now)
        return now


def build_profile(
    config: AppConfig,
    entries: list[GlossaryEntry],
    topics: list[Group],
    updated_at: str,
) -> RemoteProfile:
    settings = {
        key: value
        for key, value in asdict(config).items()
        if key not in MACHINE_SPECIFIC_FIELDS
    }
    return RemoteProfile(
        settings=settings,
        words=[asdict(entry) for entry in entries],
        topics=[asdict(group) for group in topics],
        updated_at=updated_at,
    )


def apply_profile(
    profile: RemoteProfile,
    config: AppConfig,
    glossary: GlossaryStore,
    topics: GroupStore,
) -> AppConfig:
    """Store the remote words and topics; return the config with the remote settings.

    Machine-specific fields keep their local value, and every setting is validated.
    """
    remote = {
        key: value
        for key, value in profile.settings.items()
        if key not in MACHINE_SPECIFIC_FIELDS
    }
    glossary.replace_all(_entries_from(profile.words))
    topics.replace_all(_groups_from(profile.topics))
    return AppConfig.from_dict({**asdict(config), **remote})


def apply_sync_result(
    result: SyncResult,
    state: SyncStateStore,
    config: AppConfig,
    glossary: GlossaryStore,
    topics: GroupStore,
) -> AppConfig:
    """Finish a sync on the main thread; returns the config to use from now on."""
    if result.profile is None:
        return config
    state.mark(result.profile.updated_at)
    if result.action is SyncAction.PULL:
        return apply_profile(result.profile, config, glossary, topics)
    return config


def decide_sync(local_updated_at: str, remote: RemoteProfile | None) -> SyncAction:
    if remote is None:
        return SyncAction.PUSH
    if not local_updated_at:
        return SyncAction.PULL
    local_time = _parse_time(local_updated_at)
    remote_time = _parse_time(remote.updated_at)
    if remote_time > local_time:
        return SyncAction.PULL
    if remote_time < local_time:
        return SyncAction.PUSH
    return SyncAction.NONE


def run_sync(
    client: AccountClient, id_token: str, local: RemoteProfile, now: str
) -> SyncResult:
    """Compare with the account and push or pull. ``local.updated_at`` is empty when
    the profile was never saved; ``now`` stamps its first upload."""
    remote = client.fetch_profile(id_token)
    action = decide_sync(local.updated_at, remote)
    if action is SyncAction.PULL:
        return SyncResult(action, remote)
    if action is SyncAction.PUSH:
        stamped = local if local.updated_at else _with_time(local, now)
        return SyncResult(action, client.push_profile(id_token, stamped))
    return SyncResult(action, None)


def _with_time(profile: RemoteProfile, updated_at: str) -> RemoteProfile:
    return RemoteProfile(profile.settings, profile.words, profile.topics, updated_at)


def _entries_from(raw: list[Any]) -> list[GlossaryEntry]:
    known = {f.name for f in fields(GlossaryEntry)}
    entries: list[GlossaryEntry] = []
    for item in raw[:MAX_ENTRIES]:
        values = (
            {k: v for k, v in item.items() if k in known}
            if isinstance(item, dict)
            else {}
        )
        if _is_entry(values):
            entries.append(GlossaryEntry(**values))
    return entries


def _is_entry(values: dict[str, Any]) -> bool:
    required = ("word", "explanation", "document", "added_on")
    return all(isinstance(values.get(key), str) for key in required) and isinstance(
        values.get("topic", ""), str
    )


def _groups_from(raw: list[Any]) -> list[Group]:
    groups: list[Group] = []
    for item in raw[:MAX_GROUPS]:
        if (
            isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and isinstance(item.get("name"), str)
            and item["id"]
        ):
            groups.append(Group(item["id"], item["name"]))
    return groups
