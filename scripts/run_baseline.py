#!/usr/bin/env python3
"""Run baseline RAG from the terminal."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from swrag.pipeline.baseline import run_query
from swrag.retrieval.fake_embedder import FakeEmbedder


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    root = repo_root()
    parser = argparse.ArgumentParser(description="Baseline RAG over the local toy corpus.")
    parser.add_argument("--question", required=True, help="Question to answer")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=root / "datasets" / "corpus",
        help="Directory of .txt files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "experiments" / "output",
        help="Directory for JSON traces (new file per run)",
    )
    parser.add_argument("--top-k", type=int, default=4, help="How many chunks to retrieve")
    parser.add_argument(
        "--retrieve-only",
        action="store_true",
        help="Skip OpenAI: rank with the fake embedder and write a trace (no generated answer)",
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Run the LLM grounding judge and attach sufficiency/support flags to the trace",
    )
    parser.add_argument(
        "--recover",
        action="store_true",
        help="Run evaluate → diagnose → one recovery → verify (implies --evaluate)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv(repo_root() / ".env")
    args = build_parser().parse_args(argv)
    evaluate = args.evaluate or args.recover
    needs_api = (not args.retrieve_only) or evaluate
    if needs_api and not os.environ.get("OPENAI_API_KEY"):
        print(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key,\n"
            "or run with --retrieve-only (and without --evaluate/--recover) to test\n"
            "ingestion, ranking, and traces without OpenAI.",
            file=sys.stderr,
        )
        return 1

    judge = None
    if evaluate:
        from swrag.evaluation.llm_judge import LLMJudge

        judge = LLMJudge()

    run_kwargs = dict(
        corpus_dir=args.corpus,
        output_dir=args.output_dir,
        top_k=args.top_k,
        embedder=FakeEmbedder() if args.retrieve_only else None,
        generate=not args.retrieve_only,
        judge=judge,
    )
    if args.recover:
        from swrag.orchestration.loop import run_with_recovery

        result = run_with_recovery(args.question, **run_kwargs)
    else:
        result = run_query(args.question, **run_kwargs)
    print(f"run_id: {result.run_id}")
    print(f"trace:  {result.trace_path}")
    print()
    print("Retrieved chunks:")
    if not result.retrieval.chunks:
        print("  (none)")
    for scored in result.retrieval.chunks:
        chunk = scored.chunk
        print(f"  {chunk.chunk_id}  score={scored.score:.4f}  {chunk.title}")
    print()
    if args.retrieve_only:
        print("Answer: (skipped; --retrieve-only)")
    else:
        print("Answer:")
        print(result.answer)
    if result.runtime_evaluation is not None:
        evaluation = result.runtime_evaluation
        print()
        print("Runtime evaluation:")
        print(f"  evidence_sufficient: {evaluation.evidence_sufficient}")
        print(f"  answer_supported:    {evaluation.answer_supported}")
    if result.recovery is not None:
        print()
        print("Recovery:")
        print(f"  action: {result.recovery.action}")
        if result.verification is not None:
            print(f"  verification: {result.verification.outcome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
