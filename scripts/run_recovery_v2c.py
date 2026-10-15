"""Run Phase 8C policies. Development first. Holdout only after a frozen selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from swrag.experiments.guard import refuse_committed
from swrag.evaluation.llm_judge import LLMJudge
from swrag.orchestration.loop import run_with_recovery
from swrag.pipeline.baseline import build_corpus_index
from swrag.recovery.policy import (
    POLICY_V1,
    POLICY_V2A_MARGIN,
    POLICY_V2C_EXPAND_STOP,
    POLICY_V2C_GAP_AWARE,
)
from swrag.recovery_benchmark.v2c import assert_runtime_kwargs, score_case, summarize

ROOT = Path(__file__).resolve().parents[1]
GAP = ROOT / "experiments/recovery-benchmark/gap-aware"
OUT = GAP / "phase8c-20261007"
DEV_POLICIES = (POLICY_V1, POLICY_V2A_MARGIN, POLICY_V2C_EXPAND_STOP, POLICY_V2C_GAP_AWARE)


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--regressions", action="store_true")
    parser.add_argument("--select", action="store_true")
    parser.add_argument("--holdout", action="store_true")
    parser.add_argument(
        "--overwrite-committed",
        action="store_true",
        help="Allow replacing the committed phase8c panels.",
    )
    args = parser.parse_args()
    if (args.development or args.regressions or args.select) and not args.holdout:
        refuse_committed(OUT, overwrite=args.overwrite_committed)
    if args.holdout:
        _require_selection()
        criteria = json.loads((GAP / "promotion_criteria.json").read_text())
        if criteria.get("holdout_opened"):
            raise SystemExit("holdout was already opened")
        criteria["holdout_opened"] = True
        (GAP / "promotion_criteria.json").write_text(json.dumps(criteria, indent=2) + "\n")
        split = json.loads((GAP / "split.json").read_text())
        split["status"] = "opened_once"
        split["outcomes_inspected"] = True
        (GAP / "split.json").write_text(json.dumps(split, indent=2) + "\n")
        _run_split("holdout", (POLICY_V1, _selected_policy()))
        return
    if args.select:
        _select()
        return
    if args.development:
        _run_split("development", DEV_POLICIES)
    if args.regressions:
        _run_regressions()
    if not any((args.development, args.regressions, args.select, args.holdout)):
        raise SystemExit("choose --development, --regressions, --select, or --holdout")


def _run_split(panel: str, policies: tuple[str, ...]) -> None:
    if panel == "holdout":
        _require_selection()
    rows = [
        json.loads(line)
        for line in (GAP / "questions.jsonl").read_text().splitlines()
        if line.strip() and json.loads(line)["panel"] == panel
    ]
    # Re-parse once. The double json.loads above is clumsy; filter cleanly.
    rows = [json.loads(line) for line in (GAP / "questions.jsonl").read_text().splitlines() if line.strip()]
    rows = [row for row in rows if row["panel"] == panel]
    records = []
    indexes = {}
    judge = LLMJudge()
    for row in rows:
        for policy in policies:
            records.append(_execute(row, policy, indexes, repeat=0, judge=judge))
            print(panel, row["question_id"], policy, records[-1]["actions"], flush=True)
    path = OUT / f"{panel}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    by_policy = {}
    for policy in policies:
        subset = [record for record in records if record["policy"] == policy]
        by_policy[policy] = {
            "summary": summarize(subset),
            "latency_ms": _latency(subset),
            "usage": _usage(subset),
        }
    (OUT / f"{panel}_summary.json").write_text(json.dumps(by_policy, indent=2) + "\n")
    print(f"wrote {path}")


def _run_regressions() -> None:
    rows = json.loads((GAP / "regressions.json").read_text())
    indexes = {}
    records = []
    judge = LLMJudge()
    for row in rows:
        repeats = 2 if row["question_id"] in {"dku-053", "dku-012"} else 1
        for repeat in range(repeats):
            for policy in DEV_POLICIES:
                record = _execute(row, policy, indexes, repeat=repeat, judge=judge)
                record["expect"] = row["expect"]
                records.append(record)
                print("regression", row["question_id"], repeat, policy, record["actions"], flush=True)
    path = OUT / "regressions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    print(f"wrote {path}")


def _execute(row: dict, policy: str, indexes: dict, *, repeat: int, judge: LLMJudge) -> dict:
    corpus = ROOT / row["corpus_dir"]
    if str(corpus) not in indexes:
        indexes[str(corpus)] = build_corpus_index(corpus)
    kwargs = {
        "query": row["question"],
        "corpus_dir": corpus,
        "output_dir": OUT / "traces" / policy,
        "top_k": 4,
        "max_recoveries": 2,
        "question_id": row["question_id"],
        "recovery_policy": policy,
        "index": indexes[str(corpus)],
        "judge": judge,
    }
    assert_runtime_kwargs({key: value for key, value in kwargs.items() if key != "index"})
    result = run_with_recovery(**kwargs)
    payload = json.loads(result.trace_path.read_text())
    attempts = payload.get("recovery_attempts") or []
    actions = [item.get("action") for item in attempts]
    answer = str(payload.get("answer") or "")
    scored = {}
    if "stratum" in row:
        scored = score_case(row, answer, actions=actions)
    added = sum(float(item.get("latency_ms") or 0) for item in attempts)
    usage = _sum_usage(attempts)
    return {
        "question_id": row["question_id"],
        "policy": policy,
        "repeat": repeat,
        "panel": row.get("panel", "regression"),
        "stratum": row.get("stratum"),
        "actions": actions,
        "answer": answer,
        "latency_ms": payload.get("latency_ms"),
        "added_latency_ms": added,
        "usage": usage,
        "success": scored.get("success"),
        "kind": scored.get("kind"),
        "rewrite_ran": "rewrite" in actions,
        "recovery_actions": scored.get("recovery_actions", sum(action != "abstain" for action in actions)),
    }


def _select() -> None:
    summary = json.loads((OUT / "development_summary.json").read_text())
    criteria = json.loads((GAP / "promotion_criteria.json").read_text())
    if criteria.get("holdout_opened"):
        raise SystemExit("holdout was already opened")
    v1 = summary[POLICY_V1]["summary"]
    choice = None
    notes = {}
    for policy in (POLICY_V2C_GAP_AWARE, POLICY_V2C_EXPAND_STOP):
        report = summary[policy]["summary"]
        ok = _meets(v1, report)
        ok["preserved_dku_053_and_dku_012"] = _preserved_library_recoveries(policy)
        notes[policy] = ok
        if choice is None and all(ok.values()):
            choice = policy
    selected = {
        "selected_before_holdout": True,
        "policy": choice,
        "checks": notes,
        "rule": "gap-aware first, then expand-then-stop, and only if every frozen check passes",
    }
    (OUT / "selected_candidate.json").write_text(json.dumps(selected, indent=2) + "\n")
    print(json.dumps(selected, indent=2))


def _meets(baseline: dict, candidate: dict) -> dict:
    def successes(report: dict, stratum: str) -> int:
        return int(report["by_stratum"][stratum]["successes"])

    return {
        "recoverable_not_worse": candidate["answer_recovery"]["successes"] >= baseline["answer_recovery"]["successes"],
        "fewer_gap_recovery_actions": candidate["recovery_actions_on_gaps"] < baseline["recovery_actions_on_gaps"],
        "neighbor_not_worse": successes(candidate, "neighbor_fact") >= successes(baseline, "neighbor_fact"),
        "conflict_not_worse": successes(candidate, "version_conflict") >= successes(baseline, "version_conflict"),
        "expand_not_worse": successes(candidate, "expand_recoverable") >= successes(baseline, "expand_recoverable"),
    }


def _preserved_library_recoveries(policy: str) -> bool:
    """Reject a candidate that drops either known library recovery on either repeat."""
    spec = {
        row["question_id"]: row["required_substrings"]
        for row in json.loads((GAP / "regressions.json").read_text())
        if row["question_id"] in {"dku-053", "dku-012"}
    }
    seen: set[tuple[str, int]] = set()
    for line in (OUT / "regressions.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["policy"] != policy or row["question_id"] not in spec:
            continue
        answer = row.get("answer") or ""
        if not all(part in answer for part in spec[row["question_id"]]):
            return False
        seen.add((row["question_id"], int(row["repeat"])))
    return seen == {("dku-053", 0), ("dku-053", 1), ("dku-012", 0), ("dku-012", 1)}


def _require_selection() -> None:
    path = OUT / "selected_candidate.json"
    if not path.is_file():
        raise SystemExit("no selected candidate; holdout stays sealed")
    selected = json.loads(path.read_text())
    if not selected.get("policy"):
        raise SystemExit("no policy met the frozen bar; holdout stays sealed")
    criteria = json.loads((GAP / "promotion_criteria.json").read_text())
    if not criteria.get("written_before_holdout"):
        raise SystemExit("promotion criteria were not frozen")


def _selected_policy() -> str:
    return str(json.loads((OUT / "selected_candidate.json").read_text())["policy"])


def _sum_usage(attempts: list[dict]) -> dict:
    total = {"chat_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "embedding_tokens": 0}
    for attempt in attempts:
        usage = attempt.get("usage") or {}
        for key in total:
            value = usage.get(key)
            if isinstance(value, int):
                total[key] += value
    return total


def _latency(records: list[dict]) -> dict:
    values = sorted(float(record["added_latency_ms"]) for record in records)
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean_ms": sum(values) / len(values),
        "p50_ms": values[len(values) // 2],
        "p95_ms": values[min(len(values) - 1, int(round(0.95 * (len(values) - 1))))],
    }


def _usage(records: list[dict]) -> dict:
    total = {"chat_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "embedding_tokens": 0}
    for record in records:
        for key in total:
            total[key] += int(record["usage"].get(key) or 0)
    prompt = total["prompt_tokens"]
    completion = total["completion_tokens"]
    embed = total["embedding_tokens"]
    # Published list price for gpt-4o-mini and text-embedding-3-small. Not an invoice.
    total["estimated_list_usd"] = (prompt * 0.15 + completion * 0.60 + embed * 0.02) / 1_000_000
    return total


if __name__ == "__main__":
    main()
