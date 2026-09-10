"""Config-driven baseline vs evaluation-guided comparison (issue #12).

Runs the same gold set under two conditions, writes timestamped traces that
are never overwritten, and records a comparison snapshot (quality, latency,
token usage, and verification-vs-gold F1 deltas). Does not interpret the
numbers as thesis claims.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from swrag.config import load_provider_config
from swrag.evaluation.judge import GroundingJudge
from swrag.experiments.runner import (
    MODE_LOOP,
    ExperimentSummary,
    QuestionOutcome,
    run_experiment,
)
from swrag.generation.openai_generator import OpenAIGenerator
from swrag.pipeline.baseline import build_corpus_index
from swrag.retrieval.embedder import Embedder
from swrag.retrieval.memory_index import InMemoryIndex
from swrag.retrieval.openai_embedder import OpenAIEmbedder
from swrag.usage import capture_usage

REQUIRED_CONFIG_KEYS = ("name", "gold_path", "corpus_dir", "conditions")


def load_benchmark_config(path: str | Path, *, repo_root: str | Path | None = None) -> dict[str, Any]:
    """Read a JSON experiment config and resolve relative paths against the repo."""
    config_path = Path(path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{config_path}: config must be a JSON object")
    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in payload]
    if missing:
        raise ValueError(f"{config_path}: missing keys {missing}")
    conditions = payload["conditions"]
    if not isinstance(conditions, list) or not conditions:
        raise ValueError(f"{config_path}: 'conditions' must be a non-empty list")
    ids: list[str] = []
    for index, condition in enumerate(conditions):
        if not isinstance(condition, dict) or "id" not in condition or "mode" not in condition:
            raise ValueError(f"{config_path}: conditions[{index}] needs 'id' and 'mode'")
        if condition["id"] in ids:
            raise ValueError(f"{config_path}: duplicate condition id {condition['id']!r}")
        ids.append(str(condition["id"]))

    root = Path(repo_root) if repo_root is not None else _default_repo_root(config_path)
    payload["gold_path"] = str(_resolve(payload["gold_path"], root))
    payload["corpus_dir"] = str(_resolve(payload["corpus_dir"], root))
    payload["_config_path"] = str(config_path)
    payload["_repo_root"] = str(root)
    return payload


def run_benchmark(
    *,
    config_path: str | Path,
    output_root: str | Path,
    results_root: str | Path,
    embedder: Embedder | None = None,
    generate: bool = True,
    judge: GroundingJudge | None = None,
    generator: OpenAIGenerator | None = None,
    regenerator: object | None = None,
    rewriter: object | None = None,
    index: InMemoryIndex | None = None,
    run_label: str | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Run every configured condition on the same gold set.

    The corpus is embedded once and reused. ``judge`` is used only for loop
    conditions. Live OpenAI objects are constructed only when not injected.
    """
    config = load_benchmark_config(config_path, repo_root=repo_root)
    label = run_label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    batch_dir = Path(output_root) / label
    snapshot_dir = Path(results_root) / label
    if batch_dir.exists():
        raise FileExistsError(f"Experiment directory already exists (refusing to overwrite): {batch_dir}")
    if snapshot_dir.exists():
        raise FileExistsError(f"Results directory already exists (refusing to overwrite): {snapshot_dir}")

    resolved_embedder = embedder if embedder is not None else OpenAIEmbedder()
    with capture_usage() as setup_usage:
        resolved_index = index if index is not None else build_corpus_index(
            config["corpus_dir"], resolved_embedder
        )
    top_k = int(config.get("top_k", 4))
    max_recoveries = int(config.get("max_recoveries", 1))

    summaries: dict[str, ExperimentSummary] = {}
    for condition in config["conditions"]:
        mode = str(condition["mode"])
        condition_id = str(condition["id"])
        condition_judge = judge if mode == MODE_LOOP else None
        if mode == MODE_LOOP and condition_judge is None:
            from swrag.evaluation.llm_judge import LLMJudge

            condition_judge = LLMJudge()
        summaries[condition_id] = run_experiment(
            gold_path=config["gold_path"],
            corpus_dir=config["corpus_dir"],
            output_root=batch_dir,
            top_k=top_k,
            embedder=resolved_embedder,
            generate=generate,
            run_label=condition_id,
            judge=condition_judge,
            mode=mode,
            index=resolved_index,
            generator=generator,
            regenerator=regenerator,
            rewriter=rewriter,
            max_recoveries=max_recoveries,
        )

    comparison = build_comparison(config, summaries, setup_usage=setup_usage.snapshot())
    comparison["output_dir"] = str(batch_dir)
    comparison["results_dir"] = str(snapshot_dir)
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "config.json").write_text(
        json.dumps(_public_config(config), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (snapshot_dir / "comparison.json").write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (batch_dir / "comparison.json").write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return comparison


def build_comparison(
    config: dict[str, Any],
    summaries: dict[str, ExperimentSummary],
    *,
    setup_usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Pair per-question outcomes and compute factual deltas. No interpretation."""
    condition_ids = [str(item["id"]) for item in config["conditions"]]
    metrics = (
        "answerable_exact_match",
        "answerable_contains_answer",
        "answerable_f1",
        "unanswerable_abstention_rate",
        "answerable_abstention_rate",
        "retrieval_hit_rate",
        "mean_latency_ms",
        "total_chat_calls",
        "total_embedding_calls",
        "total_prompt_tokens",
        "total_completion_tokens",
        "total_embedding_tokens",
    )
    quality: dict[str, Any] = {}
    for metric in metrics:
        row = {condition_id: getattr(summaries[condition_id], metric) for condition_id in condition_ids}
        if len(condition_ids) == 2:
            left, right = condition_ids
            row["delta"] = row[right] - row[left]
        quality[metric] = row

    paired = _pair_outcomes(summaries, condition_ids)
    loop_id = next(
        (
            str(item["id"])
            for item in config["conditions"]
            if item["mode"] == MODE_LOOP
        ),
        None,
    )
    verification = _verification_table(
        summaries[loop_id].outcomes if loop_id is not None else ()
    )

    return {
        "name": config.get("name"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gold_path": config["gold_path"],
        "corpus_dir": config["corpus_dir"],
        "top_k": int(config.get("top_k", 4)),
        "max_recoveries": int(config.get("max_recoveries", 1)),
        "provider": load_provider_config().as_trace_payload(),
        "setup_usage": setup_usage or {
            "chat_calls": 0,
            "embedding_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "embedding_tokens": 0,
        },
        "condition_ids": condition_ids,
        "quality": quality,
        "verification_vs_gold": verification,
        "conditions": {
            condition_id: _summary_without_outcomes(summaries[condition_id])
            for condition_id in condition_ids
        },
        "paired_outcomes": paired,
    }


def _pair_outcomes(
    summaries: dict[str, ExperimentSummary],
    condition_ids: list[str],
) -> list[dict[str, Any]]:
    by_id = {
        condition_id: {item.question_id: item for item in summaries[condition_id].outcomes}
        for condition_id in condition_ids
    }
    question_ids = [item.question_id for item in next(iter(summaries.values())).outcomes]
    paired: list[dict[str, Any]] = []
    for question_id in question_ids:
        first = by_id[condition_ids[0]][question_id]
        row: dict[str, Any] = {
            "question_id": question_id,
            "question": first.question,
            "answerable": first.answerable,
        }
        for condition_id in condition_ids:
            row[condition_id] = _outcome_payload(by_id[condition_id][question_id])
        paired.append(row)
    return paired


def _outcome_payload(outcome: QuestionOutcome) -> dict[str, Any]:
    return {
        "answer": outcome.answer,
        "exact_match": outcome.score.exact_match,
        "contains_answer": outcome.score.contains_answer,
        "f1": outcome.score.f1,
        "abstained": outcome.score.abstained,
        "retrieval_hit": outcome.retrieval_hit,
        "retrieved_doc_ids": list(outcome.retrieved_doc_ids),
        "latency_ms": outcome.latency_ms,
        "usage": outcome.usage,
        "recovery_action": outcome.recovery_action,
        "attributed_class": outcome.attributed_class,
        "verification_outcome": outcome.verification_outcome,
        "previous_answer": outcome.previous_answer,
        "previous_f1": outcome.previous_score.f1 if outcome.previous_score else None,
        "f1_delta": outcome.f1_delta,
        "rewritten_query": outcome.rewritten_query,
        "run_id": outcome.run_id,
        "trace_path": outcome.trace_path,
    }


def _verification_table(outcomes: tuple[QuestionOutcome, ...]) -> dict[str, Any]:
    """Contingency of runtime verification vs sign of gold F1 delta.

    This is the ADR 002 measurement. Gold never entered the runtime loop; it is
    applied here after the fact. ``still_failing`` and ``unchanged`` are kept
    distinct rather than collapsed.
    """
    recovered = [item for item in outcomes if item.verification_outcome is not None]
    empty = {"n": 0, "gold_f1_up": 0, "gold_f1_down": 0, "gold_f1_same": 0, "no_previous_score": 0}
    by_outcome: dict[str, dict[str, int]] = {}
    by_class: dict[str, dict[str, int]] = {}
    by_action: dict[str, dict[str, int]] = {}

    def _bucket(table: dict[str, dict[str, int]], key: str, item: QuestionOutcome) -> None:
        row = table.setdefault(key, dict(empty))
        row["n"] += 1
        if item.f1_delta is None:
            row["no_previous_score"] += 1
        elif item.f1_delta > 0:
            row["gold_f1_up"] += 1
        elif item.f1_delta < 0:
            row["gold_f1_down"] += 1
        else:
            row["gold_f1_same"] += 1

    for item in recovered:
        _bucket(by_outcome, item.verification_outcome or "unknown", item)
        _bucket(by_action, item.recovery_action or "unknown", item)
        if item.attributed_class:
            _bucket(by_class, item.attributed_class, item)

    return {
        "n_with_runtime_verification": len(recovered),
        "n_loop_questions": len(outcomes),
        "by_runtime_outcome": by_outcome,
        "by_recovery_action": by_action,
        "by_attributed_class": by_class,
    }


def _summary_without_outcomes(summary: ExperimentSummary) -> dict[str, Any]:
    payload = asdict(summary)
    payload.pop("outcomes", None)
    return payload


def _public_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if not str(key).startswith("_")}


def _resolve(path_value: str, root: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (root / path).resolve()


def _default_repo_root(config_path: Path) -> Path:
    for candidate in (config_path.resolve().parent, *config_path.resolve().parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "datasets" / "corpus").is_dir():
            return candidate
    raise ValueError(f"Could not find repo root from config path {config_path}")
