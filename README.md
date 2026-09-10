# Signature Work

Software for **evaluation-guided Agentic RAG**: the system answers a question, evaluates the result, diagnoses a failure, recovers, and verifies whether recovery helped.

Built so far: **baseline RAG with JSON traces**, and the **offline evaluation foundation** (gold set, scoring, batch experiment harness). Runtime evaluation, diagnosis, recovery, and verification are Phase 1; the UI is later.

The measured contribution is **verification quality** — whether the system's own verdict that "recovery worked" is correct. See [ADR 002](docs/decisions/002-contribution-and-scope.md).

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

## Score the gold set

Runs every question in `datasets/gold/questions.jsonl` and writes a timestamped
result directory that is never overwritten:

```bash
python scripts/run_experiment.py --retrieve-only          # no API key
python scripts/run_experiment.py                          # needs OPENAI_API_KEY
```

Results are reported **per class** — answerable and unanswerable questions have
opposite success criteria, so a pooled average is misleading. Both are written
to `summary.json` along with which model backend produced them.

## Point at a different backend

Any OpenAI-compatible endpoint works. Set `OPENAI_BASE_URL` in `.env`.

The endpoint is recorded in every trace and summary, because a proxy can serve
a model named `gpt-4o-mini` without it being that model. Benchmark results are
only reproducible if the backend that produced them is known.

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
| `src/swrag/config.py` | Which model backend to call, recorded in every trace |
| `src/swrag/evaluation/` | Gold-set loader and offline EM/F1 scoring |
| `src/swrag/experiments/` | Batch harness with per-class aggregation |
| `datasets/corpus/` | Toy documents (original, fictional), including deliberate distractors |
| `datasets/gold/` | Hand-written questions and their ground truth |
| `docs/decisions/` | Architecture decision records |

Stub packages exist for diagnosis, recovery, verification, and orchestration so later work does not reshape the tree.

Decisions: [001 stack](docs/decisions/001-first-slice-stack.md), [002 contribution and scope](docs/decisions/002-contribution-and-scope.md), [003 evaluation method](docs/decisions/003-evaluation-method.md), [004 corpus difficulty](docs/decisions/004-corpus-difficulty.md), [005 failure taxonomy](docs/decisions/005-failure-taxonomy.md).
