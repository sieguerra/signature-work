Traces from `scripts/run_baseline.py` and batch runs live under `output/` as
one JSON file per run. That directory is gitignored. The tracer and the
experiment runner refuse to overwrite an existing file.

Comparison snapshots from `scripts/run_benchmark.py` live under `results/`.
Those are small (no chunk text) and are meant to be committed so a run can be
cited later. Re-running with the same `--label` is rejected.

Reproduce the V1 baseline vs evaluation-guided comparison:

```bash
python scripts/run_benchmark.py --config experiments/configs/v1_baseline_vs_loop.json
```

`--retrieve-only` exercises the same config with a fake embedder and no OpenAI
calls. It is a harness check, not a quality result.

The two conditions share one corpus index so embedding the documents is paid
once (`setup_usage` in `comparison.json`). They also share the embedder's
text cache, so the second condition's embedding-token total omits queries
already embedded during the first condition. Chat tokens and wall-clock
latency are not affected by that cache.

Issue #32 recovery gold (underspecified questions, `top_k=1`):

```bash
python scripts/run_benchmark.py --config experiments/configs/v2_dku_recovery_vs_loop.json
```

Issue #69 first-pass-fail gold (answerable misses at `top_k=1`, expand budget 2):

```bash
python scripts/run_benchmark.py --config experiments/configs/v3_kestrel_expand_vs_loop.json
python scripts/run_benchmark.py --config experiments/configs/v3_dku_expand_vs_loop.json
```

Committed snapshots from those two commands (do not overwrite). These are
`top_k` 1 stress tests on 5 questions each, not the full sets:

- `results/20260927T151157/` — Kestrel first-pass-fail
- `results/20260927T151544/` — DKU first-pass-fail

Issue #100 full gold on the current loop (`top_k` 4, `max_recoveries` 2,
student-signed gold from #99, whole-word contains-answer from #110):

```bash
python scripts/run_benchmark.py --config experiments/configs/v4_harbor_full_current_loop.json
python scripts/run_benchmark.py --config experiments/configs/v4_dku_full_current_loop.json
python scripts/run_benchmark.py --config experiments/configs/v4_kestrel_full_current_loop.json
```

Committed snapshots from those commands (do not overwrite). They are the
current-loop record. They are one run each with a live model, and they are not
by themselves evidence that recovery works:

- `results/20261010T203121/` — Harbor, 32 questions
- `results/20261010T203115/` — DKU, 40 questions
- `results/20261010T202849/` — Kestrel, 16 questions

Judge-agreement labels (issue #38) live under `judge-audit/`. See that
README. Do not overwrite `results/20260910T070623/`.

