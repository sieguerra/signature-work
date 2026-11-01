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
    parser.add_argument("--system", default="dku", help="System shown first (default: dku).")
    parser.add_argument(
        "--systems",
        default="all",
        help="Comma-separated system ids to include, or 'all' built-in systems (default).",
    )
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
    from swrag.corpus_registry import load_registry

    if args.systems == "all":
        system_ids = [entry.id for entry in load_registry()]
    else:
        system_ids = [item.strip() for item in args.systems.split(",") if item.strip()]
    if args.system in system_ids:
        system_ids.remove(args.system)
    system_ids.insert(0, args.system)
    extra = {"traces_root": args.traces_root} if args.traces_root else {}
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "static").mkdir(parents=True)

    saved = 0

    def save(path: str, payload: object, prefix: str = "") -> None:
        nonlocal saved
        target = out / prefix / (path.lstrip("/") + ".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        saved += 1

    # Each system is saved under systems/<id>/; snapshot.js switches between
    # them in the browser. The first system is also saved at the top level so
    # a page without the system list still works.
    corpora: list[dict] = []
    meta = {}
    for system_id in system_ids:
        prefixes = [f"systems/{system_id}"] + ([""] if system_id == args.system else [])
        with TestClient(create_app(corpus_id=system_id, **extra)) as client:

            def grab(path: str) -> object | None:
                response = client.get(path)
                if response.status_code != 200:
                    return None
                payload = response.json()
                for prefix in prefixes:
                    save(path, payload, prefix)
                return payload

            system_meta = client.get("/api/meta").json()
            system_meta["demo"] = {"enabled": False, "snapshot": True, "daily_runs": 0, "runs_left": 0}
            system_meta["api_key_present"] = False
            for prefix in prefixes:
                save("/api/meta", system_meta, prefix)
            if system_id == args.system:
                meta = system_meta
            listing = client.get("/api/corpora").json()
            corpora.extend(item for item in listing.get("corpora", []) if item.get("id") == system_id)
            for path in ("/api/overview", "/api/logical-runs", "/api/eval"):
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
    save("/api/corpora", {"active_id": args.system, "corpora": corpora})

    web = ROOT / "web"
    for source in web.iterdir():
        if source.is_file() and not source.name.endswith(".test.js") and not source.name.startswith("_"):
            shutil.copy2(source, out / "static" / source.name)

    page = (web / "index.html").read_text(encoding="utf-8")
    page = page.replace('"/static/', '"static/')
    marker = '<script src="static/theme.js'
    if marker not in page:
        raise SystemExit("index.html changed: could not find where to load snapshot.js")
    config = json.dumps({"default": args.system, "systems": [item["id"] for item in corpora]})
    page = page.replace(
        marker,
        f"<script>window.GROUNDLOOP_SNAPSHOT = {config};</script>\n    "
        '<script src="static/snapshot.js?v=2"></script>\n    ' + marker,
        1,
    )
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    (out / "404.html").write_text(page, encoding="utf-8")

    print(f"Snapshot of {len(corpora)} systems (first: {meta.get('corpus_label', args.system)}): {saved} API responses -> {out}")
    print("Preview: python -m http.server -d", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
