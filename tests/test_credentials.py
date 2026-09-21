"""Hashed project API keys. No live OpenAI."""

from __future__ import annotations

from pathlib import Path

import pytest

from swrag.api.credentials import (
    KEYS_FILENAME,
    create_api_key,
    find_active_key,
    keys_file_contains_plaintext,
    list_api_keys,
    revoke_api_key,
)
from swrag.projects import create_project

ROOT = Path(__file__).resolve().parents[1]


def _project(tmp_path: Path, name: str = "Keys"):
    traces_root = tmp_path / "traces"
    base = tmp_path / "projects"
    entry = create_project(name, root=ROOT, traces_root=traces_root, base=base)
    return entry, traces_root, base


def test_created_key_is_hashed_shown_once_and_revocable(tmp_path: Path) -> None:
    entry, traces_root, base = _project(tmp_path)
    token, record = create_api_key(
        entry.id, root=ROOT, traces_root=traces_root, base=base
    )
    folder = tmp_path / "projects" / entry.id
    assert token.startswith("swr_")
    assert token != record.token_hash
    assert not keys_file_contains_plaintext(folder, token)
    stored = (folder / KEYS_FILENAME).read_text(encoding="utf-8")
    assert record.token_hash in stored
    assert "hash" in stored
    public = record.as_public_payload()
    assert "hash" not in public
    assert "token_hash" not in public
    assert find_active_key(token, root=ROOT, base=base) == record
    listed = list_api_keys(entry.id, root=ROOT, traces_root=traces_root, base=base)
    assert listed[0].key_id == record.key_id
    revoked = revoke_api_key(
        entry.id, record.key_id, root=ROOT, traces_root=traces_root, base=base
    )
    assert revoked.revoked_at is not None
    assert find_active_key(token, root=ROOT, base=base) is None


def test_builtin_corpus_cannot_have_keys(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="built-in"):
        create_api_key(
            "harbor",
            root=ROOT,
            traces_root=tmp_path / "traces",
            base=tmp_path / "projects",
        )


def test_unknown_token_does_not_match(tmp_path: Path) -> None:
    entry, traces_root, base = _project(tmp_path, "Other")
    create_api_key(entry.id, root=ROOT, traces_root=traces_root, base=base)
    assert find_active_key("swr_not-a-real-token", root=ROOT, base=base) is None
    assert find_active_key("", root=ROOT, base=base) is None
