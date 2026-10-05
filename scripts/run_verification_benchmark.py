#!/usr/bin/env python3
"""Run the shadow verification benchmark.

Gold is joined only after a candidate returns a prediction. Runtime recovery
is not invoked unless ``--generate`` is set, and even then the new traces are
scored offline. Verification v1 inside the product is not modified.

Example:
    python scripts/run_verification_benchmark.py --panel archive --candidate coverage
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from swrag.verification.v2.adversarial import adversarial_examples
from swrag.verification.v2.benchmark import (
    score_examples,
    select_on_development,
    write_report,
)
from swrag.verification.v2.candidates import (
    Completion,
    CoverageVerifier,
    PairwiseVerifier,
    PointwiseVerifier,
    SurfaceVerifier,
)
from swrag.verification.v2.examples import examples_from_trace_dir
from swrag.verification.v2.historical import load_archive
from swrag.verification.v2.protocol import (
    DEV_CORPUS,
    DEV_GOLD,
    LIVE_MAX_RECOVERIES,
    LIVE_TOP_K,
    PROTOCOL_VERSION,
    SEED,
    TEST_CORPUS,
    TEST_GOLD,
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score shadow verifiers against offline gold.")
    parser.add_argument("--panel", choices=("archive", "adversarial", "live"), required=True)
    parser.add_argument(
        "--candidate",
        choices=("surface", "coverage", "pointwise", "pairwise", "all"),
        default="coverage",
    )
    parser.add_argument("--split", choices=("dev", "test", "all"), default="all")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--model", default=None, help="Chat model for pointwise and pairwise.")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--call-model",
        action="store_true",
        help="Allow pointwise and pairwise to call the configured chat model.",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Run the recovery loop to create traces before scoring the live panel.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing benchmark output directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    root = repo_root()
    load_dotenv(root / ".env")
    args = build_parser().parse_args(argv)
    if args.seed != SEED:
        print(f"warning: protocol seed is {SEED}; this run uses {args.seed}", file=sys.stderr)

    output_root = args.output_dir or (root / "experiments" / "verification-v2" / "runs" / args.panel)
    cache_dir = args.cache_dir or (root / "experiments" / "verification-v2" / "cache")
    names = ("surface", "coverage", "pointwise", "pairwise") if args.candidate == "all" else (args.candidate,)
    model = args.model or os.environ.get("OPENAI_CHAT_MODEL") or "gpt-4o-mini"

    summaries = {}
    for name in names:
        if name in {"pointwise", "pairwise"} and not args.call_model:
            print(f"skip {name}: pass --call-model to spend a judge call")
            continue
        destination = output_root / name if len(names) > 1 else output_root
        if (destination / "metrics.json").exists() and not args.force:
            print(f"refuse to overwrite {destination} (pass --force)", file=sys.stderr)
            return 2
        examples = _examples(root, args, name)
        candidate = _candidate(name, model=model, cache_dir=cache_dir, call_model=args.call_model)
        rows = score_examples(candidate, examples)
        config = {
            "protocol": PROTOCOL_VERSION,
            "panel": args.panel,
            "split": args.split,
            "candidate": name,
            "model": model if name in {"pointwise", "pairwise"} else None,
            "seed": args.seed,
            "call_model": args.call_model,
            "live_top_k": LIVE_TOP_K,
            "live_max_recoveries": LIVE_MAX_RECOVERIES,
            "n_examples": len(examples),
        }
        payload = write_report(destination, config=config, rows=rows, candidate=name)
        summaries[name] = payload["summary"]
        print(
            f"{name}: n={payload['summary']['n']} "
            f"decided={payload['summary']['n_decided']} "
            f"false_improvement_rate={payload['summary']['false_improvement_rate']}"
        )

    if args.split == "dev" and len(summaries) > 1:
        selected = select_on_development(summaries)
        selection = {"selected": selected, "candidates": sorted(summaries)}
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
        print(f"development selection: {selected}")
    return 0


def _examples(root: Path, args: argparse.Namespace, candidate: str) -> tuple:
    del candidate
    if args.panel == "archive":
        return load_archive(root)
    if args.panel == "adversarial":
        return adversarial_examples()
    if args.generate:
        _generate(root, args.split)
    splits = ("dev", "test") if args.split == "all" else (args.split,)
    found = []
    for split in splits:
        corpus_id = DEV_CORPUS if split == "dev" else TEST_CORPUS
        gold = DEV_GOLD if split == "dev" else TEST_GOLD
        traces_root = root / "experiments" / "verification-v2" / "traces"
        for gold_relative in gold:
            label = f"{split}-{Path(gold_relative).stem}"
            traces_dir = traces_root / label / "traces"
            if not traces_dir.exists():
                continue
            found.extend(
                examples_from_trace_dir(
                    traces_dir,
                    gold,
                    root=root,
                    panel="live",
                    split=split,
                    corpus_id=corpus_id,
                )
            )
    return tuple(found)


def _generate(root: Path, split: str) -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set; refusing to generate traces.")
    from swrag.evaluation.llm_judge import LLMJudge
    from swrag.experiments.runner import run_experiment

    splits = ("dev", "test") if split == "all" else (split,)
    for name in splits:
        gold_files = DEV_GOLD if name == "dev" else TEST_GOLD
        corpus = root / "datasets" / (DEV_CORPUS if name == "dev" else TEST_CORPUS) / "corpus"
        for relative in gold_files:
            label = f"{name}-{Path(relative).stem}"
            destination = root / "experiments" / "verification-v2" / "traces" / label
            if destination.exists():
                print(f"reuse traces {destination}")
                continue
            print(f"generate {label}")
            run_experiment(
                gold_path=root / relative,
                corpus_dir=corpus,
                output_root=root / "experiments" / "verification-v2" / "traces",
                top_k=LIVE_TOP_K,
                mode="loop",
                max_recoveries=LIVE_MAX_RECOVERIES,
                judge=LLMJudge(),
                run_label=label,
            )


def _candidate(name: str, *, model: str, cache_dir: Path, call_model: bool) -> object:
    if name == "surface":
        return SurfaceVerifier()
    if name == "coverage":
        return CoverageVerifier()
    if not call_model:
        raise SystemExit(f"{name} needs --call-model")
    client = _OpenAIChat(model)
    if name == "pointwise":
        return PointwiseVerifier(client, model=model, cache_dir=cache_dir)
    if name == "pairwise":
        return PairwiseVerifier(client, model=model, cache_dir=cache_dir)
    raise SystemExit(f"unknown candidate {name}")


class _OpenAIChat:
    def __init__(self, model: str) -> None:
        from openai import OpenAI

        self.model = model
        self._client = OpenAI()

    def complete(self, *, system: str, user: str) -> Completion:
        started = time.perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except Exception as error:
            if "timeout" in type(error).__name__.lower():
                raise TimeoutError(str(error)) from error
            raise
        usage = getattr(response, "usage", None)
        text = response.choices[0].message.content or ""
        return Completion(
            text=text,
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage is not None else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage is not None else None,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )


if __name__ == "__main__":
    raise SystemExit(main())
