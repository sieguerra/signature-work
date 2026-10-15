#!/usr/bin/env python3
"""Run baseline RAG and the evaluation-guided loop on the same gold set."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from swrag.config import load_provider_config
from swrag.experiments.benchmark import run_benchmark
from swrag.retrieval.fake_embedder import FakeEmbedder


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    root = repo_root()
    parser = argparse.ArgumentParser(
        description="Compare baseline RAG with evaluation-guided recovery (issue #12)."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=root / "experiments" / "configs" / "v2_dku_baseline_vs_loop.json",
        help="JSON experiment config",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=root / "experiments" / "output",
        help="Parent for timestamped traces (gitignored)",
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=None,
        help=(
            "Parent for committed comparison snapshots (never overwritten). Default "
            "experiments/results, or experiments/output/retrieve-only-checks with --retrieve-only"
        ),
    )
    parser.add_argument("--label", default=None, help="Name this batch instead of using a timestamp")
    parser.add_argument(
        "--retrieve-only",
        action="store_true",
        help="Skip OpenAI generation; fake embedder + scripted judge (structure check only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv(repo_root() / ".env")
    args = build_parser().parse_args(argv)
    if args.label and ("/" in args.label or "\\" in args.label or ".." in args.label):
        print("--label must be a plain folder name", file=sys.stderr)
        return 1
    if args.results_root is None:
        # A retrieve-only harness check has no answers; keep it out of the
        # committed results folder (#144).
        sub = ("experiments", "output", "retrieve-only-checks") if args.retrieve_only else ("experiments", "results")
        args.results_root = repo_root().joinpath(*sub)

    if not args.retrieve_only and not os.environ.get("OPENAI_API_KEY"):
        print(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key,\n"
            "or run with --retrieve-only to exercise the harness without OpenAI.",
            file=sys.stderr,
        )
        return 1

    kwargs: dict = {
        "config_path": args.config,
        "output_root": args.output_root,
        "results_root": args.results_root,
        "run_label": args.label,
        "repo_root": repo_root(),
    }
    if args.retrieve_only:
        from swrag.evaluation.scripted_judge import ScriptedJudge

        kwargs["embedder"] = FakeEmbedder()
        kwargs["generate"] = False
        kwargs["judge"] = ScriptedJudge(evidence_sufficient=True, answer_supported=None)

    comparison = run_benchmark(**kwargs)
    _report(comparison, retrieve_only=args.retrieve_only)
    return 0


def _report(comparison: dict, *, retrieve_only: bool) -> None:
    config = load_provider_config()
    print(f"benchmark: {comparison['name']}")
    print(f"traces:    {comparison.get('output_dir')}")
    print(f"snapshot:  {comparison.get('results_dir')}")
    print(
        f"backend:  {config.base_url}"
        + ("" if config.is_official_openai else "  (not official OpenAI)")
    )
    print()
    ids = comparison["condition_ids"]
    quality = comparison["quality"]
    print(f"conditions: {', '.join(ids)}")
    print()
    if retrieve_only:
        print("Answers were not generated (--retrieve-only). Retrieval hit rate:")
        _print_metric(quality["retrieval_hit_rate"], ids)
        return

    print("Answerable")
    _print_metric(quality["answerable_exact_match"], ids, "exact match")
    _print_metric(quality["answerable_contains_answer"], ids, "contains answer")
    _print_metric(quality["answerable_f1"], ids, "token F1")
    _print_metric(quality["answerable_abstention_rate"], ids, "abstained")
    print()
    print("Unanswerable")
    _print_metric(quality["unanswerable_abstention_rate"], ids, "abstained")
    print()
    print("Retrieval")
    _print_metric(quality["retrieval_hit_rate"], ids, "hit rate")
    print()
    print("Cost / latency")
    _print_metric(quality["mean_latency_ms"], ids, "mean latency ms")
    _print_metric(quality["total_chat_calls"], ids, "chat calls")
    _print_metric(quality["total_prompt_tokens"], ids, "prompt tokens")
    _print_metric(quality["total_completion_tokens"], ids, "completion tokens")
    _print_metric(quality["total_embedding_tokens"], ids, "embedding tokens")
    print()
    verification = comparison["verification_vs_gold"]
    print(
        "Runtime verification vs gold F1 delta "
        f"(n={verification['n_with_runtime_verification']} recovered):"
    )
    print(json.dumps(verification["by_runtime_outcome"], indent=2))
    print(
        f"verdict agrees with gold F1 direction: {verification['n_verdict_agrees']}, "
        f"disagrees: {verification['n_verdict_disagrees']}"
    )
    print()
    print("Loop condition by failure class:")
    print(json.dumps(comparison["by_failure_class"], indent=2))
    print()
    print("Numbers only. Interpretation is out of scope for this command.")


def _print_metric(row: dict, ids: list[str], label: str | None = None) -> None:
    prefix = f"  {label:<22}" if label else "  "
    parts = [f"{condition_id}={row[condition_id]:.3f}" if isinstance(row[condition_id], float) else f"{condition_id}={row[condition_id]}" for condition_id in ids]
    extra = f"  delta={row['delta']:.3f}" if "delta" in row and isinstance(row["delta"], float) else ""
    if "delta" in row and not isinstance(row["delta"], float):
        extra = f"  delta={row['delta']}"
    print(prefix + "  ".join(parts) + extra)


if __name__ == "__main__":
    raise SystemExit(main())
