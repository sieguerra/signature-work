#!/usr/bin/env python3
"""Build a static, read-only snapshot of the GroundLoop console.

The snapshot is plain files (HTML, CSS, JS, and JSON copies of the API
responses for one system), so it can be served by any free static host such
as GitHub Pages. It needs no server and no OpenAI key, and it changes nothing.

    python scripts/build_static_demo.py                    # DKU -> dist/site
    python scripts/build_static_demo.py --system dku --out dist/site

Responses pass through the same scrubbing as public demo mode, so the
snapshot carries no absolute paths and no provider endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--system", default="dku", help="System id to snapshot (default: dku).")
    parser.add_argument("--out", default=str(ROOT / "dist" / "site"), help="Output directory.")
    parser.add_argument(
        "--traces-root",
        default=os.environ.get("GROUNDLOOP_TRACES_ROOT", ""),
        help="Where recorded runs live (default: the app's own setting).",
    )
    args = parser.parse_args(argv)

    # Public mode scrubs paths and the provider endpoint from every response.
    os.environ["GROUNDLOOP_DEMO"] = "1"
    os.environ["GROUNDLOOP_DAILY_RUNS"] = "0"
    sys.path.insert(0, str(ROOT / "src"))
    from fastapi.testclient import TestClient

    from swrag.api.app import create_app

    kwargs = {"corpus_id": args.system}
    if args.traces_root:
        kwargs["traces_root"] = args.traces_root
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "static").mkdir(parents=True)

    saved = 0

    def save(path: str, payload: object) -> None:
        nonlocal saved
        target = out / (path.lstrip("/") + ".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        saved += 1

    with TestClient(create_app(**kwargs)) as client:

        def grab(path: str) -> object | None:
            response = client.get(path)
            if response.status_code != 200:
                return None
            payload = response.json()
            save(path, payload)
            return payload

        meta = client.get("/api/meta").json()
        meta["demo"] = {"enabled": False, "snapshot": True, "daily_runs": 0, "runs_left": 0}
        meta["api_key_present"] = False
        save("/api/meta", meta)
        for path in ("/api/corpora", "/api/overview", "/api/logical-runs", "/api/eval"):
            grab(path)
        traces = grab("/api/traces") or {}
        for item in traces.get("traces", []):
            run_id = item.get("run_id")
            if not run_id:
                continue
            grab(f"/api/traces/{quote(run_id)}")
            grab(f"/api/traces/{quote(run_id)}/quality")
        documents = grab("/api/documents") or {}
        for item in documents.get("documents", []):
            name = item.get("name")
            if name:
                grab(f"/api/documents/{name}")

    web = ROOT / "web"
    for source in web.iterdir():
        if source.is_file() and not source.name.endswith(".test.js") and not source.name.startswith("_"):
            shutil.copy2(source, out / "static" / source.name)

    page = (web / "index.html").read_text(encoding="utf-8")
    page = page.replace('"/static/', '"static/')
    marker = '<script src="static/theme.js'
    if marker not in page:
        raise SystemExit("index.html changed: could not find where to load snapshot.js")
    page = page.replace(marker, '<script src="static/snapshot.js"></script>\n    ' + marker, 1)
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    (out / "404.html").write_text(page, encoding="utf-8")

    print(f"Snapshot of {meta.get('corpus_label', args.system)}: {saved} API responses -> {out}")
    print("Preview: python -m http.server -d", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
