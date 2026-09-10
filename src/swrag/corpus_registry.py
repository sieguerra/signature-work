"""Named local corpora for the UI toggle.

Each corpus is a separate folder and a separate in-memory index. The explorer
never mixes documents from two worlds in one retrieve. Harbor and DKU paths
stay where they are; new industry worlds live under ``datasets/<id>/``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from swrag.ingestion.loader import load_documents

REGISTRY_PATH = Path("datasets") / "registry.json"
DEFAULT_CORPUS_ID = "dku"


@dataclass(frozen=True)
class CorpusEntry:
    """One selectable corpus. Paths are absolute after load."""

    id: str
    label: str
    industry: str
    group: str
    corpus_dir: Path
    gold_path: Path | None
    examples: tuple[str, ...]
    fictional: bool

    @property
    def doc_count(self) -> int:
        if not self.corpus_dir.is_dir():
            return 0
        return len(list(self.corpus_dir.glob("*.txt")))

    def as_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "industry": self.industry,
            "group": self.group,
            "corpus_dir": str(self.corpus_dir),
            "gold_path": str(self.gold_path) if self.gold_path else None,
            "examples": list(self.examples),
            "fictional": self.fictional,
            "doc_count": self.doc_count,
        }


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_registry(*, root: Path | None = None) -> tuple[CorpusEntry, ...]:
    """Read ``datasets/registry.json`` and resolve paths against the repo."""
    base = root or repo_root()
    path = base / REGISTRY_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "corpora" not in payload:
        raise ValueError(f"{path}: expected an object with a 'corpora' list")
    entries: list[CorpusEntry] = []
    seen: set[str] = set()
    for index, raw in enumerate(payload["corpora"]):
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: corpora[{index}] must be an object")
        corpus_id = str(raw.get("id") or "").strip()
        if not corpus_id or "/" in corpus_id or "\\" in corpus_id or ".." in corpus_id:
            raise ValueError(f"{path}: corpora[{index}] has an unsafe id")
        if corpus_id in seen:
            raise ValueError(f"{path}: duplicate corpus id {corpus_id!r}")
        seen.add(corpus_id)
        gold_raw = raw.get("gold_path")
        entries.append(
            CorpusEntry(
                id=corpus_id,
                label=str(raw.get("label") or corpus_id),
                industry=str(raw.get("industry") or ""),
                group=str(raw.get("group") or "Other"),
                corpus_dir=_resolve(base, raw.get("corpus_dir")),
                gold_path=_resolve(base, gold_raw) if gold_raw else None,
                examples=tuple(str(item) for item in raw.get("examples") or ()),
                fictional=bool(raw.get("fictional", True)),
            )
        )
    if not entries:
        raise ValueError(f"{path}: 'corpora' is empty")
    return tuple(entries)


def default_corpus_id(*, root: Path | None = None) -> str:
    base = root or repo_root()
    path = base / REGISTRY_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    configured = str(payload.get("default") or DEFAULT_CORPUS_ID)
    ids = {entry.id for entry in load_registry(root=base)}
    if configured not in ids:
        raise ValueError(f"{path}: default {configured!r} is not in corpora")
    return configured


def get_corpus(corpus_id: str, *, root: Path | None = None) -> CorpusEntry:
    for entry in load_registry(root=root):
        if entry.id == corpus_id:
            return entry
    raise KeyError(corpus_id)


def traces_dir_for(corpus_id: str, traces_root: str | Path) -> Path:
    """Isolate playground traces so two corpora never share a run list."""
    if not corpus_id or "/" in corpus_id or "\\" in corpus_id or ".." in corpus_id:
        raise ValueError(f"unsafe corpus id: {corpus_id!r}")
    return Path(traces_root) / corpus_id


def assert_corpus_readable(entry: CorpusEntry) -> None:
    """Fail fast if the folder is missing or has no ``.txt`` files."""
    load_documents(entry.corpus_dir)


def _resolve(root: Path, value: object) -> Path:
    path = Path(str(value))
    if path.is_absolute():
        return path
    return (root / path).resolve()
