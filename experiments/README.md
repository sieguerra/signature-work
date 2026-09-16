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

Judge-agreement labels (issue #38) live under `judge-audit/`. See that
README. Do not overwrite `results/20260910T070623/`.

