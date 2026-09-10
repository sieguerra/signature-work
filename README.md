# Signature Work

Software for **evaluation-guided Agentic RAG**: the system answers a question, evaluates the result, diagnoses a failure, recovers, and verifies whether recovery helped.

The first working slice is **baseline RAG + JSON traces** only. Evaluation, diagnosis, recovery, and the UI are later issues.

## Setup

Python 3.11+. An OpenAI API key is only required when you want a generated answer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run without an API key (foundation)

Ingest the toy corpus, retrieve chunks, and write a JSON trace. Ranking uses a fake hashing embedder, not OpenAI:

```bash
python scripts/run_baseline.py --retrieve-only --question "When is the Harbor Institute Library open on Saturday?"
```

## Run full baseline RAG (needs OPENAI_API_KEY)

```bash
cp .env.example .env
# edit .env and set OPENAI_API_KEY
python scripts/run_baseline.py --question "When is the Harbor Institute Library open on Saturday?"
```

Both commands print retrieved chunk ids and write a new JSON trace under `experiments/output/` (gitignored). Existing traces are not overwritten.

Optional flags: `--corpus`, `--output-dir`, `--top-k`.

## Tests (no API key)

```bash
pytest
```

Tests use the same fake embedder, so chunking, ranking, and tracing do not call OpenAI.

## Layout

| Path | Role |
|---|---|
| `src/swrag/ingestion/` | Load local `.txt` files and chunk them |
| `src/swrag/retrieval/` | Embedder protocol, OpenAI embedder, in-memory index |
| `src/swrag/generation/` | OpenAI generation from evidence |
| `src/swrag/tracing/` | Per-run JSON traces |
| `src/swrag/pipeline/` | Baseline `run_query` |
| `datasets/corpus/` | Toy documents (original, fictional) |
| `docs/decisions/` | Architecture decision records |

Stub packages exist for evaluation, diagnosis, recovery, verification, and orchestration so later work does not reshape the tree.

Stack choice for this slice: [docs/decisions/001-first-slice-stack.md](docs/decisions/001-first-slice-stack.md).
