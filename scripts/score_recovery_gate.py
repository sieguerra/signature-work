"""Score human review files against the frozen gate table.

Does nothing to the runtime. Refuses the future holdout. If no human file
is present, writes a status that says the rates were not measured.
"""

from __future__ import annotations

import json
from pathlib import Path

from swrag.recovery_benchmark.gate_sim import CANDIDATES, adopt, margin_only_effects, simulate
from swrag.recovery_benchmark.necessity import (
    action_on_needed,
    gate_contingency,
    gating_report,
    miss_report,
    transition_agreement,
    unchanged_needed_groups,
    unnecessary_cost,
    validate_label_file,
)
from swrag.recovery_benchmark.protocol import RUN_ID
from swrag.recovery_benchmark.review import cohens_kappa

PHASE = "phase75-20261006"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = root / "experiments" / "recovery-benchmark" / "runs" / PHASE
    features = [
        json.loads(line)
        for line in (out / "gate_features.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if any(row.get("panel") == "future_holdout" for row in features):
        raise SystemExit("feature table contains the future holdout")
    key = {
        row["review_id"]: row
        for row in (
            json.loads(line)
            for line in (out / "review_key.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    labels = _read_optional(out / "human_labels.jsonl")
    nontrigger = _read_optional(out / "human_labels_nontrigger.jsonl")
    second = _read_optional(out / "human_labels_reviewer2.jsonl")
    if not labels:
        status = {
            "human_labels_collected": False,
            "reviewer_count": 0,
            "note": "Place human_labels.jsonl in this directory and run this script again. Rates were not filled in.",
        }
        _write(out / "human_gate_report.json", status)
        print("no human labels; rates not measured")
        return
    if nontrigger:
        expected = {review_id for review_id, meta in key.items() if meta.get("packet") == "nontrigger"}
        validate_label_file(nontrigger, expected_ids=expected)
    joined = _join(features, key, [*labels, *nontrigger])
    report = {
        "human_labels_collected": True,
        "reviewer_count": 1,
        "single_reviewer": True,
        "inter_rater": "No inter-rater agreement measured." if not second else _kappa(labels, second),
        "triggered": gating_report(joined),
        "nontrigger": miss_report(joined),
        "unnecessary_cost": unnecessary_cost(joined),
        "paths_on_needed": action_on_needed(joined),
        "human_vs_gold": transition_agreement(joined, reference="gold_label"),
        "human_vs_paraphrase": transition_agreement(joined, reference="gold_label_paraphrase"),
        "human_vs_grounded": transition_agreement(joined, reference="gold_label_grounded"),
        "v1_vs_human": transition_agreement(joined, reference="v1_outcome"),
        "v2_vs_human": transition_agreement(joined, reference="v2_outcome"),
        "candidates": {name: simulate(joined, rule) for name, rule in CANDIDATES.items()},
        "contingency": gate_contingency(joined),
        "margin_only": margin_only_effects(joined),
        "unchanged_needed_groups": unchanged_needed_groups(joined),
        "nontrigger_file_present": bool(nontrigger),
    }
    report["adopted_candidate"] = adopt(report["candidates"])
    report["adopted_note"] = (
        "A candidate is returned only when it skips some triggered runs and misses none "
        "that the human called bad. Otherwise no rule is selected."
    )
    _write(out / "human_gate_report.json", report)
    print(
        "necessity",
        report["triggered"]["necessity_rate"],
        "conditional",
        report["triggered"]["conditional"]["success_rate"],
        "adopted",
        report["adopted_candidate"],
        "miss",
        report["nontrigger"]["miss_rate"],
    )


def _join(features: list[dict], key: dict[str, dict], labels: list[dict]) -> list[dict]:
    by_logical = {row["logical_id"]: row for row in features}
    joined = []
    for label in labels:
        meta = key.get(label.get("review_id") or "")
        if meta is None:
            continue
        feature = by_logical.get(meta["logical_id"])
        if feature is None:
            continue
        if feature.get("panel") == "future_holdout":
            raise SystemExit("refusing a holdout label")
        joined.append({**feature, **label, "logical_id": feature["logical_id"]})
    return joined


def _kappa(first: list[dict], second: list[dict]) -> dict | str:
    right = {row["review_id"]: row.get("transition") or row.get("before_state") for row in second}
    left_labels = []
    right_labels = []
    for row in first:
        other = right.get(row.get("review_id"))
        if other is None:
            continue
        left_labels.append(row.get("transition") or "")
        right_labels.append(other or "")
    if not left_labels:
        return "No inter-rater agreement measured."
    result = cohens_kappa(left_labels, right_labels)
    return result if result is not None else "No inter-rater agreement measured."


def _read_optional(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
