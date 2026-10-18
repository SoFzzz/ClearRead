"""Named groups with a stable id: library folders and glossary topics.

Items point to a group by id, so renaming a group never touches them. Without a path the
groups live in memory only.
"""

import json
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

from clearread.services.atomic_json import write_json_atomic
from clearread.services.text_search import search_key

MAX_GROUPS = 50
MAX_NAME_CHARS = 40
FILTER_ALL = "*"  # "show everything" in a group filter
NO_GROUP = ""  # the id of an item that belongs to no group


class GroupNameProblem(Enum):
    """The value is the last part of the ``group.error.<value>`` catalog keys."""

    EMPTY = "empty"
    DUPLICATE = "duplicate"
    TOO_MANY = "too_many"


class GroupNameError(Exception):
    def __init__(self, problem: GroupNameProblem) -> None:
        super().__init__(problem.value)
        self.problem = problem


@dataclass(frozen=True)
class Group:
    id: str
    name: str


def clean_name(name: str) -> str:
    return " ".join(name.split())[:MAX_NAME_CHARS].strip()


class GroupStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._groups = self._load()

    def groups(self) -> list[Group]:
        return list(self._groups)

    def get(self, group_id: str) -> Group | None:
        return next((g for g in self._groups if g.id == group_id), None)

    def find_by_name(self, name: str) -> Group | None:
        needle = search_key(name)
        return next((g for g in self._groups if search_key(g.name) == needle), None)

    def create(self, name: str) -> Group:
        cleaned = self._checked(name, None)
        if len(self._groups) >= MAX_GROUPS:
            raise GroupNameError(GroupNameProblem.TOO_MANY)
        group = Group(uuid.uuid4().hex, cleaned)
        self._groups.append(group)
        self._save()
        return group

    def rename(self, group_id: str, name: str) -> None:
        cleaned = self._checked(name, group_id)
        self._groups = [
            Group(g.id, cleaned) if g.id == group_id else g for g in self._groups
        ]
        self._save()

    def delete(self, group_id: str) -> None:
        self._groups = [g for g in self._groups if g.id != group_id]
        self._save()

    def _checked(self, name: str, own_id: str | None) -> str:
        cleaned = clean_name(name)
        if not cleaned:
            raise GroupNameError(GroupNameProblem.EMPTY)
        twin = self.find_by_name(cleaned)
        if twin is not None and twin.id != own_id:
            raise GroupNameError(GroupNameProblem.DUPLICATE)
        return cleaned

    def _load(self) -> list[Group]:
        if self._path is None:
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return [Group(**item) for item in raw][:MAX_GROUPS]
        except (
            OSError,
            ValueError,
            TypeError,
        ):  # a missing or damaged file starts an empty list
            return []

    def _save(self) -> None:
        if self._path is None:
            return
        try:
            write_json_atomic(self._path, [asdict(g) for g in self._groups])
        except OSError:
            pass  # losing the write only costs the last change, never the reading
