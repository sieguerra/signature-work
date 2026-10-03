#!/usr/bin/env python3
"""Export a blank judge-audit sheet, or score one a human has filled in."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from swrag.evaluation.judge_audit import export_audit_rows, score_audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="Write unlabeled rows from traces")
    export.add_argument("traces_dir", type=Path)
    export.add_argument("-o", "--output", type=Path, required=True)

    score = sub.add_parser("score", help="Count agreement on a filled sheet")
    score.add_argument("audit_file", type=Path)

    args = parser.parse_args(argv)
    if args.command == "export":
        rows = export_audit_rows(args.traces_dir)
        lines = [
            "# Fill human_sufficient and human_supported without looking at gold.",
            *(json.dumps(row, ensure_ascii=False) for row in rows),
        ]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {len(rows)} unlabeled rows to {args.output}")
        return 0
    counts = score_audit(args.audit_file)
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
