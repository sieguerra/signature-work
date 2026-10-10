"""Registry and isolated industry corpora. No live OpenAI calls."""

from __future__ import annotations

import json
from pathlib import Path

from swrag.corpus_registry import assert_corpus_readable, load_registry
from swrag.evaluation.gold import load_gold_set
from swrag.ingestion.loader import load_documents

ROOT = Path(__file__).resolve().parents[1]


def test_registry_lists_harbor_dku_and_industry_worlds() -> None:
    entries = load_registry(root=ROOT)
    ids = [entry.id for entry in entries]
    assert ids[0] == "harbor"
    assert "dku" in ids
    assert "northhaven-water" in ids
    assert "kestrel-aero" in ids
    assert len(ids) == len(set(ids))
    assert len(entries) >= 10


def test_every_registered_corpus_loads_and_gold_cites_real_files() -> None:
    seen_question_ids: set[str] = set()
    for entry in load_registry(root=ROOT):
        assert_corpus_readable(entry)
        documents = load_documents(entry.corpus_dir)
        assert len(documents) >= 10
        stems = {document.doc_id for document in documents}
        stems.update(Path(document.path).stem for document in documents)
        if entry.gold_path is None:
            continue
        questions = load_gold_set(entry.gold_path)
        assert questions
        for question in questions:
            assert question.question_id not in seen_question_ids, question.question_id
            seen_question_ids.add(question.question_id)
            missing = set(question.supporting_doc_ids) - stems
            assert not missing, (entry.id, question.question_id, missing)


def test_industry_folders_are_pairwise_distinct() -> None:
    paths = [entry.corpus_dir.resolve() for entry in load_registry(root=ROOT)]
    assert len(paths) == len(set(paths))


def test_every_gold_id_has_an_audit_row() -> None:
    for entry in load_registry(root=ROOT):
        if entry.gold_path is None:
            continue
        audit_path = entry.gold_path.parent / "audit.jsonl"
        assert audit_path.is_file(), audit_path
        audited: set[str] = set()
        for raw in audit_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            payload = json.loads(line)
            audited.add(str(payload["question_id"]))
            assert payload["span_found"] in {"yes", "no", "n/a"}
        gold_ids = {question.question_id for question in load_gold_set(entry.gold_path)}
        missing = gold_ids - audited
        assert not missing, (entry.id, missing)


# The collections scored in the study. Their gold must carry a person's sign-off
# (#99), not the machine substring search the other collections still use.
_STUDY_CORPORA = {"harbor", "dku", "kestrel-aero"}


def test_study_gold_is_signed_off_by_a_person() -> None:
    for entry in load_registry(root=ROOT):
        if entry.id not in _STUDY_CORPORA:
            continue
        audit_path = entry.gold_path.parent / "audit.jsonl"
        for raw in audit_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            payload = json.loads(line)
            assert payload["auditor"] != "substring-search", (entry.id, payload["question_id"])
            assert "student should confirm" not in payload["notes"], (
                entry.id,
                payload["question_id"],
            )
