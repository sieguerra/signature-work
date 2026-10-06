#!/usr/bin/env python3
"""Phase 8A recovery policies. The product default stays v1.

Retrospective scores replay the frozen human-reviewed first passes.
Fresh runs execute only the policies whose action order changes, starting
from those same first-pass states. The future holdout is refused.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from swrag.corpus_registry import load_registry
from swrag.diagnosis.diagnose import diagnose_runtime
from swrag.evaluation.retrieval_signal import RetrievalSignal
from swrag.pipeline.baseline import QueryState
from swrag.recovery.policy import (
    POLICY_V1,
    POLICY_V2A_COMBINED,
    POLICY_V2A_EXPAND_FIRST,
    POLICY_V2A_MARGIN,
)
from swrag.recovery_benchmark.protocol import MAX_RECOVERIES, TOP_K
from swrag.recovery_benchmark.v2a import PROMOTION_RULES, retrospective_report
from swrag.types import Chunk, GenerationResult, RetrievalResult, RuntimeEvaluation, ScoredChunk

PHASE = "phase8a-20261007"
REVIEW = "phase75-20261006"
POLICIES = (POLICY_V1, POLICY_V2A_MARGIN, POLICY_V2A_EXPAND_FIRST, POLICY_V2A_COMBINED)
FRESH_POLICIES = (POLICY_V2A_EXPAND_FIRST, POLICY_V2A_COMBINED)
REPEAT_IDS = ("dku-053", "dku-012", "dku-045", "dku-055", "seed-009", "dku-031", "dku-035", "sw-014")


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Score Recovery Engine v2A without changing the default.")
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--retrospective", action="store_true")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--holdout", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args(argv)
    if not any((args.freeze, args.retrospective, args.fresh, args.holdout)):
        args.freeze = True
        args.retrospective = True
    out = root / "experiments" / "recovery-v2a" / PHASE
    out.mkdir(parents=True, exist_ok=True)
    rows = _joined_rows(root)
    if any(row.get("panel") == "future_holdout" for row in rows):
        raise SystemExit("refusing the future holdout")
    if args.freeze:
        _write(out / "frozen_manifest.json", _manifest(rows))
        _write(
            out / "promotion_criteria.json",
            {
                "written_before_holdout": True,
                "holdout_opened": False,
                "rules": list(PROMOTION_RULES),
            },
        )
        print(f"froze {len(rows)} human-reviewed rows")
    if args.retrospective:
        report = retrospective_report(rows, POLICIES)
        _write(out / "retrospective.json", report)
        for policy, block in report.items():
            print(
                policy,
                "triggered",
                block["triggered"],
                "precision",
                block["gate_precision"],
                "missed",
                block["needed_missed"],
            )
    if args.fresh:
        if not (out / "promotion_criteria.json").is_file():
            raise SystemExit("write promotion criteria before fresh runs")
        _fresh(root, out, rows, repeats=args.repeats)
    if args.holdout:
        _holdout(root, out)
    return 0


def _joined_rows(root: Path) -> list[dict]:
    review = root / "experiments" / "recovery-benchmark" / "runs" / REVIEW
    key = {
        json.loads(line)["review_id"]: json.loads(line)
        for line in (review / "review_key.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    features = {
        json.loads(line)["logical_id"]: json.loads(line)
        for line in (review / "gate_features.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    labels = []
    for name in ("human_labels.jsonl", "human_labels_nontrigger.jsonl"):
        labels.extend(
            json.loads(line)
            for line in (review / name).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    rows = []
    for label in labels:
        meta = key[label["review_id"]]
        feature = features[meta["logical_id"]]
        if feature.get("panel") == "future_holdout":
            raise SystemExit("refusing a holdout label")
        path = str(feature.get("path") or "")
        historical = path.split(">")[0] if path else ("accept" if not feature.get("triggered") else "")
        rows.append({**feature, **label, "historical_action": historical})
    return rows


def _manifest(rows: list[dict]) -> dict:
    return {
        "review": REVIEW,
        "n": len(rows),
        "policies": list(POLICIES),
        "default_policy": POLICY_V1,
        "top_k": TOP_K,
        "max_recoveries": MAX_RECOVERIES,
        "expand_first": {
            "first_action_when_evidence_insufficient": "expand",
            "first_search_query": "original",
            "later_rewrite_top_k": "expanded",
            "budget": MAX_RECOVERIES,
        },
        "rows": [
            {
                "review_id": row["review_id"],
                "logical_id": row["logical_id"],
                "question_id": row["question_id"],
                "corpus_id": row["corpus_id"],
                "before_state": row["before_state"],
                "transition": row.get("transition") or "",
                "path": row.get("path") or "",
                "triggered": row.get("triggered"),
                "evidence_sufficient": row.get("evidence_sufficient"),
                "answer_supported": row.get("answer_supported"),
                "weak_top": row.get("weak_top"),
                "ambiguous_top": row.get("ambiguous_top"),
                "relative_margin": row.get("relative_margin"),
                "panel": row.get("panel"),
            }
            for row in rows
        ],
    }


def _fresh(root: Path, out: Path, rows: list[dict], *, repeats: int) -> None:
    from dotenv import load_dotenv
    from openai import OpenAI

    from swrag.config import load_provider_config
    from swrag.evaluation.llm_judge import LLMJudge
    from swrag.generation.openai_generator import OpenAIGenerator
    from swrag.orchestration.loop import run_with_recovery
    from swrag.pipeline.baseline import build_corpus_index
    from swrag.recovery.regenerate import ConstrainedRegenerator
    from swrag.recovery.rewrite import LLMQueryRewriter
    from swrag.retrieval.openai_embedder import OpenAIEmbedder

    load_dotenv(root / ".env")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set; refusing fresh recovery runs.")
    targets = []
    for index, row in enumerate(rows):
        if row.get("panel") == "future_holdout":
            raise SystemExit("refusing the future holdout")
        policies = [policy for policy in FRESH_POLICIES if _would_run(row, policy)]
        if not policies:
            continue
        times = repeats if row["question_id"] in REPEAT_IDS else 1
        for repeat in range(times):
            ordered = policies[repeat % len(policies) :] + policies[: repeat % len(policies)]
            targets.append((index, repeat, ordered, row))
    log_path = out / "fresh.jsonl"
    done = set()
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            done.add((item["question_id"], item["policy"], item["repeat"]))
    entries = {entry.id: entry for entry in load_registry(root=root)}
    traces = _trace_index(root / "experiments" / "recovery-benchmark" / "traces")
    config = load_provider_config()
    client = OpenAI(base_url=config.base_url, timeout=120.0, max_retries=1)
    embedder = OpenAIEmbedder(client=client, config=config)
    generator = OpenAIGenerator(client=client, config=config)
    rewriter = LLMQueryRewriter(client=client, config=config)
    regenerator = ConstrainedRegenerator(client=client, config=config)
    judge = LLMJudge(client=client, config=config)
    indexes: dict[str, object] = {}
    with log_path.open("a", encoding="utf-8") as handle:
        for index, repeat, ordered, row in targets:
            corpus_id = row["corpus_id"]
            if corpus_id not in indexes:
                print(f"index {corpus_id}", flush=True)
                indexes[corpus_id] = build_corpus_index(entries[corpus_id].corpus_dir, embedder)
            trace_path = traces.get((corpus_id, row["question_id"]))
            if trace_path is None:
                print(f"missing trace {corpus_id} {row['question_id']}", flush=True)
                continue
            payload = json.loads(trace_path.read_text(encoding="utf-8"))
            for position, policy in enumerate(ordered):
                key = (row["question_id"], policy, repeat)
                if key in done:
                    continue
                print(f"fresh {row['question_id']} {policy} repeat {repeat} position {position}", flush=True)
                result = run_with_recovery(
                    str(payload.get("query") or ""),
                    corpus_dir=entries[corpus_id].corpus_dir,
                    output_dir=out / "traces" / policy,
                    top_k=TOP_K,
                    max_recoveries=MAX_RECOVERIES,
                    embedder=embedder,
                    generator=generator,
                    judge=judge,
                    regenerator=regenerator,
                    rewriter=rewriter,
                    question_id=row["question_id"],
                    index=indexes[corpus_id],
                    recovery_policy=policy,
                    prepared_state=_state_from_trace(payload),
                )
                record = _compact(result.trace_path, row, policy, repeat, position)
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                done.add(key)


def _would_run(row: dict, policy: str) -> bool:
    from swrag.recovery_benchmark.v2a import replay_action

    return replay_action(row, policy) != "accept"


def _trace_index(root: Path) -> dict[tuple[str, str], Path]:
    found: dict[tuple[str, str], Path] = {}
    for path in root.glob("*/*/traces/*.json"):
        corpus_id = path.parts[-4]
        payload = json.loads(path.read_text(encoding="utf-8"))
        question_id = str(payload.get("question_id") or "")
        if question_id and (corpus_id, question_id) not in found:
            found[(corpus_id, question_id)] = path
    return found


def _state_from_trace(payload: dict) -> QueryState:
    initial = payload.get("initial") if isinstance(payload.get("initial"), dict) else {}
    source = initial if initial.get("retrieved_chunks") else payload
    chunks = []
    for row in source.get("retrieved_chunks") or []:
        chunks.append(
            ScoredChunk(
                chunk=Chunk(
                    chunk_id=str(row.get("chunk_id") or ""),
                    doc_id=str(row.get("doc_id") or ""),
                    title=str(row.get("title") or ""),
                    text=str(row.get("text") or ""),
                    start_char=0,
                    end_char=0,
                ),
                score=float(row.get("score") or 0),
            )
        )
    retrieval = RetrievalResult(
        query=str(payload.get("query") or ""),
        chunks=tuple(chunks),
        top_k=int(source.get("top_k") or payload.get("top_k") or TOP_K),
        embedding_model=str(payload.get("embedding_model") or ""),
    )
    evaluation = _evaluation(source.get("runtime_evaluation"))
    signal_payload = source.get("retrieval_signal")
    signal = None
    if isinstance(signal_payload, dict):
        signal = RetrievalSignal(
            top_score=signal_payload.get("top_score"),
            runner_up_score=signal_payload.get("runner_up_score"),
            relative_margin=signal_payload.get("relative_margin"),
            weak_top=bool(signal_payload.get("weak_top")),
            ambiguous_top=bool(signal_payload.get("ambiguous_top")),
            reason=str(signal_payload.get("reason") or ""),
            detector=str(signal_payload.get("detector") or "retrieval-score"),
        )
    return QueryState(
        query=str(payload.get("query") or ""),
        retrieval=retrieval,
        generation=GenerationResult(
            answer=str(source.get("answer") or ""),
            model=str(source.get("model") or ""),
        ),
        runtime_evaluation=evaluation,
        diagnosis=diagnose_runtime(evaluation) if evaluation is not None else None,
        retrieval_signal=signal,
    )


def _evaluation(payload: object) -> RuntimeEvaluation | None:
    if not isinstance(payload, dict):
        return None
    return RuntimeEvaluation(
        evidence_sufficient=bool(payload.get("evidence_sufficient")),
        answer_supported=payload.get("answer_supported"),
        sufficiency_rationale=str(payload.get("sufficiency_rationale") or ""),
        support_rationale=str(payload.get("support_rationale") or ""),
        judge=str(payload.get("judge") or ""),
        model=str(payload.get("model") or ""),
    )


def _compact(path: Path, row: dict, policy: str, repeat: int, position: int) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    attempts = payload.get("recovery_attempts") or []
    return {
        "question_id": row["question_id"],
        "corpus_id": row["corpus_id"],
        "policy": policy,
        "repeat": repeat,
        "position": position,
        "before_state": row.get("before_state"),
        "historical_transition": row.get("transition") or "",
        "actions": [item.get("action") for item in attempts],
        "attempt_answers": [item.get("answer") for item in attempts],
        "attempt_outcomes": [
            (item.get("verification") or {}).get("outcome") if isinstance(item.get("verification"), dict) else None
            for item in attempts
        ],
        "final_answer": payload.get("answer"),
        "verification": (payload.get("verification") or {}).get("outcome")
        if isinstance(payload.get("verification"), dict)
        else None,
        "ambiguous_top": ((payload.get("initial") or {}).get("retrieval_signal") or payload.get("retrieval_signal") or {}).get(
            "ambiguous_top"
        ),
        "latency_ms": payload.get("latency_ms"),
        "usage": payload.get("usage"),
        "trace": str(path),
    }


def _holdout(root: Path, out: Path) -> None:
    """One pass of v1 and the margin policy. No other candidate. No retuning."""
    if not (out / "promotion_criteria.json").is_file():
        raise SystemExit("promotion criteria were not frozen")
    selected = out / "selected_candidate.json"
    if not selected.is_file():
        raise SystemExit("select the candidate before opening the holdout")
    choice = json.loads(selected.read_text(encoding="utf-8"))
    policy = choice.get("policy")
    if policy != POLICY_V2A_MARGIN:
        raise SystemExit("this holdout runner only compares v1 with the margin policy")
    from dotenv import load_dotenv
    from openai import OpenAI

    from swrag.config import load_provider_config
    from swrag.evaluation.llm_judge import LLMJudge
    from swrag.generation.openai_generator import OpenAIGenerator
    from swrag.orchestration.loop import run_with_recovery
    from swrag.pipeline.baseline import build_corpus_index
    from swrag.recovery.regenerate import ConstrainedRegenerator
    from swrag.recovery.rewrite import LLMQueryRewriter
    from swrag.retrieval.openai_embedder import OpenAIEmbedder

    load_dotenv(root / ".env")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set; refusing the holdout run.")
    split = json.loads(
        (root / "experiments" / "recovery-benchmark" / "runs" / "phase7-20261006" / "question_split.json").read_text(
            encoding="utf-8"
        )
    )
    questions = [row for row in split["questions"] if row.get("panel") == "future_holdout"]
    if len(questions) != 39:
        raise SystemExit(f"expected 39 holdout questions, found {len(questions)}")
    entries = {entry.id: entry for entry in load_registry(root=root)}
    config = load_provider_config()
    client = OpenAI(base_url=config.base_url, timeout=120.0, max_retries=1)
    embedder = OpenAIEmbedder(client=client, config=config)
    generator = OpenAIGenerator(client=client, config=config)
    judge = LLMJudge(client=client, config=config)
    rewriter = LLMQueryRewriter(client=client, config=config)
    regenerator = ConstrainedRegenerator(client=client, config=config)
    indexes: dict[str, object] = {}
    log_path = out / "holdout.jsonl"
    done = set()
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                done.add((item["question_id"], item["policy"]))
    policies = (POLICY_V1, POLICY_V2A_MARGIN)
    with log_path.open("a", encoding="utf-8") as handle:
        for index, row in enumerate(questions):
            ordered = policies[index % 2 :] + policies[: index % 2]
            corpus_id = row["corpus_id"]
            if corpus_id not in indexes:
                print(f"index {corpus_id}", flush=True)
                indexes[corpus_id] = build_corpus_index(entries[corpus_id].corpus_dir, embedder)
            for position, policy in enumerate(ordered):
                if (row["question_id"], policy) in done:
                    continue
                print(f"holdout {row['question_id']} {policy} position {position}", flush=True)
                result = run_with_recovery(
                    row["question"],
                    corpus_dir=entries[corpus_id].corpus_dir,
                    output_dir=out / "holdout-traces" / policy,
                    top_k=TOP_K,
                    max_recoveries=MAX_RECOVERIES,
                    embedder=embedder,
                    generator=generator,
                    judge=judge,
                    regenerator=regenerator,
                    rewriter=rewriter,
                    question_id=row["question_id"],
                    index=indexes[corpus_id],
                    recovery_policy=policy,
                )
                payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
                attempts = payload.get("recovery_attempts") or []
                initial = payload.get("initial") if isinstance(payload.get("initial"), dict) else {}
                handle.write(
                    json.dumps(
                        {
                            "question_id": row["question_id"],
                            "corpus_id": corpus_id,
                            "policy": policy,
                            "position": position,
                            "actions": [item.get("action") for item in attempts],
                            "before_answer": initial.get("answer") if attempts else payload.get("answer"),
                            "final_answer": payload.get("answer"),
                            "verification": (payload.get("verification") or {}).get("outcome")
                            if isinstance(payload.get("verification"), dict)
                            else None,
                            "recovery_action": (payload.get("recovery") or {}).get("action"),
                            "ambiguous_top": (payload.get("retrieval_signal") or {}).get("ambiguous_top"),
                            "evidence_sufficient": (payload.get("runtime_evaluation") or {}).get("evidence_sufficient")
                            if not attempts
                            else (payload.get("initial") or {}).get("runtime_evaluation", {}).get("evidence_sufficient"),
                            "latency_ms": payload.get("latency_ms"),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                handle.flush()
                done.add((row["question_id"], policy))


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
