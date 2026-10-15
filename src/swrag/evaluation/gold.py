"""Load the hand-built gold set.

ADR 003 fixes the gold set as hand-written questions over ``datasets/corpus``,
with short answers so Exact Match and F1 are meaningful, and with unanswerable
questions so the corpus-gap failure class exists at all.

Format is JSON Lines: one question object per line, so questions can be added
without rewriting the file and diffs stay readable.
"""

from __future__ import annotations

import json
from pathlib import Path

from swrag.types import GoldQuestion


def load_gold_set(path: str | Path) -> tuple[GoldQuestion, ...]:
    """Read a ``.jsonl`` gold set, skipping blank lines and ``#`` comments."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Gold set not found: {file_path}")

    questions: list[GoldQuestion] = []
    seen_ids: set[str] = set()
    for line_number, raw in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{file_path}:{line_number}: invalid JSON ({error})") from error

        question = _parse_question(payload, f"{file_path}:{line_number}")
        if question.question_id in seen_ids:
            raise ValueError(f"{file_path}:{line_number}: duplicate question_id {question.question_id!r}")
        seen_ids.add(question.question_id)
        questions.append(question)

    if not questions:
        raise ValueError(f"Gold set is empty: {file_path}")
    return tuple(questions)


def _parse_question(payload: object, where: str) -> GoldQuestion:
    if not isinstance(payload, dict):
        raise ValueError(f"{where}: expected a JSON object")

    for required in ("question_id", "question", "answerable"):
        if required not in payload:
            raise ValueError(f"{where}: missing required field {required!r}")

    answerable = payload["answerable"]
    if not isinstance(answerable, bool):
        raise ValueError(f"{where}: 'answerable' must be true or false")

    answers = tuple(str(item) for item in payload.get("answers", ()))
    if answerable and not answers:
        raise ValueError(f"{where}: answerable questions need at least one entry in 'answers'")
    if not answerable and answers:
        raise ValueError(f"{where}: unanswerable questions must have an empty 'answers'")

    rejections = tuple(str(item) for item in payload.get("rejections", ()))
    traps = tuple(str(item) for item in payload.get("traps", ()))
    if answerable and (rejections or traps):
        raise ValueError(f"{where}: 'rejections' and 'traps' are for unanswerable questions only")

    return GoldQuestion(
        question_id=str(payload["question_id"]),
        question=str(payload["question"]),
        answerable=answerable,
        answers=answers,
        supporting_doc_ids=tuple(str(item) for item in payload.get("supporting_doc_ids", ())),
        notes=str(payload.get("notes", "")),
        rejections=rejections,
        traps=traps,
    )
