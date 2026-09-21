"""Project-scoped API keys for ``/api/v1/*`` (issue #79).

Plaintext is returned once at creation and never written to disk. Verification
uses SHA-256 of the token with a constant-time compare. Dashboard ``/api/*``
routes stay unauthenticated for local use.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from swrag.projects import _assert_safe_id, get_workspace, projects_root

KEYS_FILENAME = "keys.json"
KEY_PREFIX = "swr_"
TOKEN_BYTES = 32
HASH_NAME = "sha256"


@dataclass(frozen=True)
class StoredKey:
    key_id: str
    prefix: str
    token_hash: str
    created_at: str
    revoked_at: str | None
    scope: str
    project_id: str

    def as_public_payload(self) -> dict[str, object]:
        return {
            "id": self.key_id,
            "prefix": self.prefix,
            "created_at": self.created_at,
            "revoked_at": self.revoked_at,
            "scope": self.scope,
        }


def create_api_key(
    project_id: str,
    *,
    root: Path,
    traces_root: Path,
    base: Path | None = None,
    scope: str = "evaluations",
) -> tuple[str, StoredKey]:
    """Create a key. Returns ``(plaintext, record)``. Plaintext is not stored."""
    folder = _project_folder(project_id, root=root, traces_root=traces_root, base=base)
    token = KEY_PREFIX + secrets.token_urlsafe(TOKEN_BYTES)
    record = StoredKey(
        key_id="k_" + secrets.token_hex(8),
        prefix=token[:12],
        token_hash=_hash_token(token),
        created_at=datetime.now(timezone.utc).isoformat(),
        revoked_at=None,
        scope=scope,
        project_id=project_id,
    )
    payload = _read_keys_file(folder)
    rows = list(payload.get("keys") or [])
    rows.append(_record_to_row(record))
    payload["keys"] = rows
    _write_keys_file(folder, payload)
    return token, record


def list_api_keys(
    project_id: str,
    *,
    root: Path,
    traces_root: Path,
    base: Path | None = None,
) -> tuple[StoredKey, ...]:
    folder = _project_folder(project_id, root=root, traces_root=traces_root, base=base)
    return tuple(_records_in_folder(folder, project_id))


def revoke_api_key(
    project_id: str,
    key_id: str,
    *,
    root: Path,
    traces_root: Path,
    base: Path | None = None,
) -> StoredKey:
    folder = _project_folder(project_id, root=root, traces_root=traces_root, base=base)
    payload = _read_keys_file(folder)
    rows = list(payload.get("keys") or [])
    stamp = datetime.now(timezone.utc).isoformat()
    updated: list[dict[str, Any]] = []
    found: StoredKey | None = None
    for row in rows:
        record = _row_to_record(row, project_id)
        if record.key_id == key_id:
            if record.revoked_at is None:
                record = StoredKey(
                    key_id=record.key_id,
                    prefix=record.prefix,
                    token_hash=record.token_hash,
                    created_at=record.created_at,
                    revoked_at=stamp,
                    scope=record.scope,
                    project_id=project_id,
                )
            found = record
            updated.append(_record_to_row(record))
        else:
            updated.append(row if isinstance(row, dict) else _record_to_row(record))
    if found is None:
        raise KeyError(key_id)
    payload["keys"] = updated
    _write_keys_file(folder, payload)
    return found


def find_active_key(token: str, *, root: Path, base: Path | None = None) -> StoredKey | None:
    """Resolve a bearer token to a live key. Does not log or return the token."""
    if not token or not token.startswith(KEY_PREFIX):
        return None
    digest = _hash_token(token)
    folder_root = base or projects_root(root)
    if not folder_root.is_dir():
        return None
    for folder in folder_root.iterdir():
        if not folder.is_dir() or not (folder / "project.json").is_file():
            continue
        project_id = folder.name
        try:
            _assert_safe_id(project_id)
        except ValueError:
            continue
        for record in _records_in_folder(folder, project_id):
            if record.revoked_at:
                continue
            stored = record.token_hash
            if not isinstance(stored, str) or len(stored) != len(digest):
                continue
            try:
                if hmac.compare_digest(stored, digest):
                    return record
            except (TypeError, ValueError):
                continue
    return None


def keys_file_contains_plaintext(folder: Path, token: str) -> bool:
    path = folder / KEYS_FILENAME
    if not path.is_file():
        return False
    return token in path.read_text(encoding="utf-8")


def _project_folder(
    project_id: str,
    *,
    root: Path,
    traces_root: Path,
    base: Path | None,
) -> Path:
    entry = get_workspace(project_id, root=root, traces_root=traces_root, base=base)
    if not entry.writable:
        raise ValueError(f"{project_id} is a built-in corpus and cannot have API keys")
    return entry.corpus_dir.parent


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _read_keys_file(folder: Path) -> dict[str, Any]:
    path = folder / KEYS_FILENAME
    if not path.is_file():
        return {"keys": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"keys": []}
    if not isinstance(payload, dict):
        return {"keys": []}
    return payload


def _write_keys_file(folder: Path, payload: dict[str, Any]) -> None:
    path = folder / KEYS_FILENAME
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _records_in_folder(folder: Path, project_id: str) -> list[StoredKey]:
    payload = _read_keys_file(folder)
    records: list[StoredKey] = []
    for row in payload.get("keys") or []:
        if not isinstance(row, dict):
            continue
        records.append(_row_to_record(row, project_id))
    return records


def _record_to_row(record: StoredKey) -> dict[str, Any]:
    return {
        "id": record.key_id,
        "prefix": record.prefix,
        "hash": record.token_hash,
        "created_at": record.created_at,
        "revoked_at": record.revoked_at,
        "scope": record.scope,
    }


def _row_to_record(row: dict[str, Any], project_id: str) -> StoredKey:
    return StoredKey(
        key_id=str(row.get("id") or ""),
        prefix=str(row.get("prefix") or ""),
        token_hash=str(row.get("hash") or ""),
        created_at=str(row.get("created_at") or ""),
        revoked_at=str(row["revoked_at"]) if row.get("revoked_at") else None,
        scope=str(row.get("scope") or "evaluations"),
        project_id=project_id,
    )
