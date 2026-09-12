"""DKU gold-set tests. No API calls. Harbor tests stay in test_gold.py."""

from __future__ import annotations

from pathlib import Path

from swrag.evaluation.gold import load_gold_set

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "datasets" / "dku" / "gold" / "questions.jsonl"
CORPUS = ROOT / "datasets" / "dku" / "corpus"


def test_dku_gold_has_both_classes() -> None:
    questions = load_gold_set(GOLD)
    assert len(questions) == 44
    assert sum(item.answerable for item in questions) == 34
    assert sum(not item.answerable for item in questions) == 10
    assert {item.question_id for item in questions} >= {"dku-041", "dku-042", "dku-043", "dku-044"}


def test_dku_answers_obey_the_answerable_flag() -> None:
    for question in load_gold_set(GOLD):
        assert bool(question.answers) == question.answerable


def test_dku_answerable_questions_cite_real_corpus_documents() -> None:
    corpus_ids = {path.stem for path in CORPUS.glob("*.txt")}
    questions = load_gold_set(GOLD)
    cited: set[str] = set()
    for question in questions:
        if question.answerable:
            assert question.supporting_doc_ids, question.question_id
            missing = set(question.supporting_doc_ids) - corpus_ids
            assert not missing, (question.question_id, missing)
            cited.update(question.supporting_doc_ids)
        else:
            assert question.supporting_doc_ids == ()
    assert corpus_ids <= cited, f"unused DKU docs: {corpus_ids - cited}"


def test_dku_gold_answers_are_short_enough_for_exact_match() -> None:
    for question in load_gold_set(GOLD):
        for answer in question.answers:
            assert len(answer) <= 40, (question.question_id, answer)
