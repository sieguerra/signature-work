"""Runtime-created projects that own documents and traces.

Built-in registry corpora stay read-only. A project is the isolation boundary
the playground uploads into (issue #70).
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from swrag.config import ALLOWED_CHAT_MODELS, DEFAULT_CHAT_MODEL
from swrag.recovery.policy import (
    POLICY_V2C_GAP_AWARE,
    PRODUCT_CURRENT,
    PRODUCT_GAP_AWARE,
    resolve_product_policy,
)
from swrag.corpus_registry import CorpusEntry, get_corpus, load_registry, traces_dir_for
from swrag.ingestion.pdf import PdfExtractError, extract_pdf_pages

PROJECTS_DIRNAME = Path("experiments") / "projects"
PROJECT_GROUP = "Projects"
_SAFE_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_SAFE_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
ALLOWED_SUFFIXES = frozenset({".txt", ".pdf"})
MAX_UPLOAD_BYTES = 32 * 1024 * 1024
MAX_INSTRUCTIONS_CHARS = 8000


def projects_root(root: Path) -> Path:
    return root / PROJECTS_DIRNAME


def list_workspaces(
    *, root: Path, traces_root: Path, base: Path | None = None
) -> list[CorpusEntry]:
    """Built-in corpora first, then runtime projects."""
    return [
        *load_registry(root=root),
        *load_projects(root=root, traces_root=traces_root, base=base),
    ]


def get_workspace(
    workspace_id: str,
    *,
    root: Path,
    traces_root: Path,
    base: Path | None = None,
) -> CorpusEntry:
    try:
        return get_corpus(workspace_id, root=root)
    except KeyError:
        pass
    for entry in load_projects(root=root, traces_root=traces_root, base=base):
        if entry.id == workspace_id:
            return entry
    raise KeyError(workspace_id)


def load_projects(
    *, root: Path, traces_root: Path, base: Path | None = None
) -> tuple[CorpusEntry, ...]:
    folder_root = base or projects_root(root)
    if not folder_root.is_dir():
        return ()
    entries: list[CorpusEntry] = []
    for folder in sorted(folder_root.iterdir(), key=lambda path: path.name.lower()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        config_path = folder / "project.json"
        if not config_path.is_file():
            continue
        entries.append(_entry_from_folder(folder, traces_root))
    return tuple(entries)


def create_project(
    name: str, *, root: Path, traces_root: Path, base: Path | None = None
) -> CorpusEntry:
    cleaned = " ".join(name.split()).strip()
    if not cleaned:
        raise ValueError("name is required")
    if len(cleaned) > 80:
        raise ValueError("name is too long")
    folder_root = base or projects_root(root)
    project_id = _allocate_id(cleaned, root=root, base=folder_root)
    folder = folder_root / project_id
    documents = folder / "documents"
    documents.mkdir(parents=True, exist_ok=False)
    payload = {
        "id": project_id,
        "name": cleaned,
        "config": default_project_config(),
    }
    (folder / "project.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    traces = traces_dir_for(project_id, traces_root)
    traces.mkdir(parents=True, exist_ok=True)
    return _entry_from_folder(folder, traces_root)


def delete_project(
    project_id: str, *, root: Path, base: Path | None = None
) -> None:
    _assert_safe_id(project_id)
    try:
        get_corpus(project_id, root=root)
    except KeyError:
        pass
    else:
        raise ValueError(f"{project_id} is a built-in corpus and cannot be deleted")
    folder = (base or projects_root(root)) / project_id
    if not folder.is_dir() or not (folder / "project.json").is_file():
        raise KeyError(project_id)
    shutil.rmtree(folder)


def list_documents(corpus_dir: Path) -> list[dict[str, object]]:
    if not corpus_dir.is_dir():
        return []
    rows: list[dict[str, object]] = []
    for path in sorted(
        (*corpus_dir.glob("*.txt"), *corpus_dir.glob("*.pdf")),
        key=lambda item: item.name.lower(),
    ):
        rows.append(
            {
                "name": path.name,
                "suffix": path.suffix.lower(),
                "size": path.stat().st_size,
            }
        )
    return rows


def default_project_config() -> dict[str, object]:
    return {
        "instructions": "",
        "chat_model": DEFAULT_CHAT_MODEL,
        "top_k": 4,
        "recovery_policy": PRODUCT_CURRENT,
    }


_BEHAVIOR_TONES = frozenset({"", "professional", "friendly", "casual", "academic", "custom"})
_BEHAVIOR_DETAILS = frozenset({"", "concise", "balanced", "detailed"})
_BEHAVIOR_EXPLANATIONS = frozenset({"", "direct", "step", "explanatory"})
_BEHAVIOR_PRESETS = frozenset({"research", "knowledge", "support", "technical", "sales", "custom"})
_FORMAT_KEYS = ("bullets", "numbered", "tables", "summaryFirst")
_GROUND_KEYS = ("evidence", "cite", "admit", "uncertainty")


def _behavior_flags(raw: object, keys: tuple[str, ...], label: str) -> dict[str, bool]:
    payload = raw if isinstance(raw, dict) else {}
    flags: dict[str, bool] = {}
    for key in keys:
        value = payload.get(key, False)
        if not isinstance(value, bool):
            raise ValueError(f"behavior.{label}.{key} must be a boolean")
        flags[key] = value
    return flags


def sanitize_behavior(raw: object) -> dict[str, object]:
    """Keep the guided-builder choices. Generation still reads ``instructions``."""
    if not isinstance(raw, dict):
        raise ValueError("behavior must be an object")
    mode = raw.get("mode", "guided")
    if mode not in {"guided", "raw"}:
        raise ValueError("behavior.mode must be guided or raw")
    preset = raw.get("preset", "custom")
    if preset not in _BEHAVIOR_PRESETS:
        raise ValueError("behavior.preset is not a known template")
    tone = raw.get("tone", "")
    if tone not in _BEHAVIOR_TONES:
        raise ValueError("behavior.tone is not a known tone")
    detail = raw.get("detail", "")
    if detail not in _BEHAVIOR_DETAILS:
        raise ValueError("behavior.detail is not a known detail level")
    explanation = raw.get("explanation", "")
    if explanation not in _BEHAVIOR_EXPLANATIONS:
        raise ValueError("behavior.explanation is not a known style")
    custom_tone = str(raw.get("customTone") or "").replace("\n", " ").strip()
    if len(custom_tone) > 240:
        raise ValueError("behavior.customTone is too long")
    rules_raw = raw.get("customRules") or []
    if not isinstance(rules_raw, list) or len(rules_raw) > 30:
        raise ValueError("behavior.customRules must be a list of at most 30 strings")
    rules: list[str] = []
    for rule in rules_raw:
        if not isinstance(rule, str):
            raise ValueError("behavior.customRules must be strings")
        text = rule.strip()
        if not text:
            continue
        if len(text) > 2000:
            raise ValueError("a custom rule is too long")
        rules.append(text)
    legacy = raw.get("legacyText")
    if legacy is not None and not isinstance(legacy, str):
        raise ValueError("behavior.legacyText must be a string")
    if isinstance(legacy, str) and len(legacy) > MAX_INSTRUCTIONS_CHARS:
        raise ValueError("behavior.legacyText is too long")
    return {
        "mode": mode,
        "preset": preset,
        "tone": tone,
        "customTone": custom_tone if tone == "custom" else "",
        "detail": detail,
        "explanation": explanation,
        "formatting": _behavior_flags(raw.get("formatting"), _FORMAT_KEYS, "formatting"),
        "grounding": _behavior_flags(raw.get("grounding"), _GROUND_KEYS, "grounding"),
        "customRules": rules,
        "legacyText": legacy,
    }


def _stored_policy(value: object) -> str:
    """Persist the product name. Blank and unknown-to-blank stay current v1."""
    internal = resolve_product_policy(value if isinstance(value, str) else None)
    if internal == POLICY_V2C_GAP_AWARE:
        return PRODUCT_GAP_AWARE
    return PRODUCT_CURRENT


def normalize_project_config(raw: object | None) -> dict[str, object]:
    payload = raw if isinstance(raw, dict) else {}
    instructions = str(payload.get("instructions") or "")
    if len(instructions) > MAX_INSTRUCTIONS_CHARS:
        raise ValueError(f"instructions must be at most {MAX_INSTRUCTIONS_CHARS} characters")
    model = str(payload.get("chat_model") or DEFAULT_CHAT_MODEL).strip()
    if model not in ALLOWED_CHAT_MODELS:
        raise ValueError(f"chat_model must be one of {sorted(ALLOWED_CHAT_MODELS)}")
    try:
        top_k = int(payload.get("top_k") or 4)
    except (TypeError, ValueError) as error:
        raise ValueError("top_k must be an integer from 1 to 20") from error
    if top_k < 1 or top_k > 20:
        raise ValueError("top_k must be an integer from 1 to 20")
    config: dict[str, object] = {
        "instructions": instructions,
        "chat_model": model,
        "top_k": top_k,
        "recovery_policy": _stored_policy(payload.get("recovery_policy")),
    }
    if payload.get("behavior") is not None:
        config["behavior"] = sanitize_behavior(payload.get("behavior"))
    return config


def update_project_config(
    project_id: str,
    raw: object,
    *,
    root: Path,
    traces_root: Path,
    base: Path | None = None,
) -> CorpusEntry:
    entry = get_workspace(project_id, root=root, traces_root=traces_root, base=base)
    if not entry.writable:
        raise ValueError(f"{project_id} is a built-in corpus and cannot be configured")
    folder = entry.corpus_dir.parent
    config_path = folder / "project.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        payload = {"id": project_id, "name": entry.label}
    payload["config"] = normalize_project_config(raw)
    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return _entry_from_folder(folder, traces_root)


def read_document_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8")
    if suffix != ".pdf":
        raise ValueError("only .txt and .pdf files can be read")
    try:
        pages = extract_pdf_pages(path)
    except PdfExtractError as error:
        raise ValueError(str(error)) from error
    return "\n\n".join(text for _, text in pages if text.strip())


def validate_uploaded_file(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        path.read_text(encoding="utf-8")
        return
    if suffix != ".pdf":
        raise ValueError("only .txt and .pdf files can be uploaded")
    try:
        pages = extract_pdf_pages(path)
    except PdfExtractError as error:
        raise ValueError(str(error)) from error
    if not pages:
        raise ValueError(f"{path.name}: no extractable text")


def safe_upload_name(filename: str) -> str:
    name = Path(filename).name
    if name != filename or "/" in filename or "\\" in filename:
        raise ValueError("filename must not contain a path")
    if not _SAFE_FILE.match(name) or ".." in name:
        raise ValueError("filename contains unsupported characters")
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("only .txt and .pdf files can be uploaded")
    return name


def _entry_from_folder(folder: Path, traces_root: Path) -> CorpusEntry:
    payload = json.loads((folder / "project.json").read_text(encoding="utf-8"))
    project_id = str(payload.get("id") or folder.name)
    _assert_safe_id(project_id)
    name = str(payload.get("name") or project_id)
    documents = folder / "documents"
    documents.mkdir(exist_ok=True)
    traces_dir_for(project_id, traces_root).mkdir(parents=True, exist_ok=True)
    del traces_root  # traces live under the shared experiments/output root
    return CorpusEntry(
        id=project_id,
        label=name,
        industry="Playground project",
        group=PROJECT_GROUP,
        corpus_dir=documents,
        gold_path=None,
        examples=(),
        fictional=True,
        writable=True,
        config=normalize_project_config(payload.get("config")),
    )


def _allocate_id(name: str, *, root: Path, base: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "project"
    taken = {entry.id for entry in load_registry(root=root)}
    if base.is_dir():
        taken.update(path.name for path in base.iterdir() if path.is_dir())
    candidate = slug
    index = 2
    while candidate in taken:
        candidate = f"{slug}-{index}"
        index += 1
    _assert_safe_id(candidate)
    return candidate


def _assert_safe_id(project_id: str) -> None:
    if not _SAFE_ID.match(project_id):
        raise ValueError(f"unsafe project id: {project_id!r}")
