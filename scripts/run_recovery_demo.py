#!/usr/bin/env python3
"""Run the visual demo questions through the real recovery loop.

The corpus is recovery-demo. These runs are not benchmark samples.
Traces are written under experiments/recovery-benchmark/demo-runs/.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from swrag.config import load_provider_config
from swrag.evaluation.gold import load_gold_set
from swrag.evaluation.llm_judge import LLMJudge
from swrag.generation.openai_generator import OpenAIGenerator
from swrag.orchestration.loop import run_with_recovery
from swrag.pipeline.baseline import build_corpus_index
from swrag.recovery.regenerate import ConstrainedRegenerator
from swrag.recovery.rewrite import LLMQueryRewriter
from swrag.recovery_benchmark.demo import load_demo_manifest
from swrag.recovery_benchmark.protocol import DEMO_CORPUS_ID, MAX_RECOVERIES, TOP_K
from swrag.retrieval.openai_embedder import OpenAIEmbedder


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")
    manifest = load_demo_manifest(root)
    if manifest.get("corpus_id") != DEMO_CORPUS_ID or manifest.get("benchmark") is not False:
        raise SystemExit("refusing to run a manifest that is not marked off-benchmark")
    corpus = root / "datasets" / "recovery-demo" / "corpus"
    gold = {item.question_id: item for item in load_gold_set(root / "datasets" / "recovery-demo" / "gold" / "questions.jsonl")}
    out = root / "experiments" / "recovery-benchmark" / "demo-runs"
    out.mkdir(parents=True, exist_ok=True)
    config = load_provider_config()
    client = OpenAI(base_url=config.base_url, timeout=120.0, max_retries=1)
    embedder = OpenAIEmbedder(client=client, config=config)
    index = build_corpus_index(corpus, embedder)
    judge = LLMJudge(client=client, config=config)
    generator = OpenAIGenerator(client=client, config=config)
    rewriter = LLMQueryRewriter(client=client, config=config)
    regenerator = ConstrainedRegenerator(client=client, config=config)
    repeats = 3
    summary = []
    for case in manifest["cases"]:
        question = gold[case["question_id"]]
        observed = []
        for repeat in range(1, repeats + 1):
            result = run_with_recovery(
                question.question,
                corpus_dir=corpus,
                output_dir=out / question.question_id,
                top_k=TOP_K,
                max_recoveries=MAX_RECOVERIES,
                question_id=question.question_id,
                judge=judge,
                index=index,
                embedder=embedder,
                generator=generator,
                rewriter=rewriter,
                regenerator=regenerator,
                run_mode="loop",
            )
            trace = json.loads(Path(result.trace_path).read_text(encoding="utf-8"))
            actions = [
                item.get("action")
                for item in (trace.get("recovery_attempts") or [])
                if isinstance(item, dict) and item.get("executed") is not False
            ]
            verification = (trace.get("verification") or {}).get("outcome")
            observed.append(
                {
                    "repeat": repeat,
                    "actions": actions,
                    "verification": verification,
                    "run_id": trace.get("run_id"),
                }
            )
            print(
                f"{question.question_id} repeat {repeat}: "
                f"{'>'.join(actions) or 'accept'} verification={verification}",
                flush=True,
            )
        summary.append(
            {
                "question_id": question.question_id,
                "question": question.question,
                "expected_path": case.get("expected_path"),
                "top_k": TOP_K,
                "max_recoveries": MAX_RECOVERIES,
                "mode": "loop",
                "repeats": observed,
            }
        )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
