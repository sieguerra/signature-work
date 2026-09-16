"""Recovery gold split (issue #32). Does not edit Harbor or DKU questions.jsonl."""

from __future__ import annotations

import json
from pathlib import Path

from swrag.corpus_registry import load_registry
from swrag.evaluation.gold import load_gold_set
from swrag.experiments.benchmark import load_benchmark_config

ROOT = Path(__file__).resolve().parents[1]
DKU_MAIN = ROOT / "datasets" / "dku" / "gold" / "questions.jsonl"
DKU_RECOVERY = ROOT / "datasets" / "dku" / "gold" / "recovery.jsonl"
KESTREL_MAIN = ROOT / "datasets" / "kestrel-aero" / "gold" / "questions.jsonl"
KESTREL_RECOVERY = ROOT / "datasets" / "kestrel-aero" / "gold" / "recovery.jsonl"
HARBOR = ROOT / "datasets" / "gold" / "questions.jsonl"
SNAPSHOT = ROOT / "experiments" / "results" / "20260910T070623" / "comparison.json"
RECOVERY_CONFIG = ROOT / "experiments" / "configs" / "v2_dku_recovery_vs_loop.json"

SOURCE_LEAKS = (
    "january 2025",
    "locations and hours",
    "2021 handbook",
    "august 2021",
    "current page",
    "current locations",
    "2025 traveler",
    "2018 traveler",
    "2018 issue",
    "2025 issue",
)


def test_harbor_gold_and_snapshot_are_untouched() -> None:
    questions = load_gold_set(HARBOR)
    assert len(questions) == 32
    assert all(not item.question_id.startswith("dku-") for item in questions)
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert payload["name"] == "v1_baseline_vs_loop"
    assert payload["verification_vs_gold"]["n_with_runtime_verification"] == 5


def test_dku_main_gold_count_is_unchanged() -> None:
    questions = load_gold_set(DKU_MAIN)
    assert len(questions) == 40
    assert {item.question_id for item in questions} == {f"dku-{i:03d}" for i in range(1, 41)}


def test_dku_recovery_ids_are_new_and_do_not_name_the_source() -> None:
    main_ids = {item.question_id for item in load_gold_set(DKU_MAIN)}
    questions = load_gold_set(DKU_RECOVERY)
    assert len(questions) == 12
    assert sum(item.answerable for item in questions) == 9
    assert sum(not item.answerable for item in questions) == 3
    for question in questions:
        assert question.question_id not in main_ids
        assert question.question_id.startswith("dku-")
        number = int(question.question_id.split("-")[1])
        assert number >= 41
        lowered = question.question.lower()
        for leak in SOURCE_LEAKS:
            assert leak not in lowered, (question.question_id, leak)


def test_kestrel_recovery_ids_are_new_and_underspecified() -> None:
    main_ids = {item.question_id for item in load_gold_set(KESTREL_MAIN)}
    questions = load_gold_set(KESTREL_RECOVERY)
    assert len(questions) == 3
    assert sum(not item.answerable for item in questions) == 1
    for question in questions:
        assert question.question_id not in main_ids
        assert question.question_id.startswith("ka-")
        lowered = question.question.lower()
        for leak in SOURCE_LEAKS:
            assert leak not in lowered, (question.question_id, leak)


def test_recovery_gold_cites_real_docs_and_keeps_short_answers() -> None:
    dku_docs = {path.stem for path in (ROOT / "datasets" / "dku" / "corpus").glob("*.txt")}
    kestrel_docs = {
        path.stem for path in (ROOT / "datasets" / "kestrel-aero" / "corpus").glob("*.txt")
    }
    for path, stems in ((DKU_RECOVERY, dku_docs), (KESTREL_RECOVERY, kestrel_docs)):
        for question in load_gold_set(path):
            for answer in question.answers:
                assert len(answer) <= 40, (question.question_id, answer)
            if question.answerable:
                assert question.supporting_doc_ids
                missing = set(question.supporting_doc_ids) - stems
                assert not missing, (question.question_id, missing)
            else:
                assert question.supporting_doc_ids == ()


def test_recovery_ids_do_not_collide_with_registered_gold() -> None:
    registered: set[str] = set()
    for entry in load_registry(root=ROOT):
        if entry.gold_path is None:
            continue
        registered.update(item.question_id for item in load_gold_set(entry.gold_path))
    for path in (DKU_RECOVERY, KESTREL_RECOVERY):
        for question in load_gold_set(path):
            assert question.question_id not in registered, question.question_id


def test_recovery_benchmark_config_uses_top_k_one() -> None:
    payload = load_benchmark_config(RECOVERY_CONFIG, repo_root=ROOT)
    assert payload["name"] == "v2_dku_recovery_vs_loop"
    assert Path(payload["gold_path"]) == DKU_RECOVERY
    assert payload["top_k"] == 1
    assert Path(payload["corpus_dir"]) == ROOT / "datasets" / "dku" / "corpus"
