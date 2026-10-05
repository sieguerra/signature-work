"""Score finished traces. Gold is attached here, not inside the loop."""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from swrag.recovery_benchmark.gold import grounded_label, paraphrase_label
from swrag.recovery_benchmark.inventory import DemoContamination
from swrag.recovery_benchmark.protocol import (
    BOOTSTRAP_ALPHA,
    BOOTSTRAP_SAMPLES,
    DEMO_CORPUS_ID,
    GOLD_GROUNDED,
    GOLD_PARAPHRASE,
    GOLD_PRIMARY,
    PRICE_PER_MILLION,
    SEED,
)
from swrag.types import GoldQuestion
from swrag.verification.v2.examples import stored_v1
from swrag.verification.v2.gold_transition import label_answers
from swrag.verification.v2.metrics import (
    accuracy,
    confusion_matrix,
    false_improvement_rate,
    improved_precision,
    improved_recall,
    macro_f1,
)
from swrag.verification.v2.payload import assert_no_gold
from swrag.verification.v2.protocol import CLASSES
from swrag.verification.v2.transitions import transitions_from_trace

OUTCOMES = CLASSES


class HoldoutLeak(ValueError):
    """A future-holdout question was about to be scored."""


def gold_from_row(row: dict) -> GoldQuestion:
    return GoldQuestion(
        question_id=row["question_id"],
        question=row["question"],
        answerable=bool(row["answerable"]),
        answers=tuple(row.get("answers") or ()),
        supporting_doc_ids=tuple(row.get("supporting_doc_ids") or ()),
    )


def score_trace(payload: dict, row: dict) -> tuple[dict | None, list[dict]]:
    """Return one logical-run row and its attempt rows.

    The logical run is the independent sample. Attempt rows are detail.
    A trace that did not execute a recovery still returns a run row with
    ``recovered`` false, so the denominator of all questions is visible.
    """
    if row.get("corpus_id") == DEMO_CORPUS_ID or "recovery-demo" in str(row.get("gold_path")):
        raise DemoContamination(str(row.get("logical_id")))
    if row.get("panel") == "future_holdout":
        raise HoldoutLeak(row["logical_id"])
    assert_no_gold(payload)
    gold = gold_from_row(row)
    transitions = transitions_from_trace(payload, corpus_id=row["corpus_id"])
    attempts = [item for item in transitions if item.level == "attempt"]
    runs = [item for item in transitions if item.level == "run"]
    actions = [item.action for item in attempts if item.action]
    recovered = bool(attempts)
    before_answer, after_answer = _endpoints(payload, attempts, runs)
    primary = label_answers(before_answer, after_answer, gold) if recovered else None
    secondary = paraphrase_label(before_answer, after_answer, gold) if recovered else None
    before_docs, after_docs = _doc_ids(attempts, runs)
    grounded = (
        grounded_label(
            before_answer,
            after_answer,
            gold,
            before_doc_ids=before_docs,
            after_doc_ids=after_docs,
            primary=primary or "",
        )
        if recovered and primary is not None
        else None
    )
    final_action = actions[-1] if actions else None
    run_transition = runs[-1] if runs else None
    v1 = stored_v1(payload, run_transition) if run_transition is not None else None
    initial = payload.get("initial") if isinstance(payload.get("initial"), dict) else {}
    diagnosis = None
    if attempts:
        diagnosis = attempts[0].before.diagnosis_class
    latency_total = _number(payload.get("latency_ms"))
    latency_initial = _number(initial.get("latency_ms")) if isinstance(initial, dict) else None
    added = None
    if latency_total is not None and latency_initial is not None:
        added = max(0.0, latency_total - latency_initial)
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    run_row = {
        "logical_id": row["logical_id"],
        "corpus_id": row["corpus_id"],
        "domain": row.get("domain"),
        "question_id": row["question_id"],
        "source": row.get("source"),
        "panel": row.get("panel"),
        "answerable": bool(row["answerable"]),
        "recovered": recovered,
        "actions": actions,
        "action": _action_bucket(actions),
        "path": ">".join(actions),
        "final_action": final_action,
        "outcome": primary,
        "gold_label": primary,
        "gold_version": GOLD_PRIMARY,
        "gold_label_paraphrase": secondary,
        "gold_paraphrase_version": GOLD_PARAPHRASE,
        "gold_label_grounded": grounded,
        "gold_grounded_version": GOLD_GROUNDED,
        "v1_outcome": v1,
        "diagnosis_class": diagnosis,
        "final_abstained": _abstained(after_answer),
        "n_attempts": len(attempts),
        "latency_ms": latency_total,
        "baseline_latency_ms": latency_initial,
        "added_latency_ms": added,
        "chat_calls": int(usage.get("chat_calls") or 0),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "embedding_tokens": int(usage.get("embedding_tokens") or 0),
        "model": payload.get("model"),
    }
    attempt_rows = []
    for transition in attempts:
        attempt_gold = label_answers(transition.before.answer, transition.after.answer, gold)
        attempt_rows.append(
            {
                "logical_id": row["logical_id"],
                "corpus_id": row["corpus_id"],
                "question_id": row["question_id"],
                "panel": row.get("panel"),
                "answerable": bool(row["answerable"]),
                "attempt_index": transition.attempt_index,
                "action": transition.action,
                "outcome": attempt_gold,
                "gold_label": attempt_gold,
                "v1_outcome": stored_v1(payload, transition),
                "diagnosis_class": transition.before.diagnosis_class,
                "n_attempts_on_question": len(attempts),
            }
        )
    return run_row, attempt_rows


def independent_recovered(run_rows: list[dict]) -> list[dict]:
    """One row per logical run that executed recovery. Attempts are not rows."""
    seen: set[str] = set()
    kept: list[dict] = []
    for row in run_rows:
        if not row.get("recovered"):
            continue
        if row.get("panel") == "future_holdout":
            raise HoldoutLeak(row.get("logical_id"))
        logical_id = str(row["logical_id"])
        if logical_id in seen:
            continue
        seen.add(logical_id)
        kept.append(row)
    return kept


def outcome_counts(rows: list[dict]) -> dict[str, int]:
    counts = {label: 0 for label in OUTCOMES}
    for row in rows:
        label = row.get("outcome")
        if label in counts:
            counts[label] += 1
    return counts


def proportion_interval(
    labels: list[str],
    target: str,
    *,
    samples: int = BOOTSTRAP_SAMPLES,
    seed: int = SEED,
    alpha: float = BOOTSTRAP_ALPHA,
) -> dict:
    """Bootstrap a single proportion. The count is always present."""
    count = sum(1 for label in labels if label == target)
    n = len(labels)
    if n == 0:
        return {"label": target, "n": 0, "count": 0, "rate": None, "low": None, "high": None}
    rate = count / n
    generator = random.Random(seed)
    draws = []
    for _ in range(samples):
        sample = [labels[generator.randrange(n)] for _ in range(n)]
        draws.append(sum(1 for label in sample if label == target) / n)
    draws.sort()
    low_index = int((alpha / 2) * (len(draws) - 1))
    high_index = int((1 - alpha / 2) * (len(draws) - 1))
    return {
        "label": target,
        "n": n,
        "count": count,
        "rate": rate,
        "low": draws[low_index],
        "high": draws[high_index],
        "samples": samples,
        "alpha": alpha,
    }


def action_breakdown(rows: list[dict]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("action") or "none")].append(row)
    report = {}
    for action, members in sorted(grouped.items()):
        labels = [str(member.get("outcome")) for member in members]
        report[action] = {
            "n": len(members),
            "counts": outcome_counts(members),
            "rates": {label: proportion_interval(labels, label) for label in OUTCOMES},
        }
    return report


def diagnosis_breakdown(rows: list[dict]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        key = row.get("diagnosis_class")
        grouped["null" if key in {None, ""} else str(key)].append(row)
    return {
        key: {"n": len(members), "counts": outcome_counts(members)}
        for key, members in sorted(grouped.items())
    }


def path_breakdown(rows: list[dict], attempt_rows: list[dict] | None = None) -> list[dict]:
    by_question: dict[str, list[dict]] = defaultdict(list)
    for attempt in attempt_rows or []:
        by_question[str(attempt["logical_id"])].append(attempt)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("action") == "multi":
            grouped[str(row.get("path") or "")].append(row)
    report = []
    for path, members in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        first: Counter[str] = Counter()
        second: Counter[str] = Counter()
        for member in members:
            ordered = sorted(by_question.get(member["logical_id"], []), key=lambda item: item.get("attempt_index") or 0)
            if ordered:
                first[str(ordered[0].get("outcome"))] += 1
            if len(ordered) > 1:
                second[str(ordered[1].get("outcome"))] += 1
        report.append(
            {
                "path": path,
                "n": len(members),
                "first_attempt": dict(first),
                "second_attempt": dict(second),
                "final_counts": outcome_counts(members),
            }
        )
    return report


def abstention_report(rows: list[dict]) -> dict:
    """Appropriateness of a final abstention. Not folded into improved."""
    abstained = [row for row in rows if row.get("final_abstained")]
    unanswerable = [row for row in rows if row.get("answerable") is False]
    answerable = [row for row in rows if row.get("answerable") is True]
    return {
        "n_recovered": len(rows),
        "n_final_abstained": len(abstained),
        "unanswerable_n": len(unanswerable),
        "unanswerable_abstained": sum(1 for row in unanswerable if row.get("final_abstained")),
        "answerable_n": len(answerable),
        "answerable_abstained": sum(1 for row in answerable if row.get("final_abstained")),
    }


def answerability_breakdown(rows: list[dict]) -> dict[str, dict]:
    report = {}
    for flag, name in ((True, "answerable"), (False, "unanswerable")):
        members = [row for row in rows if row.get("answerable") is flag]
        labels = [str(member.get("outcome")) for member in members]
        report[name] = {
            "n": len(members),
            "counts": outcome_counts(members),
            "rates": {label: proportion_interval(labels, label) for label in OUTCOMES},
        }
    return report


def verifier_summary(rows: list[dict], predicted_key: str) -> dict | None:
    """Confusion of one stored or shadow verdict against primary gold."""
    paired = [
        row
        for row in rows
        if row.get("gold_label") in OUTCOMES and row.get(predicted_key) in OUTCOMES
    ]
    if not paired:
        return None
    matrix = confusion_matrix(
        (row["gold_label"] for row in paired),
        (row[predicted_key] for row in paired),
    )
    return {
        "n": len(paired),
        "accuracy": accuracy(matrix),
        "macro_f1": macro_f1(matrix),
        "improved_precision": improved_precision(matrix),
        "improved_recall": improved_recall(matrix),
        "false_improvement_rate": false_improvement_rate(matrix),
        "confusion": matrix,
    }


def cost_report(rows: list[dict]) -> dict:
    def _mean(values: list[float]) -> float | None:
        if not values:
            return None
        return sum(values) / len(values)

    def _side(members: list[dict]) -> dict:
        chat_in = sum(int(row.get("prompt_tokens") or 0) for row in members)
        chat_out = sum(int(row.get("completion_tokens") or 0) for row in members)
        embed = sum(int(row.get("embedding_tokens") or 0) for row in members)
        price = PRICE_PER_MILLION["gpt-4o-mini"]
        embed_price = PRICE_PER_MILLION["text-embedding-3-small"]["input"]
        estimate = (chat_in * price["input"] + chat_out * price["output"] + embed * embed_price) / 1_000_000
        return {
            "n": len(members),
            "mean_baseline_latency_ms": _mean(
                [float(row["baseline_latency_ms"]) for row in members if row.get("baseline_latency_ms") is not None]
            ),
            "mean_added_latency_ms": _mean(
                [float(row["added_latency_ms"]) for row in members if row.get("added_latency_ms") is not None]
            ),
            "mean_latency_ms": _mean(
                [float(row["latency_ms"]) for row in members if row.get("latency_ms") is not None]
            ),
            "chat_calls": sum(int(row.get("chat_calls") or 0) for row in members),
            "prompt_tokens": chat_in,
            "completion_tokens": chat_out,
            "embedding_tokens": embed,
            "estimated_usd": estimate,
            "price_note": "list price estimate, not an invoice",
        }

    improved = [row for row in rows if row.get("outcome") == "improved"]
    other = [row for row in rows if row.get("outcome") != "improved"]
    return {"improved": _side(improved), "not_improved": _side(other), "all_recovered": _side(rows)}


def label_agreement(rows: list[dict], left_key: str, right_key: str) -> dict:
    paired = [row for row in rows if row.get(left_key) in OUTCOMES and row.get(right_key) in OUTCOMES]
    matches = sum(1 for row in paired if row[left_key] == row[right_key])
    disagree = [row["logical_id"] for row in paired if row[left_key] != row[right_key]]
    return {
        "n": len(paired),
        "matches": matches,
        "rate": None if not paired else matches / len(paired),
        "disagreement_ids": disagree,
    }


def build_metrics(run_rows: list[dict], attempt_rows: list[dict]) -> dict:
    recovered = independent_recovered(run_rows)
    labels = [str(row.get("outcome")) for row in recovered]
    attempt_labels = [str(row.get("outcome")) for row in attempt_rows]
    by_outcome = {label: proportion_interval(labels, label) for label in OUTCOMES}
    return {
        "gold_version": GOLD_PRIMARY,
        "n_logical_runs": len({row["logical_id"] for row in run_rows}),
        "n_recovered_logical_runs": len(recovered),
        "n_attempt_rows": len(attempt_rows),
        "attempt_rows_are_not_independent": True,
        "outcome_counts": outcome_counts(recovered),
        "outcome_rates": by_outcome,
        "by_action": action_breakdown(recovered),
        "by_answerability": answerability_breakdown(recovered),
        "by_diagnosis": diagnosis_breakdown(recovered),
        "paths": path_breakdown(recovered, attempt_rows),
        "abstention": abstention_report(recovered),
        "attempt_outcome_counts": outcome_counts(attempt_rows),
        "attempt_outcome_rates": {label: proportion_interval(attempt_labels, label) for label in OUTCOMES},
        "primary_vs_paraphrase": label_agreement(recovered, "gold_label", "gold_label_paraphrase"),
        "primary_vs_grounded": label_agreement(recovered, "gold_label", "gold_label_grounded"),
        "v1": verifier_summary(recovered, "v1_outcome"),
        "cost": cost_report(recovered),
    }


def load_trace_dir(path: Path) -> list[dict]:
    traces = []
    for file in sorted(path.glob("*.json")):
        payload = json.loads(file.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("query"):
            traces.append(payload)
    return traces


def index_split(split: dict) -> dict[tuple[str, str, str], dict]:
    """Map (corpus, source, question_id) to a split row."""
    found = {}
    for row in split["questions"]:
        if row.get("duplicate_of"):
            continue
        found[(row["corpus_id"], Path(row["source"]).stem, row["question_id"])] = row
    return found


def iter_trace_payloads(traces_root: Path) -> list[tuple[str, str, dict]]:
    """Yield (corpus_id, source, payload) from corpus/source/traces/*.json."""
    found = []
    if not traces_root.exists():
        return found
    for corpus_dir in sorted(path for path in traces_root.iterdir() if path.is_dir()):
        if corpus_dir.name == "gold-slices":
            continue
        for source_dir in sorted(path for path in corpus_dir.iterdir() if path.is_dir()):
            trace_dir = source_dir / "traces"
            if not trace_dir.is_dir():
                continue
            for payload in load_trace_dir(trace_dir):
                found.append((corpus_dir.name, source_dir.name, payload))
    return found


def score_tree(split: dict, traces_root: Path) -> tuple[list[dict], list[dict], list[str]]:
    """Score analysis traces. Future-holdout traces are listed and skipped."""
    index = index_split(split)
    run_rows: list[dict] = []
    attempt_rows: list[dict] = []
    skipped_holdout: list[str] = []
    for corpus_id, source, payload in iter_trace_payloads(traces_root):
        question_id = str(payload.get("question_id") or "")
        row = index.get((corpus_id, source, question_id))
        if row is None:
            continue
        if row.get("panel") == "future_holdout":
            skipped_holdout.append(row["logical_id"])
            continue
        if row.get("panel") != "analysis":
            continue
        run_row, attempts = score_trace(payload, row)
        if run_row is not None:
            run_rows.append(run_row)
        attempt_rows.extend(attempts)
    return run_rows, attempt_rows, skipped_holdout


def domain_counts(rows: list[dict]) -> dict[str, dict[str, int]]:
    report: dict[str, dict[str, int]] = {}
    for row in rows:
        domain = str(row.get("domain") or row.get("corpus_id"))
        bucket = report.setdefault(domain, {"n": 0, "answerable": 0, "unanswerable": 0})
        bucket["n"] += 1
        if row.get("answerable"):
            bucket["answerable"] += 1
        else:
            bucket["unanswerable"] += 1
    return report


def composition(split: dict) -> dict:
    runnable = [row for row in split["questions"] if not row.get("duplicate_of")]
    analysis = [row for row in runnable if row["panel"] == "analysis"]
    holdout = [row for row in runnable if row["panel"] == "future_holdout"]

    def _pack(rows: list[dict]) -> dict:
        return {
            "n": len(rows),
            "answerable": sum(1 for row in rows if row["answerable"]),
            "unanswerable": sum(1 for row in rows if not row["answerable"]),
            "by_corpus": dict(Counter(row["corpus_id"] for row in rows)),
            "by_domain": domain_counts(rows),
            "by_source": dict(Counter(row["source"] for row in rows)),
        }

    return {"all_runnable": _pack(runnable), "analysis": _pack(analysis), "future_holdout": _pack(holdout)}


def _action_bucket(actions: list[str | None]) -> str:
    executed = [action for action in actions if action and action != "accept"]
    if not executed:
        return "none"
    if len(executed) == 1:
        return str(executed[0])
    return "multi"


def _endpoints(payload: dict, attempts: list, runs: list) -> tuple[str, str]:
    initial = payload.get("initial") if isinstance(payload.get("initial"), dict) else {}
    before = str(initial.get("answer") or "") if isinstance(initial, dict) else ""
    if attempts and not before:
        before = attempts[0].before.answer
    if runs:
        return runs[-1].before.answer or before, runs[-1].after.answer
    if attempts:
        return attempts[0].before.answer, attempts[-1].after.answer
    return before, str(payload.get("answer") or before)


def _doc_ids(attempts: list, runs: list) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if runs:
        return _ids(runs[-1].before.chunks), _ids(runs[-1].after.chunks)
    if attempts:
        return _ids(attempts[0].before.chunks), _ids(attempts[-1].after.chunks)
    return (), ()


def _ids(chunks: tuple[dict, ...]) -> tuple[str, ...]:
    return tuple(str(chunk.get("doc_id")) for chunk in chunks if chunk.get("doc_id"))


def _abstained(answer: str) -> bool:
    from swrag.evaluation.scoring import looks_like_abstention

    return looks_like_abstention(answer)


def observed_groups(rows: list[dict]) -> dict:
    """Group real outcomes. Category names are filled only after reading them."""
    recovered = independent_recovered(rows)

    def _pack(members: list[dict]) -> list[dict]:
        grouped: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        for row in members:
            diagnosis = row.get("diagnosis_class")
            key = (
                str(row.get("outcome")),
                str(row.get("action")),
                "null" if diagnosis in {None, ""} else str(diagnosis),
            )
            grouped[key].append(str(row["logical_id"]))
        return [
            {"outcome": key[0], "action": key[1], "diagnosis_class": key[2], "n": len(ids), "logical_ids": ids}
            for key, ids in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
        ]

    failures = [row for row in recovered if row.get("outcome") != "improved"]
    successes = [row for row in recovered if row.get("outcome") == "improved"]
    return {
        "method": (
            "Groups are the observed outcome, action, and stored diagnosis. "
            "Narrative categories are written only after the examples are read."
        ),
        "failure_groups": _pack(failures),
        "success_groups": _pack(successes),
        "categories": [],
        "success_notes": [],
    }


def render_summary(metrics: dict, composition_report: dict, *, skipped_holdout: list[str]) -> str:
    recovered = metrics["n_recovered_logical_runs"]
    lines = [
        "# Recovery benchmark",
        "",
        f"Primary gold: `{metrics['gold_version']}`.",
        f"Independent recovered logical runs: **{recovered}**.",
        f"Logical runs scored, including accepts: {metrics['n_logical_runs']}.",
        f"Attempt rows (not independent samples): {metrics['n_attempt_rows']}.",
        f"Future holdout traces skipped: {len(skipped_holdout)}.",
        "",
        "Rates below use recovered logical runs as the denominator.",
        "A percentage from a very small count is not a precise estimate.",
        "",
        "## Outcomes",
        "",
    ]
    for label, stats in metrics["outcome_rates"].items():
        lines.append(_rate_line(label, stats))
    lines.extend(["", "## By answerability", ""])
    for name, block in metrics["by_answerability"].items():
        lines.append(f"### {name} (n={block['n']})")
        lines.append("")
        for label, stats in block["rates"].items():
            lines.append(_rate_line(label, stats))
        lines.append("")
    lines.extend(["## By action", ""])
    for action, block in metrics["by_action"].items():
        lines.append(f"### {action} (n={block['n']})")
        lines.append("")
        for label, stats in block["rates"].items():
            lines.append(_rate_line(label, stats))
        lines.append("")
    analysis = composition_report["analysis"]
    holdout = composition_report["future_holdout"]
    lines.extend(
        [
            "## Split",
            "",
            f"Analysis questions available to run: {analysis['n']} "
            f"({analysis['answerable']} answerable, {analysis['unanswerable']} unanswerable).",
            f"Future holdout reserved and not scored: {holdout['n']} "
            f"({holdout['answerable']} answerable, {holdout['unanswerable']} unanswerable).",
            "",
        ]
    )
    return "\n".join(lines)


def _rate_line(label: str, stats: dict) -> str:
    count = stats["count"]
    n = stats["n"]
    if stats["rate"] is None:
        return f"- {label}: 0/{n}"
    low = stats["low"]
    high = stats["high"]
    return (
        f"- {label}: {count}/{n} = {stats['rate']:.3f} "
        f"(90% bootstrap interval {low:.3f} to {high:.3f})"
    )


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
