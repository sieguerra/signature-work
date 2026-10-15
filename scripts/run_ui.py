#!/usr/bin/env python3
"""Serve the trace explorer UI over the callable RAG core."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    load_dotenv(repo_root() / ".env")
    parser = argparse.ArgumentParser(description="Open the Groundloop console.")
    # Hosting platforms pass HOST/PORT in the environment.
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args(argv)

    import uvicorn

    from swrag.api.app import app

    print(f"Groundloop: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
