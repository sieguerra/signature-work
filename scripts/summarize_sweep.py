#!/usr/bin/env python3
"""Summarize repeated depth-sweep snapshots into one table. No model calls.

    python scripts/summarize_sweep.py --prefix 20261015-v5 --out experiments/rescored/v5-sweep-20261015

Reads ``experiments/results/<prefix>-<corpus>-r<N>/comparison.json`` as
written by ``scripts/run_benchmark.py`` with a ``v5_*_depth_sweep`` config.
Every number in the output is a count or mean copied from those files; the
script adds no interpretation. Repeats are reported as mean and range, not
pooled into one run.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPORA = ("harbor", "dku", "kestrel")


def _load(results_root: Path, prefix: str) -> dict[str, list[dict]]:
    runs: dict[str, list[dict]] = defaultdict(list)
    pattern = re.compile(rf"^{re.escape(prefix)}-(\w+)-r(\d+)$")
    for folder in sorted(results_root.iterdir()):
        match = pattern.match(folder.name)
        if not match or not (folder / "comparison.json").is_file():
            continue
        payload = json.loads((folder / "comparison.json").read_text(encoding="utf-8"))
        payload["_folder"] = folder.name
        runs[match.group(1)].append(payload)
    return runs


def _count(pairs: list[dict], condition: str, *, answerable: bool, field: str) -> tuple[int, int]:
    rows = [pair[condition] for pair in pairs if pair.get(condition) and pair["_answerable"] is answerable]
    return sum(1 for row in rows if row.get(field)), len(rows)


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "min": None, "max": None}
    return {"mean": sum(values) / len(values), "min": min(values), "max": max(values)}


def summarize(runs: dict[str, list[dict]]) -> dict:
    report: dict = {}
    for corpus, payloads in runs.items():
        conditions = payloads[0]["condition_ids"]
        per_condition: dict[str, dict] = {}
        for condition in conditions:
            contains, abstain, chat, median, hit, usd = [], [], [], [], [], []
            n_ans: list[int] = []
            n_unans: list[int] = []
            for payload in payloads:
                pairs = _tag_answerable(payload)
                # Rates per run: a question that errored is dropped from every
                # condition of that run (#140), so n can differ between repeats.
                c, na = _count(pairs, condition, answerable=True, field="contains_answer")
                a, nu = _count(pairs, condition, answerable=False, field="abstained")
                n_ans.append(na)
                n_unans.append(nu)
                contains.append(c / na if na else 0.0)
                abstain.append(a / nu if nu else 0.0)
                summary = payload["conditions"][condition]
                chat.append(summary.get("total_chat_calls") or 0)
                tokens = (summary.get("total_prompt_tokens"), summary.get("total_completion_tokens"), summary.get("total_embedding_tokens"))
                if all(isinstance(value, int) for value in tokens):
                    # Same list prices as swrag.usage.estimated_list_cost. An estimate, not an invoice.
                    usd.append((tokens[0] * 0.15 + tokens[1] * 0.60 + tokens[2] * 0.02) / 1_000_000)
                if summary.get("median_latency_ms") is not None:
                    median.append(summary["median_latency_ms"])
                if summary.get("retrieval_hit_rate") is not None:
                    hit.append(summary["retrieval_hit_rate"])
            per_condition[condition] = {
                "top_k": payloads[0]["conditions"][condition].get("top_k"),
                "answerable_n": n_ans,
                "unanswerable_n": n_unans,
                "contains_answer_rate": _stats(contains),
                "unanswerable_abstention_rate": _stats(abstain),
                "chat_calls": _stats(chat),
                "median_latency_ms": _stats(median),
                "retrieval_hit_rate": _stats(hit),
                "estimated_list_usd": _stats(usd),
            }
        report[corpus] = {
            "folders": [payload["_folder"] for payload in payloads],
            "repeats": len(payloads),
            "questions_per_run": [len(payload["paired_outcomes"]) for payload in payloads],
            "excluded_per_run": {payload["_folder"]: payload.get("excluded_question_ids") or [] for payload in payloads},
            "conditions": per_condition,
            "loop_vs_baseline": _loop_changes(payloads, conditions),
            "verification": _verification(payloads),
            "rank_rule_by_loop": _rank_by_loop(payloads, conditions),
        }
    return report


def _tag_answerable(payload: dict) -> list[dict]:
    """Answerability from the baseline row: abstention counts only on unanswerable."""
    gold_path = Path(payload["gold_path"])
    if not gold_path.is_file() and "datasets/" in str(gold_path):
        gold_path = ROOT / str(gold_path)[str(gold_path).index("datasets/"):]
    answerable = {}
    for line in gold_path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("{"):
            row = json.loads(line)
            answerable[row["question_id"]] = bool(row["answerable"])
    return [{**pair, "_answerable": answerable[pair["question_id"]]} for pair in payload["paired_outcomes"]]


def _correct(row: dict, answerable: bool) -> bool:
    return bool(row.get("contains_answer")) if answerable else bool(row.get("abstained"))


def _loop_changes(payloads: list[dict], conditions: list[str]) -> dict:
    """Per depth, questions the loop fixed or broke relative to the same-depth baseline."""
    out: dict = {}
    for loop in [c for c in conditions if c.startswith("loop_")]:
        base = "baseline_" + loop.split("_", 1)[1]
        if base not in conditions:
            continue
        fixed, broke = [], []
        for payload in payloads:
            pairs = _tag_answerable(payload)
            fixed.append(sum(1 for p in pairs if not _correct(p[base], p["_answerable"]) and _correct(p[loop], p["_answerable"])))
            broke.append(sum(1 for p in pairs if _correct(p[base], p["_answerable"]) and not _correct(p[loop], p["_answerable"])))
        out[loop] = {"vs": base, "fixed": fixed, "broke": broke}
    return out


def _verification(payloads: list[dict]) -> dict:
    """The comparison's own verification table is for the first loop condition only."""
    rows = []
    for payload in payloads:
        table = payload.get("verification_vs_gold") or {}
        rank = table.get("rank_rule") or {}
        rows.append(
            {
                "folder": payload["_folder"],
                "n_verified": table.get("n_with_runtime_verification"),
                "f1_sign_agrees": table.get("n_verdict_agrees"),
                "f1_sign_disagrees": table.get("n_verdict_disagrees"),
                "rank_answerable": (rank.get("by_answerability") or {}).get("answerable"),
                "rank_unanswerable": (rank.get("by_answerability") or {}).get("unanswerable"),
                "outcomes": {k: v.get("n") for k, v in (table.get("by_runtime_outcome") or {}).items()},
            }
        )
    return {"loop_condition": payloads[0]["condition_ids"][1] if len(payloads[0]["condition_ids"]) > 1 else None, "runs": rows}


def _rank_by_loop(payloads: list[dict], conditions: list[str]) -> dict:
    """Rank-rule agreement for every loop condition, rescored from the stored answers."""
    sys.path.insert(0, str(ROOT / "src"))
    from swrag.evaluation.gold import load_gold_set
    from swrag.evaluation.scoring import score_answer
    from swrag.verification.v2.gold_transition import transition_label

    out: dict = {}
    for loop in [c for c in conditions if c.startswith("loop_")]:
        totals = {"answerable": {"n": 0, "agrees": 0}, "unanswerable": {"n": 0, "agrees": 0}}
        verdicts: dict[str, int] = {}
        for payload in payloads:
            gold_path = Path(payload["gold_path"])
            if not gold_path.is_file():
                gold_path = ROOT / str(gold_path)[str(gold_path).index("datasets/"):]
            gold = {q.question_id: q for q in load_gold_set(gold_path)}
            for pair in payload["paired_outcomes"]:
                row = pair.get(loop) or {}
                verdict = row.get("verification_outcome")
                if verdict is None or row.get("previous_answer") is None:
                    continue
                question = gold[pair["question_id"]]
                label = transition_label(score_answer(row["previous_answer"], question), score_answer(row.get("answer") or "", question))
                key = "answerable" if question.answerable else "unanswerable"
                totals[key]["n"] += 1
                totals[key]["agrees"] += int(label == verdict)
                verdicts[verdict] = verdicts.get(verdict, 0) + 1
        out[loop] = {**totals, "runtime_verdicts": verdicts}
    return out


def _fmt(stats: dict, digits: int = 1) -> str:
    if stats["mean"] is None:
        return "n/a"
    if stats["min"] == stats["max"]:
        return f"{stats['mean']:.{digits}f}"
    return f"{stats['mean']:.{digits}f} ({stats['min']:.{digits}f} to {stats['max']:.{digits}f})"


def markdown(report: dict) -> str:
    lines = [
        "# Depth sweep summary",
        "",
        "Mean over repeats, with the range in brackets when repeats differ. Counts are questions.",
        "Generated by `scripts/summarize_sweep.py`; no model calls, no interpretation.",
        "",
    ]
    for corpus in [c for c in CORPORA if c in report] + [c for c in report if c not in CORPORA]:
        data = report[corpus]
        lines += [f"## {corpus} ({data['repeats']} repeats, questions per run {data['questions_per_run']})", ""]
        excluded = {k: v for k, v in data["excluded_per_run"].items() if v}
        if excluded:
            lines += [f"Excluded after an error, from every condition of that run: {excluded}", ""]
        lines += ["Folders: " + ", ".join(f"`{f}`" for f in data["folders"]), ""]
        lines += ["| Condition | top_k | Answerable n | Contains-answer rate | Unanswerable n | Abstention rate | Chat calls | Est. USD | Median latency ms |", "|:--|:--|:--|:--|:--|:--|:--|:--|:--|"]
        for name, row in data["conditions"].items():
            lines.append(
                f"| {name} | {row['top_k']} | {row['answerable_n']} | {_fmt(row['contains_answer_rate'], 3)} | "
                f"{row['unanswerable_n']} | {_fmt(row['unanswerable_abstention_rate'], 3)} | {_fmt(row['chat_calls'], 0)} | {_fmt(row['estimated_list_usd'], 4)} | {_fmt(row['median_latency_ms'], 0)} |"
            )
        lines += ["", "| Loop | vs | Fixed per repeat | Broke per repeat |", "|:--|:--|:--|:--|"]
        for loop, row in data["loop_vs_baseline"].items():
            lines.append(f"| {loop} | {row['vs']} | {row['fixed']} | {row['broke']} |")
        lines += ["", "Rank-rule agreement, all repeats pooled:", ""]
        for loop, row in data["rank_rule_by_loop"].items():
            lines.append(
                f"- `{loop}`: answerable {row['answerable']['agrees']}/{row['answerable']['n']}, "
                f"unanswerable {row['unanswerable']['agrees']}/{row['unanswerable']['n']}, verdicts {row['runtime_verdicts']}"
            )
        lines += ["", f"Verification vs gold for `{data['verification']['loop_condition']}` (from each comparison.json):", ""]
        for row in data["verification"]["runs"]:
            lines.append(
                f"- `{row['folder']}`: verified {row['n_verified']}, outcomes {row['outcomes']}, "
                f"F1-sign {row['f1_sign_agrees']}/{row['f1_sign_disagrees']}, rank answerable {row['rank_answerable']}, rank unanswerable {row['rank_unanswerable']}"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--results-root", default=str(ROOT / "experiments" / "results"))
    parser.add_argument("--out", required=True, help="New folder for summary.json and summary.md")
    args = parser.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        raise SystemExit(f"{out} already exists; pick a new folder (summaries are never overwritten)")
    runs = _load(Path(args.results_root), args.prefix)
    if not runs:
        raise SystemExit("no matching snapshots")
    report = summarize(runs)
    out.mkdir(parents=True)
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (out / "summary.md").write_text(markdown(report), encoding="utf-8")
    print(f"Summarized {sum(len(v) for v in runs.values())} snapshots -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
