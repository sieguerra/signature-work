# Signature Work

Software for **evaluation-guided Agentic RAG**: the system answers a question, evaluates the result, diagnoses a failure, recovers, and verifies whether recovery helped.

Built so far: baseline RAG, offline scoring, runtime grounding judge, diagnosis,
constrained regenerate, **query rewrite + second retrieve**, runtime
verification, the evaluate → diagnose → recover → verify loop, a **trace
explorer UI**, and the baseline-vs-loop benchmark.

The measured contribution is **verification quality** — whether the system's own verdict that "recovery worked" is correct. See [ADR 002](docs/decisions/002-contribution-and-scope.md).

## Setup

Python 3.11+. An OpenAI API key is only required when you want a generated answer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run without an API key (foundation)

Ingest the DKU corpus, retrieve chunks, and write a JSON trace. Ranking uses a fake hashing embedder, not OpenAI:

```bash
python scripts/run_baseline.py --retrieve-only --question "What are breakfast hours at University Dining in the Academic Building?"
```

## Run full baseline RAG (needs OPENAI_API_KEY)

```bash
cp .env.example .env
# edit .env and set OPENAI_API_KEY
python scripts/run_baseline.py --question "What are breakfast hours at University Dining in the Academic Building?"
```

Both commands print retrieved chunk ids and write a new JSON trace under `experiments/output/` (gitignored). Existing traces are not overwritten.

Optional flags: `--corpus`, `--output-dir`, `--top-k`, `--evaluate`, `--recover`.

`--evaluate` runs the LLM grounding judge (ADR 003) and writes
`evidence_sufficient` / `answer_supported` onto the trace. It never reads the
gold set. Needs `OPENAI_API_KEY`.

`--recover` runs the evaluation-guided loop (implies `--evaluate`): diagnose,
maybe constrained-regenerate, then verify improved / unchanged / degraded /
still_failing.

## Score the gold set

Runs every question in `datasets/dku/gold/questions.jsonl` (default) and writes a
timestamped result directory that is never overwritten. The Harbor gold set is
still at `datasets/gold/questions.jsonl`.

```bash
python scripts/run_experiment.py --retrieve-only          # no API key
python scripts/run_experiment.py                          # needs OPENAI_API_KEY
python scripts/run_experiment.py --evaluate               # also writes runtime judge flags on each trace
```

Results are reported **per class** — answerable and unanswerable questions have
opposite success criteria, so a pooled average is misleading. Both are written
to `summary.json` along with which model backend produced them.

## Benchmark baseline vs evaluation-guided recovery (issue #12)

Same gold set, two conditions, one shared corpus index. Default config is the
DKU set: `experiments/configs/v2_dku_baseline_vs_loop.json`. Reproduce the
Harbor snapshot with `--config experiments/configs/v1_baseline_vs_loop.json`
(do not overwrite `experiments/results/20260910T070623/`).

```bash
python scripts/run_benchmark.py --retrieve-only   # harness check, no API key
python scripts/run_benchmark.py                   # needs OPENAI_API_KEY
```

Each batch writes:

- traces under `experiments/output/<label>/` (gitignored)
- a comparison snapshot under `experiments/results/<label>/` (committed; never overwritten)

The snapshot records per-class quality, wall-clock latency, OpenAI token usage
when the API returns it, and a contingency table of runtime verification
outcomes against gold F1 delta (ADR 002). The command prints numbers. It does
not interpret them.

## Trace explorer UI

A LangSmith-style three-pane explorer over the same core (ADR 008). It does not
own retrieval, judging, or recovery.

```bash
python scripts/run_ui.py
# open http://127.0.0.1:8000
```

Ask a question in the playground, or inspect traces already under
`experiments/output/<corpus-id>/`. The **Corpus** control in the top bar picks
one world at a time so retrieval never mixes DKU notes with a water utility.
Each run can be deleted, or **Delete all** clears traces for the active corpus
only. Loop and baseline need `OPENAI_API_KEY`. Retrieve-only does not.

When the software is ready for a mentor demo, use [docs/software-done.md](docs/software-done.md).

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
| `src/swrag/diagnosis/` | First-pass + rewrite-outcome labels |
| `src/swrag/recovery/` | Regenerate, query rewrite, accept/abstain |
| `src/swrag/verification/` | Runtime improved / degraded / still_failing |
| `src/swrag/orchestration/` | Evaluate → diagnose → recover → verify loop |
| `src/swrag/config.py` | Which model backend to call, recorded in every trace |
| `src/swrag/evaluation/` | Gold-set loader, offline EM/F1, runtime grounding judge |
| `src/swrag/experiments/` | Batch harness, baseline-vs-loop comparison, per-class aggregation |
| `src/swrag/api/` | FastAPI adapter; does not own RAG logic |
| `web/` | Static trace explorer (run list, waterfall, inspector) |
| `experiments/configs/` | Reproducible experiment JSON |
| `experiments/results/` | Committed comparison snapshots (never overwritten) |
| `datasets/registry.json` | Named corpora for the UI toggle (one index at a time) |
| `datasets/dku/` | DKU public-facts corpus and gold (UI / V2 default) |
| `datasets/corpus/` | Harbor Institute fictional corpus (V1 snapshot) |
| `datasets/gold/` | Harbor gold set |
| `docs/decisions/` | Architecture decision records |

Stub packages are gone for the Phase 1 core.

Decisions: [001 stack](docs/decisions/001-first-slice-stack.md), [002 contribution and scope](docs/decisions/002-contribution-and-scope.md), [003 evaluation method](docs/decisions/003-evaluation-method.md), [004 corpus difficulty](docs/decisions/004-corpus-difficulty.md), [005 failure taxonomy](docs/decisions/005-failure-taxonomy.md), [006 recovery policy](docs/decisions/006-recovery-policy.md), [007 query rewrite](docs/decisions/007-query-rewrite.md), [008 UI adapter](docs/decisions/008-ui-adapter.md), [009 DKU corpus](docs/decisions/009-dku-corpus.md), [010 isolated industry corpora](docs/decisions/010-isolated-industry-corpora.md).
