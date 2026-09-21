# Duke Kunshan corpus and gold set

Local documents about **Duke Kunshan University**, written as original short notes
grounded in public web pages retrieved on 2026-09-10. They are not HTML dumps.

The Harbor Institute corpus in `datasets/corpus/` is unchanged. The #12 snapshot
under `experiments/results/20260910T070623/` still scores Harbor and must not be
overwritten.

## Why this exists

The first Harbor run accepted 27/32 questions on the first pass. This set is
meant to be harder and closer to campus life: two libraries-in-name (Kunshan vs
Durham), two dining buildings, a 2021 handbook vs a 2026 hours page, and a
January 2025 brochure vs that hours page.

## Leakage (read this)

ADR 003 used a fictional corpus so the model could not already know the answers.
A real university reopens **pretraining leakage**, especially on unanswerable
officer / tuition / enrollment questions. That is a limitation to report, not
something this folder hides. Unanswerable items `dku-036`–`dku-038` exist so
abstention can be tested when the model may still “know” the fact.

## Documents

| File | Role |
|---|---|
| `dku-about.txt` | Partnership, dates, 200 acres, address |
| `dku-library-hours.txt` | Current website hours and contacts |
| `dku-library-guide-202501.txt` | January 2025 brochure (desk hours differ) |
| `dku-library-handbook-2021.txt` | Superseded Academic Building rooms + old phone |
| `academic-building-dining.txt` | University Dining and Executive Dining |
| `conference-center-dining.txt` | Halal Dining (no breakfast listed) |
| `conference-center.txt` | Rooms and auditorium |
| `registrar-fall-2026.txt` | Fall 2026 dates |
| `registrar-spring-2027.txt` | Spring 2027 dates, commencement |
| `getting-to-dku.txt` | Airport/station distances, Kunshan South taxi |
| `dayu-bay.txt` | 500 m, no restaurant names |
| `wuhan-university.txt` | Partner university in Hubei |
| `duke-university-durham.txt` | Durham campus; no Perkins hours |
| `cscc.txt` | Center for the Study of Contemporary China |

## Gold

`gold/questions.jsonl` — 40 questions (`dku-001`–`dku-040`). Every answerable
row must be checked by hand against the cited `.txt` files. Do not edit a
question after it has results; add a new id.

`gold/recovery.jsonl` — issue #32 split (`dku-041`–`dku-052`). Underspecified
contrast questions over the same notes; they do **not** name the dated source.
Hours and phone gold is the current Locations & Hours page. Unique brochure
facts (seats, Tea House, Meditation Room) stay on the January 2025 guide.
Three rows are unanswerable so abstention can still be tested. Harbor gold and
`questions.jsonl` are unchanged.

If these questions still first-pass accept at `top_k=4`, use `top_k=1`
(`experiments/configs/v2_dku_recovery_vs_loop.json`) rather than editing old gold.

`gold/first-pass-fail.jsonl` (`dku-053`–`dku-057`) is an issue #69 split:
answerable questions that miss the supporting note at `top_k=1` and hit it
at `top_k=8`, plus one unanswerable row. Use
`experiments/configs/v3_dku_expand_vs_loop.json` (`max_recoveries: 2`).

`gold/audit.jsonl` lists every id in `questions.jsonl`. Those rows are a
substring search, not a student sign-off. Do not quote DKU scores until you
have personally confirmed the spans. Recovery ids in `recovery.jsonl` are a
proposed split until you confirm them.

## Run

```bash
python scripts/run_experiment.py --retrieve-only \
  --gold datasets/dku/gold/questions.jsonl \
  --corpus datasets/dku/corpus

python scripts/run_benchmark.py --config experiments/configs/v2_dku_baseline_vs_loop.json
python scripts/run_benchmark.py --config experiments/configs/v2_dku_recovery_vs_loop.json
```
