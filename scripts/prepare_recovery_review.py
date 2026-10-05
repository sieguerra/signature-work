"""Build the blinded review packets and the trace-side gate table.

The packets contain the question and the answers a reviewer may see.
They do not contain gold, verifier labels, or the recovery action.
The feature table is for scoring after a human file exists. It is not a
review packet.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from swrag.orchestration.loop import is_abstention
from swrag.recovery_benchmark.gate_sim import CANDIDATES
from swrag.recovery_benchmark.necessity import (
    NONTRIGGER_LIMIT,
    assert_analysis_ids,
    assert_blind_payload,
    select_nontrigger_ids,
    unnecessary_cost,
)
from swrag.recovery_benchmark.protocol import DEMO_CORPUS_ID, RUN_ID, SEED

PHASE = "phase75-20261006"
KNOWN = ("dku-008", "dku-032", "ls-016", "nw-015", "og-016", "gold-030", "og-004", "dku-053", "dku-055", "dku-012", "dku-045", "seed-009")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    phase7 = root / "experiments" / "recovery-benchmark" / "runs" / RUN_ID
    out = root / "experiments" / "recovery-benchmark" / "runs" / PHASE
    packet = root / "tools" / "recovery-review" / "packet"
    out.mkdir(parents=True, exist_ok=True)
    packet.mkdir(parents=True, exist_ok=True)

    split = json.loads((phase7 / "question_split.json").read_text(encoding="utf-8"))
    runs = [json.loads(line) for line in (phase7 / "run_results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    attempts = [
        json.loads(line)
        for line in (phase7 / "attempt_results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    holdout = {row["logical_id"] for row in split["questions"] if row.get("panel") == "future_holdout"}
    triggered_ids = [row["logical_id"] for row in runs if row.get("recovered")]
    nontrigger_ids = select_nontrigger_ids(runs, limit=NONTRIGGER_LIMIT, seed=SEED)
    assert_analysis_ids(triggered_ids + nontrigger_ids, holdout_ids=holdout)

    triggered_src = phase7 / "human_review_sample.jsonl"
    triggered_rows = [
        json.loads(line) for line in triggered_src.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    for row in triggered_rows:
        assert_blind_payload(row)
    _write_jsonl(out / "triggered_review.jsonl", triggered_rows)
    shutil.copyfile(out / "triggered_review.jsonl", packet / "triggered.jsonl")

    by_trace = _traces(root / "experiments" / "recovery-benchmark" / "traces")
    by_id = {row["logical_id"]: row for row in runs}
    nontrigger_rows = []
    key_rows = []
    for number, logical_id in enumerate(nontrigger_ids, start=1):
        row = by_id[logical_id]
        payload = by_trace[(row["corpus_id"], Path(row["source"]).stem, row["question_id"])]
        blinded = _before_row(payload, review_id=f"N{number:03d}")
        assert_blind_payload(blinded)
        nontrigger_rows.append(blinded)
        key_rows.append({"review_id": blinded["review_id"], "logical_id": logical_id, "packet": "nontrigger"})
    old_key = [
        json.loads(line)
        for line in (phase7 / "human_review_key.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in old_key:
        key_rows.append({**row, "packet": "triggered"})
    _write_jsonl(out / "nontrigger_review.jsonl", nontrigger_rows)
    shutil.copyfile(out / "nontrigger_review.jsonl", packet / "nontrigger.jsonl")
    _write_jsonl(out / "review_key.jsonl", key_rows)

    v2 = _v2(phase7 / "verifier_run_predictions.jsonl")
    features = [_feature(row, by_trace, attempts, v2) for row in runs]
    if any(row.get("panel") == "future_holdout" for row in features):
        raise SystemExit("refusing to write a feature row from the future holdout")
    _write_jsonl(out / "gate_features.jsonl", features)
    audit = _trace_audit(features)
    _write_json(out / "trace_gate_audit.json", audit)
    print(
        f"triggered {len(triggered_rows)} nontrigger {len(nontrigger_rows)} "
        f"features {len(features)} holdout reserved {len(holdout)}"
    )


def _traces(traces_root: Path) -> dict[tuple[str, str, str], dict]:
    found = {}
    for corpus_dir in sorted(path for path in traces_root.iterdir() if path.is_dir()):
        if corpus_dir.name == "gold-slices":
            continue
        for source_dir in sorted(path for path in corpus_dir.iterdir() if path.is_dir()):
            trace_dir = source_dir / "traces"
            if not trace_dir.is_dir():
                continue
            for path in sorted(trace_dir.glob("*.json")):
                payload = json.loads(path.read_text(encoding="utf-8"))
                found[(corpus_dir.name, source_dir.name, str(payload.get("question_id") or ""))] = payload
    return found


def _before_row(payload: dict, *, review_id: str) -> dict:
    chunks = payload.get("retrieved_chunks") or []
    evidence = "\n\n".join(str(chunk.get("text") or "").strip() for chunk in chunks if str(chunk.get("text") or "").strip())
    return {
        "review_id": review_id,
        "question": payload.get("query") or "",
        "before_evidence": evidence,
        "before_answer": payload.get("answer") or "",
    }


def _v2(path: Path) -> dict[tuple[str, str], str]:
    found = {}
    if not path.exists():
        return found
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("level") not in (None, "run"):
            continue
        logical = str(row.get("logical_id") or "")
        corpus = logical.split(":", 1)[0]
        found[(corpus, str(row.get("question_id") or ""))] = row.get("v2_outcome")
    return found


def _feature(row: dict, traces: dict, attempts: list[dict], v2: dict) -> dict:
    payload = traces[(row["corpus_id"], Path(row["source"]).stem, row["question_id"])]
    initial = payload.get("initial") if isinstance(payload.get("initial"), dict) else {}
    evaluation = initial.get("runtime_evaluation") or payload.get("runtime_evaluation") or {}
    signal = initial.get("retrieval_signal") or payload.get("retrieval_signal") or {}
    before_answer = initial.get("answer") or payload.get("previous_answer") or payload.get("answer") or ""
    attempt_rows = []
    for attempt in payload.get("recovery_attempts") or []:
        usage = attempt.get("usage") if isinstance(attempt.get("usage"), dict) else {}
        attempt_rows.append(
            {
                "action": attempt.get("action"),
                "after_answer": attempt.get("answer") or "",
                "chat_calls": int(usage.get("chat_calls") or 0),
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
                "embedding_tokens": int(usage.get("embedding_tokens") or 0),
                "latency_ms": attempt.get("latency_ms"),
            }
        )
    return {
        "logical_id": row["logical_id"],
        "corpus_id": row["corpus_id"],
        "question_id": row["question_id"],
        "panel": row.get("panel"),
        "triggered": bool(row.get("recovered")),
        "recovered": bool(row.get("recovered")),
        "path": row.get("path"),
        "action": row.get("action"),
        "answerable": row.get("answerable"),
        "gold_label": row.get("gold_label"),
        "gold_label_paraphrase": row.get("gold_label_paraphrase"),
        "gold_label_grounded": row.get("gold_label_grounded"),
        "v1_outcome": row.get("v1_outcome"),
        "v2_outcome": v2.get((row["corpus_id"], row["question_id"])),
        "evidence_sufficient": evaluation.get("evidence_sufficient"),
        "answer_supported": evaluation.get("answer_supported"),
        "weak_top": signal.get("weak_top"),
        "ambiguous_top": signal.get("ambiguous_top"),
        "relative_margin": signal.get("relative_margin"),
        "before_abstained": is_abstention(str(before_answer)),
        "added_latency_ms": row.get("added_latency_ms"),
        "attempts": attempt_rows,
        "attempt_gold": [
            item.get("gold_label")
            for item in attempts
            if item.get("logical_id") == row["logical_id"]
        ],
    }


def _trace_audit(features: list[dict]) -> dict:
    triggered = [row for row in features if row["triggered"]]
    resting = [row for row in features if not row["triggered"]]

    def bucket(row: dict) -> str:
        if row.get("evidence_sufficient") is False and row.get("before_abstained"):
            return "insufficient_and_abstention"
        if row.get("evidence_sufficient") is False:
            return "insufficient_specific_answer"
        if row.get("ambiguous_top") and row.get("evidence_sufficient") is True:
            return "ambiguous_margin_on_accepted_answer"
        if row.get("weak_top"):
            return "weak_top"
        return "other"

    groups: dict[str, list[dict]] = {}
    for row in triggered:
        groups.setdefault(bucket(row), []).append(row)
    mechanical = {}
    for name, rule in CANDIDATES.items():
        skipped = [row for row in triggered if not rule(row)]
        gold_improved_skipped = [
            row["logical_id"] for row in skipped if row.get("gold_label") == "improved"
        ]
        mechanical[name] = {
            "would_still_trigger": sum(1 for row in triggered if rule(row)),
            "would_skip": len(skipped),
            "gold_improved_skipped": gold_improved_skipped,
            "note": "Counted from traces and automatic gold. Not a human result and not a selected rule.",
        }
    return {
        "human_labels_collected": False,
        "n_triggered": len(triggered),
        "n_not_triggered": len(resting),
        "not_triggered_all_judge_accepted": all(
            row.get("evidence_sufficient") is True
            and row.get("answer_supported") is True
            and not row.get("weak_top")
            and not row.get("ambiguous_top")
            for row in resting
        ),
        "trigger_groups": {
            name: {
                "n": len(members),
                "logical_ids": [row["logical_id"] for row in members],
                "recovery_attempt_cost": unnecessary_cost(
                    [{**row, "before_state": "correct"} for row in members]
                ),
                "cost_note": "Cost of this signal group. Not a human judgment that the recovery was unnecessary.",
            }
            for name, members in sorted(groups.items())
        },
        "mechanical_candidates_against_automatic_gold": mechanical,
        "known_question_ids_present": [
            row["logical_id"]
            for row in triggered
            if row["question_id"] in KNOWN
        ],
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


if __name__ == "__main__":
    main()
