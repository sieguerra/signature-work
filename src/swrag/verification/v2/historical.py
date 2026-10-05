"""Historical run-level transitions from committed comparison files.

The trace directories for these runs are gone, so evidence text is unknown.
Coverage and model verifiers must return unavailable rather than guess.
"""

from __future__ import annotations

import json
from pathlib import Path

from swrag.evaluation.gold import load_gold_set
from swrag.verification.v2.examples import Example
from swrag.verification.v2.gold_transition import label_answers
from swrag.verification.v2.protocol import ARCHIVE_CORPUS, CLASSES, DEV_CORPUS, TEST_CORPUS
from swrag.verification.v2.transitions import StateView, Transition

ARCHIVE_RUNS = (
    "experiments/results/20260910T070623",
    "experiments/results/20260927T151157",
    "experiments/results/20260927T151544",
)


def load_archive(root: Path) -> tuple[Example, ...]:
    found: list[Example] = []
    for relative in ARCHIVE_RUNS:
        run_dir = root / relative
        config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
        comparison = json.loads((run_dir / "comparison.json").read_text(encoding="utf-8"))
        gold_path = _resolve_gold(str(config["gold_path"]), root)
        gold_by_id = {item.question_id: item for item in load_gold_set(gold_path)}
        corpus_id = _corpus_id(str(config.get("corpus_dir", "")), str(config.get("gold_path", "")))
        for row in comparison.get("paired_outcomes") or []:
            payload = row.get("eval_guided")
            if not isinstance(payload, dict) or not payload.get("previous_answer"):
                continue
            question_id = str(row["question_id"])
            gold = gold_by_id.get(question_id)
            if gold is None:
                continue
            outcome = payload.get("verification_outcome")
            transition = Transition(
                level="run",
                question=str(row.get("question") or gold.question),
                before=StateView(answer=str(payload["previous_answer"]), chunks=(), evidence_known=False),
                after=StateView(answer=str(payload.get("answer") or ""), chunks=(), evidence_known=False),
                action=str(payload["recovery_action"]) if payload.get("recovery_action") else None,
                executed=True,
                schema_version=1,
                question_id=question_id,
                corpus_id=corpus_id,
            )
            found.append(
                Example(
                    transition=transition,
                    gold_label=label_answers(transition.before.answer, transition.after.answer, gold),
                    v1_outcome=outcome if outcome in CLASSES else None,
                    answerable=gold.answerable,
                    panel="archive",
                    split="archive",
                    source=str(run_dir.relative_to(root)),
                    failure_class=payload.get("attributed_class"),
                )
            )
    return tuple(found)


def _resolve_gold(path: str, root: Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate
    marker = "datasets/"
    if marker in path:
        relative = root / path[path.index(marker) :]
        if relative.exists():
            return relative
    raise FileNotFoundError(path)


def _corpus_id(corpus_dir: str, gold_path: str) -> str:
    text = f"{corpus_dir} {gold_path}"
    if DEV_CORPUS in text:
        return DEV_CORPUS
    if f"{TEST_CORPUS}/" in text or text.rstrip("/").endswith(f"/{TEST_CORPUS}"):
        return TEST_CORPUS
    if "datasets/corpus" in text or "datasets/gold" in text:
        return ARCHIVE_CORPUS
    return "unknown"
