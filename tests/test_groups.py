"""GroupStore: the named groups behind library folders and glossary topics."""

import json
from pathlib import Path

import pytest

from clearread.services.groups import (
    MAX_GROUPS,
    MAX_NAME_CHARS,
    GroupNameError,
    GroupNameProblem,
    GroupStore,
)


def problem_of(action: object) -> GroupNameProblem:
    with pytest.raises(GroupNameError) as caught:
        action()  # type: ignore[operator]
    return caught.value.problem


def test_create_rename_and_delete_persist(tmp_path: Path) -> None:
    path = tmp_path / "folders.json"
    store = GroupStore(path)
    maths = store.create("Matemáticas")
    science = store.create("Ciencias")
    assert [g.name for g in GroupStore(path).groups()] == ["Matemáticas", "Ciencias"]

    store.rename(maths.id, "Mates")
    reloaded = GroupStore(path)
    assert reloaded.get(maths.id) is not None
    assert reloaded.get(maths.id).name == "Mates"  # type: ignore[union-attr]

    store.delete(science.id)
    assert [g.name for g in GroupStore(path).groups()] == ["Mates"]


def test_names_are_cleaned_and_limited() -> None:
    store = GroupStore()
    assert store.create("  Historia   del   arte ").name == "Historia del arte"
    assert len(store.create("x" * 200).name) == MAX_NAME_CHARS


def test_empty_and_duplicate_names_are_refused_ignoring_case_and_accents() -> None:
    store = GroupStore()
    first = store.create("Matemáticas")
    assert problem_of(lambda: store.create("   ")) is GroupNameProblem.EMPTY
    assert problem_of(lambda: store.create("MATEMATICAS")) is GroupNameProblem.DUPLICATE
    other = store.create("Ciencias")
    assert (
        problem_of(lambda: store.rename(other.id, "matematicas"))
        is GroupNameProblem.DUPLICATE
    )
    store.rename(first.id, "MATEMÁTICAS")  # the same group may change its own case
    assert store.get(first.id).name == "MATEMÁTICAS"  # type: ignore[union-attr]


def test_there_is_a_limit_of_groups() -> None:
    store = GroupStore()
    for number in range(MAX_GROUPS):
        store.create(f"Grupo {number}")
    assert problem_of(lambda: store.create("Uno más")) is GroupNameProblem.TOO_MANY


def test_find_by_name_ignores_case_and_accents() -> None:
    store = GroupStore()
    group = store.create("Ciencias")
    assert store.find_by_name("  cIENCIAS ") == group
    assert store.find_by_name("Otra") is None


@pytest.mark.parametrize("content", ["", "{no json", '{"a": 1}', "[1, 2]", "[{}]"])
def test_a_damaged_file_means_no_groups(tmp_path: Path, content: str) -> None:
    path = tmp_path / "folders.json"
    path.write_text(content, encoding="utf-8")
    assert GroupStore(path).groups() == []


def test_the_file_is_a_plain_list_of_id_and_name(tmp_path: Path) -> None:
    path = tmp_path / "topics.json"
    group = GroupStore(path).create("Ciencias")
    assert json.loads(path.read_text(encoding="utf-8")) == [
        {"id": group.id, "name": "Ciencias"}
    ]
