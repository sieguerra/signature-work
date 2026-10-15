#!/usr/bin/env python3
"""Rescore frozen benchmark snapshots with the current offline scorer.

Snapshots under ``experiments/results/`` are never edited. This reads the
answers each snapshot stored, scores them again with ``swrag.evaluation
.scoring`` (same gold files, same aggregation as ``experiments/runner.py``),
and writes a side-by-side report to a new folder:

    python scripts/rescore_snapshots.py --label scoring-v2-2026-10-16

It makes no model calls. Use it when the scorer changes (for example the
clock-range fix in issue #130 and the abstention fix in #131) so the write-up
can cite both the frozen number and the rescored number.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swrag.evaluation.gold import load_gold_set  # noqa: E402
from swrag.evaluation.scoring import score_answer  # noqa: E402

FIELDS = (
    "answerable_exact_match",
    "answerable_contains_answer",
    "answerable_f1",
    "unanswerable_abstention_rate",
    "answerable_abstention_rate",
)
CONDITIONS = ("baseline", "eval_guided")


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _gold_path(stored: str) -> Path:
    """Snapshots store an absolute path from the machine that ran them."""
    path = Path(stored)
    if path.is_file():
        return path
    marker = "datasets/"
    if marker in stored:
        return ROOT / stored[stored.index(marker):]
    raise FileNotFoundError(stored)


def rescore(snapshot: Path) -> dict:
    comparison = json.loads((snapshot / "comparison.json").read_text(encoding="utf-8"))
    gold = {item.question_id: item for item in load_gold_set(_gold_path(comparison["gold_path"]))}
    report: dict = {"snapshot": snapshot.name, "name": comparison.get("name"), "conditions": {}, "changed_questions": []}
    for condition in CONDITIONS:
        rows = []
        for pair in comparison.get("paired_outcomes", []):
            outcome = pair.get(condition)
            question = gold.get(pair.get("question_id"))
            if not outcome or question is None:
                continue
            score = score_answer(outcome.get("answer") or "", question)
            rows.append((pair["question_id"], question.answerable, outcome, score))
            stored = (outcome.get("contains_answer"), outcome.get("abstained"), round(outcome.get("f1") or 0.0, 4))
            fresh = (score.contains_answer, score.abstained, round(score.f1, 4))
            if stored != fresh:
                report["changed_questions"].append(
                    {
                        "condition": condition,
                        "question_id": pair["question_id"],
                        "answerable": question.answerable,
                        "stored": {"contains": stored[0], "abstained": stored[1], "f1": stored[2]},
                        "rescored": {"contains": fresh[0], "abstained": fresh[1], "f1": fresh[2]},
                        "answer": outcome.get("answer"),
                    }
                )
        answerable = [r for r in rows if r[1]]
        unanswerable = [r for r in rows if not r[1]]
        rescored = {
            "answerable_exact_match": _mean([float(r[3].exact_match) for r in answerable]),
            "answerable_contains_answer": _mean([float(r[3].contains_answer) for r in answerable]),
            "answerable_f1": _mean([r[3].f1 for r in answerable]),
            "unanswerable_abstention_rate": _mean([float(r[3].abstained) for r in unanswerable]),
            "answerable_abstention_rate": _mean([float(r[3].abstained) for r in answerable]),
        }
        stored = {field: (comparison.get("quality", {}).get(field) or {}).get(condition) for field in FIELDS}
        report["conditions"][condition] = {"stored": stored, "rescored": rescored}
    return report


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def markdown(reports: list[dict]) -> str:
    lines = [
        "# Rescored benchmark snapshots",
        "",
        "Frozen snapshots in `experiments/results/` are unchanged. These are the same stored answers",
        "scored again with the current offline scorer (see `scripts/rescore_snapshots.py`). No model calls.",
        "",
    ]
    for report in reports:
        lines += [f"## {report['snapshot']} ({report['name']})", "", "| Metric | Baseline stored | Baseline rescored | Eval stored | Eval rescored |", "|:--|:--|:--|:--|:--|"]
        for field in FIELDS:
            base = report["conditions"]["baseline"]
            ev = report["conditions"]["eval_guided"]
            lines.append(
                f"| {field} | {_fmt(base['stored'][field])} | {_fmt(base['rescored'][field])} | {_fmt(ev['stored'][field])} | {_fmt(ev['rescored'][field])} |"
            )
        changed = report["changed_questions"]
        lines += ["", f"Questions whose score changed: {len(changed)}", ""]
        for item in changed:
            lines.append(
                f"- `{item['question_id']}` ({item['condition']}): contains {item['stored']['contains']} to {item['rescored']['contains']}, "
                f"abstained {item['stored']['abstained']} to {item['rescored']['abstained']}, f1 {item['stored']['f1']} to {item['rescored']['f1']}"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True, help="Name of the new report folder.")
    parser.add_argument("--results-root", default=str(ROOT / "experiments" / "results"))
    parser.add_argument("--out-root", default=str(ROOT / "experiments" / "rescored"))
    args = parser.parse_args(argv)
    if "/" in args.label or "\\" in args.label or ".." in args.label:
        raise SystemExit("label must be a plain folder name")
    out = Path(args.out_root) / args.label
    if out.exists():
        raise SystemExit(f"{out} already exists; pick a new label (reports are never overwritten)")
    snapshots = sorted(path.parent for path in Path(args.results_root).glob("*/comparison.json"))
    reports = [rescore(path) for path in snapshots]
    out.mkdir(parents=True)
    (out / "rescored.json").write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
    (out / "report.md").write_text(markdown(reports), encoding="utf-8")
    print(f"Rescored {len(reports)} snapshots -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
