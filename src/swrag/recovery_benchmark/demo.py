"""Visual demo corpus. These questions are not benchmark samples."""

from __future__ import annotations

import json
from pathlib import Path

from swrag.recovery_benchmark.protocol import DEMO_CORPUS_ID, DEMO_MANIFEST


def load_demo_manifest(root: Path) -> dict:
    path = root / DEMO_MANIFEST
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("corpus_id") != DEMO_CORPUS_ID:
        raise ValueError("demo manifest corpus_id does not match the protocol")
    if payload.get("benchmark") is not False:
        raise ValueError("demo manifest must set benchmark to false")
    if payload.get("role") != "visual_demo":
        raise ValueError("demo manifest role must be visual_demo")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("demo manifest needs cases")
    return payload


def demo_question_ids(root: Path) -> set[str]:
    manifest = load_demo_manifest(root)
    return {str(case["question_id"]) for case in manifest["cases"]}
