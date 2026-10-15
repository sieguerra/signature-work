#!/usr/bin/env python3
"""Run the frozen recovery loop and score it offline.

The loop receives the question text only. Gold labels are joined after the
trace is written. The visual demo corpus is not a benchmark input. The future
holdout is reserved and is not generated or scored.

Example:
    python scripts/run_recovery_benchmark.py --generate --score
    python scripts/run_recovery_benchmark.py --verify --call-model
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

from swrag.experiments.guard import refuse_committed
from swrag.corpus_registry import load_registry
from swrag.recovery_benchmark.inventory import load_questions, questions_to_generate
from swrag.recovery_benchmark.protocol import (
    DEMO_CORPUS_ID,
    GOLD_GROUNDED,
    GOLD_PARAPHRASE,
    GOLD_PRIMARY,
    MAX_RECOVERIES,
    PROTOCOL_VERSION,
    RUN_ID,
    SEED,
    TOP_K,
)
from swrag.recovery_benchmark.review import blinded_export, select_review_ids
from swrag.recovery_benchmark.scoring import (
    build_metrics,
    composition,
    independent_recovered,
    observed_groups,
    render_summary,
    score_tree,
)
from swrag.recovery_benchmark.split import assign_split
from swrag.types import GoldQuestion
from swrag.verification.v2.examples import Example, examples_from_trace
from swrag.verification.v2.transitions import transitions_from_trace


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score runtime recovery at the frozen product settings.")
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--verify", action="store_true", help="Score frozen pairwise v2. Needs --call-model.")
    parser.add_argument("--sample", action="store_true", help="Write a blinded review sample. Labels stay empty.")
    parser.add_argument("--call-model", action="store_true")
    parser.add_argument("--run-id", default=RUN_ID)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--overwrite-committed",
        action="store_true",
        help="Allow writing into a run folder that holds committed results.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    root = repo_root()
    load_dotenv(root / ".env")
    args = build_parser().parse_args(argv)
    if not any((args.generate, args.score, args.verify, args.sample)):
        args.generate = True
        args.score = True
        args.sample = True
    run_dir = root / "experiments" / "recovery-benchmark" / "runs" / args.run_id
    traces_root = root / "experiments" / "recovery-benchmark" / "traces"
    split_path = run_dir / "question_split.json"
    refuse_committed(run_dir, overwrite=args.overwrite_committed)
    run_dir.mkdir(parents=True, exist_ok=True)

    if split_path.exists() and not args.force and args.generate:
        split = json.loads(split_path.read_text(encoding="utf-8"))
        print(f"reuse split {split_path}")
    else:
        records = load_questions(root)
        split = assign_split(records, root)
        _write_json(split_path, split)
        print(
            f"split analysis={split['n_analysis']} future_holdout={split['n_future_holdout']} "
            f"exact_duplicates_dropped={split['n_exact_duplicates_dropped']}"
        )

    if args.generate:
        _generate(root, split, traces_root)
    if args.score or args.sample or args.verify:
        run_rows, attempt_rows, skipped = score_tree(split, traces_root)
        if skipped:
            print(f"skipped {len(skipped)} future-holdout traces")
        metrics = build_metrics(run_rows, attempt_rows)
        comp = composition(split)
        if args.score:
            _write_scored(run_dir, split, run_rows, attempt_rows, metrics, comp, skipped)
            print(
                f"recovered logical runs={metrics['n_recovered_logical_runs']} "
                f"improved={metrics['outcome_counts']['improved']}"
            )
        if args.sample:
            _write_sample(run_dir, split, traces_root, run_rows)
        if args.verify:
            if not args.call_model:
                print("skip verify: pass --call-model", file=sys.stderr)
                return 2
            _verify(root, split, traces_root, run_dir, run_rows)
    return 0


def _generate(root: Path, split: dict, traces_root: Path) -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set; refusing to generate traces.")
    from swrag.evaluation.llm_judge import LLMJudge
    from swrag.experiments.runner import run_experiment
    from swrag.generation.openai_generator import OpenAIGenerator
    from swrag.pipeline.baseline import build_corpus_index
    from swrag.recovery.regenerate import ConstrainedRegenerator
    from swrag.recovery.rewrite import LLMQueryRewriter
    from swrag.retrieval.openai_embedder import OpenAIEmbedder
    from openai import OpenAI
    from swrag.config import load_provider_config

    selected = questions_to_generate(split["questions"])
    by_corpus: dict[str, list[dict]] = {}
    for row in selected:
        by_corpus.setdefault(row["corpus_id"], []).append(row)
    entries = {entry.id: entry for entry in load_registry(root=root)}
    config = load_provider_config()
    # Harness timeout only. The product client is unchanged.
    client = OpenAI(base_url=config.base_url, timeout=120.0, max_retries=1)
    embedder = OpenAIEmbedder(client=client, config=config)
    generator = OpenAIGenerator(client=client, config=config)
    rewriter = LLMQueryRewriter(client=client, config=config)
    regenerator = ConstrainedRegenerator(client=client, config=config)
    judge = LLMJudge(client=client, config=config)
    failures: list[str] = []
    for corpus_id, rows in sorted(by_corpus.items()):
        if corpus_id == DEMO_CORPUS_ID:
            raise SystemExit("refusing to generate the visual demo inside the benchmark")
        entry = entries[corpus_id]
        by_source: dict[str, list[dict]] = {}
        for row in rows:
            by_source.setdefault(row["source"], []).append(row)
        print(f"index {corpus_id}", flush=True)
        index = build_corpus_index(entry.corpus_dir, embedder)
        for source, source_rows in sorted(by_source.items()):
            destination = traces_root / corpus_id / Path(source).stem
            if (destination / "summary.json").is_file():
                print(f"reuse traces {destination}", flush=True)
                continue
            if destination.exists():
                print(f"removing partial {destination}", flush=True)
                shutil.rmtree(destination)
            print(f"generate {corpus_id} {source} n={len(source_rows)} top_k={TOP_K}", flush=True)
            slice_path = traces_root / "gold-slices" / corpus_id / f"{Path(source).stem}.jsonl"
            _write_gold_slice(slice_path, source_rows)
            try:
                run_experiment(
                    gold_path=slice_path,
                    corpus_dir=entry.corpus_dir,
                    output_root=traces_root / corpus_id,
                    top_k=TOP_K,
                    mode="loop",
                    max_recoveries=MAX_RECOVERIES,
                    judge=judge,
                    index=index,
                    embedder=embedder,
                    generator=generator,
                    regenerator=regenerator,
                    rewriter=rewriter,
                    run_label=Path(source).stem,
                )
            except Exception as error:
                print(f"failed {corpus_id} {source}: {type(error).__name__}: {error}", flush=True)
                if destination.exists() and not (destination / "summary.json").is_file():
                    shutil.rmtree(destination)
                failures.append(f"{corpus_id}:{source}:{type(error).__name__}")
    if failures:
        print("generation failures: " + ", ".join(failures), flush=True)


def _write_gold_slice(path: Path, rows: list[dict]) -> None:
    """Offline input for the experiment runner. Not a runtime trace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for row in rows:
        lines.append(
            json.dumps(
                {
                    "question_id": row["question_id"],
                    "question": row["question"],
                    "answerable": row["answerable"],
                    "answers": row["answers"],
                    "supporting_doc_ids": row["supporting_doc_ids"],
                },
                ensure_ascii=False,
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_scored(
    run_dir: Path,
    split: dict,
    run_rows: list[dict],
    attempt_rows: list[dict],
    metrics: dict,
    comp: dict,
    skipped: list[str],
) -> None:
    config = {
        "protocol": PROTOCOL_VERSION,
        "seed": SEED,
        "top_k": TOP_K,
        "max_recoveries": MAX_RECOVERIES,
        "gold_primary": GOLD_PRIMARY,
        "gold_paraphrase": GOLD_PARAPHRASE,
        "gold_grounded": GOLD_GROUNDED,
        "demo_corpus_excluded": DEMO_CORPUS_ID,
        "future_holdout_scored": False,
        "n_analysis": split["n_analysis"],
        "n_future_holdout": split["n_future_holdout"],
    }
    _write_json(run_dir / "config.json", config)
    _write_jsonl(run_dir / "run_results.jsonl", run_rows)
    _write_jsonl(run_dir / "attempt_results.jsonl", attempt_rows)
    _write_json(run_dir / "metrics.json", metrics)
    _write_json(run_dir / "action_breakdown.json", metrics["by_action"])
    _write_json(run_dir / "failure_analysis.json", observed_groups(run_rows))
    _write_json(run_dir / "cost_latency.json", metrics["cost"])
    _write_json(run_dir / "composition.json", comp)
    (run_dir / "summary.md").write_text(
        render_summary(metrics, comp, skipped_holdout=skipped),
        encoding="utf-8",
    )


def _write_sample(run_dir: Path, split: dict, traces_root: Path, run_rows: list[dict]) -> None:
    from swrag.recovery_benchmark.scoring import iter_trace_payloads

    chosen = select_review_ids(run_rows, limit=100)
    by_id = {row["logical_id"]: row for row in run_rows}
    split_by_id = {row["logical_id"]: row for row in split["questions"] if not row.get("duplicate_of")}
    index = {
        (row["corpus_id"], Path(row["source"]).stem, row["question_id"]): row
        for row in split["questions"]
        if not row.get("duplicate_of")
    }
    traces = {}
    for corpus_id, source, payload in iter_trace_payloads(traces_root):
        question_id = str(payload.get("question_id") or "")
        row = index.get((corpus_id, source, question_id))
        if row is not None:
            traces[row["logical_id"]] = payload
    blinded = []
    key_rows = []
    for number, logical_id in enumerate(chosen, start=1):
        scored = by_id[logical_id]
        row = split_by_id[logical_id]
        payload = traces.get(logical_id)
        if payload is None:
            continue
        review_id = f"R{number:03d}"
        example = _run_example(payload, row)
        if example is None:
            continue
        blinded.append(blinded_export(example, review_id=review_id))
        key_rows.append(
            {
                "review_id": review_id,
                "logical_id": logical_id,
                "gold_label": scored.get("gold_label"),
                "answerable": scored.get("answerable"),
                "action": scored.get("action"),
            }
        )
    _write_jsonl(run_dir / "human_review_sample.jsonl", blinded)
    _write_jsonl(run_dir / "human_review_key.jsonl", key_rows)
    print(f"blinded review sample n={len(blinded)} (labels left empty)")


def _run_example(payload: dict, row: dict) -> Example | None:
    gold = GoldQuestion(
        question_id=row["question_id"],
        question=row["question"],
        answerable=bool(row["answerable"]),
        answers=tuple(row.get("answers") or ()),
        supporting_doc_ids=tuple(row.get("supporting_doc_ids") or ()),
    )
    examples = examples_from_trace(
        payload,
        {row["question_id"]: gold},
        panel="recovery-benchmark",
        split="analysis",
        corpus_id=row["corpus_id"],
        source=row.get("source") or "",
    )
    runs = [example for example in examples if example.transition.level == "run"]
    return runs[-1] if runs else None


def _verify(root: Path, split: dict, traces_root: Path, run_dir: Path, run_rows: list[dict]) -> None:
    from swrag.verification.v2.benchmark import score_examples
    from swrag.verification.v2.candidates import PairwiseVerifier
    from swrag.verification.v2.metrics import summarize_predictions
    from swrag.recovery_benchmark.scoring import iter_trace_payloads

    recovered_ids = {row["logical_id"] for row in independent_recovered(run_rows)}
    human_ids = _logical_ids_from_key(run_dir / "human_review_key.jsonl")
    index = {
        (row["corpus_id"], Path(row["source"]).stem, row["question_id"]): row
        for row in split["questions"]
        if row.get("panel") == "analysis" and not row.get("duplicate_of")
    }
    run_examples: list[Example] = []
    attempt_examples: list[Example] = []
    for corpus_id, source, payload in iter_trace_payloads(traces_root):
        question_id = str(payload.get("question_id") or "")
        row = index.get((corpus_id, source, question_id))
        if row is None or row["logical_id"] not in recovered_ids:
            continue
        if transitions_from_trace(payload, corpus_id=corpus_id) and row.get("panel") == "future_holdout":
            raise SystemExit("refusing to verify the future holdout")
        gold = {
            row["question_id"]: GoldQuestion(
                question_id=row["question_id"],
                question=row["question"],
                answerable=bool(row["answerable"]),
                answers=tuple(row.get("answers") or ()),
                supporting_doc_ids=tuple(row.get("supporting_doc_ids") or ()),
            )
        }
        examples = examples_from_trace(
            payload,
            gold,
            panel="recovery-benchmark",
            split="analysis",
            corpus_id=corpus_id,
            source=source,
        )
        for example in examples:
            if example.transition.level == "run":
                run_examples.append(example)
            elif example.transition.level == "attempt":
                attempt_examples.append(example)
    model = os.environ.get("OPENAI_CHAT_MODEL") or "gpt-4o-mini"
    cache_dir = root / "experiments" / "recovery-benchmark" / "cache"
    client = _OpenAIChat(model)
    candidate = PairwiseVerifier(client, model=model, cache_dir=cache_dir)
    print(f"pairwise run-level n={len(run_examples)}")
    run_predictions = _with_logical_ids(score_examples(candidate, run_examples), run_examples)
    print(f"pairwise attempt-level n={len(attempt_examples)}")
    attempt_predictions = _with_logical_ids(score_examples(candidate, attempt_examples), attempt_examples)
    human_predictions = [row for row in run_predictions if row.get("logical_id") in human_ids]
    _write_json(
        run_dir / "verifier.json",
        {
            "candidate": "pairwise",
            "prompt": "pairwise-2026-10-06",
            "tuned": False,
            "run_level": summarize_predictions(run_predictions),
            "attempt_level": summarize_predictions(attempt_predictions),
            "review_sample_subset": summarize_predictions(human_predictions),
            "human_labels_collected": False,
            "n_run": len(run_predictions),
            "n_attempt": len(attempt_predictions),
            "n_human_subset": len(human_predictions),
        },
    )
    _write_jsonl(run_dir / "verifier_run_predictions.jsonl", run_predictions)
    print("wrote verifier.json")


def _with_logical_ids(rows: list[dict], examples: list[Example]) -> list[dict]:
    for row, example in zip(rows, examples, strict=True):
        corpus_id = example.transition.corpus_id or ""
        question_id = example.transition.question_id or ""
        source_name = example.source if str(example.source).endswith(".jsonl") else f"{example.source}.jsonl"
        row["logical_id"] = f"{corpus_id}:{source_name}:{question_id}"
    return rows


def _logical_ids_from_key(path: Path) -> set[str]:
    if not path.exists():
        return set()
    found = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        found.add(str(json.loads(line)["logical_id"]))
    return found


class _OpenAIChat:
    def __init__(self, model: str) -> None:
        import time

        from openai import OpenAI

        from swrag.verification.v2.candidates import Completion

        self._Completion = Completion
        self._time = time
        self.model = model
        self._client = OpenAI()

    def complete(self, *, system: str, user: str):
        started = self._time.perf_counter()
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
        return self._Completion(
            text=text,
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage is not None else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage is not None else None,
            latency_ms=(self._time.perf_counter() - started) * 1000.0,
        )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
