"""Loading backend/.env."""

import os
from pathlib import Path

import pytest

from clearread_backend.settings import load_env_file


def test_env_file_with_a_utf8_bom_still_sets_its_first_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FIRST_KEY", raising=False)
    monkeypatch.delenv("SECOND_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_bytes(b'\xef\xbb\xbfFIRST_KEY=one\r\nSECOND_KEY="two"\r\n')
    load_env_file(env)
    assert os.environ["FIRST_KEY"] == "one"
    assert os.environ["SECOND_KEY"] == "two"
    monkeypatch.delenv("FIRST_KEY")
    monkeypatch.delenv("SECOND_KEY")
