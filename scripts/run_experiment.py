#!/usr/bin/env python3
"""Score the gold set from the terminal and write a timestamped result set."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from swrag.config import load_provider_config
from swrag.experiments.runner import ExperimentSummary, run_experiment
from swrag.retrieval.fake_embedder import FakeEmbedder


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    root = repo_root()
    parser = argparse.ArgumentParser(description="Run the gold set through the pipeline.")
    parser.add_argument(
        "--gold",
        type=Path,
        default=root / "datasets" / "dku" / "gold" / "questions.jsonl",
        help="Gold set in JSON Lines format",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=root / "datasets" / "dku" / "corpus",
        help="Directory of .txt or .pdf files",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=root / "experiments" / "output",
        help="Parent directory; each run writes its own timestamped subdirectory",
    )
    parser.add_argument("--top-k", type=int, default=4, help="How many chunks to retrieve")
    parser.add_argument("--label", default=None, help="Name this run instead of using a timestamp")
    parser.add_argument(
        "--retrieve-only",
        action="store_true",
        help="Skip OpenAI: rank with the fake embedder and score empty answers",
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Run the LLM grounding judge on each question and attach flags to traces",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv(repo_root() / ".env")
    args = build_parser().parse_args(argv)

    needs_api = (not args.retrieve_only) or args.evaluate
    if needs_api and not os.environ.get("OPENAI_API_KEY"):
        print(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key,\n"
            "or run with --retrieve-only (and without --evaluate) to exercise retrieval\n"
            "and scoring without OpenAI.",
            file=sys.stderr,
        )
        return 1

    judge = None
    if args.evaluate:
        from swrag.evaluation.llm_judge import LLMJudge

        judge = LLMJudge()

    summary = run_experiment(
        gold_path=args.gold,
        corpus_dir=args.corpus,
        output_root=args.output_root,
        top_k=args.top_k,
        embedder=FakeEmbedder() if args.retrieve_only else None,
        generate=not args.retrieve_only,
        run_label=args.label,
        judge=judge,
    )
    _report(summary, retrieve_only=args.retrieve_only)
    return 0


def _report(summary: ExperimentSummary, *, retrieve_only: bool) -> None:
    config = load_provider_config()
    print(f"run:      {summary.run_label}")
    print(f"results:  {summary.output_dir}")
    print(
        f"backend:  {config.base_url}"
        + ("" if config.is_official_openai else "  (not official OpenAI)")
    )
    print()
    print(f"questions: {summary.total}  ({summary.answerable_total} answerable, "
          f"{summary.unanswerable_total} unanswerable)")
    print()

    if retrieve_only:
        print("Answers were not generated (--retrieve-only), so correctness is not meaningful.")
        print(f"  retrieval hit rate       {summary.retrieval_hit_rate:.3f}")
        return

    print("Answerable questions")
    print(f"  exact match              {summary.answerable_exact_match:.3f}")
    print(f"  contains answer          {summary.answerable_contains_answer:.3f}")
    print(f"  token F1                 {summary.answerable_f1:.3f}")
    print(f"  abstained (should be 0)  {summary.answerable_abstention_rate:.3f}")
    print()
    print("Unanswerable questions")
    print(f"  abstained (should be 1)  {summary.unanswerable_abstention_rate:.3f}")
    print()
    print("Retrieval")
    print(f"  hit rate                 {summary.retrieval_hit_rate:.3f}")
    print()
    print("Per-class numbers above are the ones to read. The pooled aggregate is")
    print("recorded in summary.json but mixes two classes with opposite success criteria.")


if __name__ == "__main__":
    raise SystemExit(main())
