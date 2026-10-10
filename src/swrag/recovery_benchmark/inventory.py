"""Load registered gold questions. Demo corpora are refused."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from swrag.corpus_registry import load_registry
from swrag.evaluation.gold import load_gold_set
from swrag.recovery_benchmark.protocol import (
    DEMO_CORPUS_ID,
    PHASE6_OBSERVED_GOLD,
    QUESTION_SOURCES,
)
from swrag.verification.v2.protocol import DEV_CORPUS, TEST_CORPUS


class DemoContamination(ValueError):
    """A visual-demo question was offered to the research benchmark."""


@dataclass(frozen=True)
class QuestionRecord:
    """One gold question. ``answers`` is offline and never sent to the runtime."""

    corpus_id: str
    domain: str
    group: str
    question_id: str
    question: str
    answerable: bool
    answers: tuple[str, ...]
    supporting_doc_ids: tuple[str, ...]
    source: str
    gold_path: str
    logical_id: str

    def as_dict(self) -> dict:
        return {
            "corpus_id": self.corpus_id,
            "domain": self.domain,
            "group": self.group,
            "question_id": self.question_id,
            "question": self.question,
            "answerable": self.answerable,
            "answers": list(self.answers),
            "supporting_doc_ids": list(self.supporting_doc_ids),
            "source": self.source,
            "gold_path": self.gold_path,
            "logical_id": self.logical_id,
        }


def load_questions(root: Path) -> tuple[QuestionRecord, ...]:
    """Every registered question file except the visual demo."""
    base = root.resolve()
    found: list[QuestionRecord] = []
    for entry in load_registry(root=base):
        if entry.id == DEMO_CORPUS_ID or "recovery-demo" in str(entry.corpus_dir):
            continue
        if entry.gold_path is None:
            continue
        for path in _question_files(entry.gold_path):
            if DEMO_CORPUS_ID in path.parts or "recovery-demo" in str(path):
                raise DemoContamination(str(path))
            relative = str(path.resolve().relative_to(base))
            source = path.name
            for question in load_gold_set(path):
                found.append(
                    QuestionRecord(
                        corpus_id=entry.id,
                        domain=entry.industry,
                        group=entry.group,
                        question_id=question.question_id,
                        question=question.question,
                        answerable=question.answerable,
                        answers=question.answers,
                        supporting_doc_ids=question.supporting_doc_ids,
                        source=source,
                        gold_path=relative,
                        logical_id=f"{entry.id}:{source}:{question.question_id}",
                    )
                )
    return tuple(found)


def observed_phase6_keys(root: Path) -> set[tuple[str, str]]:
    """Question ids already scored in Phase 6, keyed by corpus."""
    keys: set[tuple[str, str]] = set()
    for relative in PHASE6_OBSERVED_GOLD:
        path = root / relative
        corpus_id = _corpus_for_observed(relative)
        for question in load_gold_set(path):
            keys.add((corpus_id, question.question_id))
    return keys


def runtime_inputs(record: QuestionRecord) -> dict[str, str]:
    """The only field the loop may see. Gold stays out."""
    from swrag.verification.v2.payload import assert_no_gold

    payload = {"question": record.question}
    assert_no_gold(payload)
    return payload


def questions_to_generate(rows: list[dict]) -> list[dict]:
    """Analysis questions that are not duplicates and not demos."""
    leaked = [
        row
        for row in rows
        if row.get("corpus_id") == DEMO_CORPUS_ID or "recovery-demo" in str(row.get("gold_path"))
    ]
    if leaked:
        raise DemoContamination(leaked[0]["logical_id"])
    return [
        row
        for row in rows
        if row.get("panel") == "analysis" and not row.get("duplicate_of")
    ]


def _question_files(gold_path: Path) -> tuple[Path, ...]:
    parent = gold_path.parent
    found = []
    for name in QUESTION_SOURCES:
        path = parent / name
        if path.is_file():
            found.append(path)
    if gold_path.is_file() and gold_path not in found:
        found.append(gold_path)
    return tuple(found)


def _corpus_for_observed(relative: str) -> str:
    if relative.startswith("datasets/dku/"):
        return TEST_CORPUS
    if relative.startswith("datasets/kestrel-aero/"):
        return DEV_CORPUS
    raise ValueError(f"unmapped Phase 6 gold path: {relative}")
