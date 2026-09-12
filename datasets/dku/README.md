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

`gold/questions.jsonl` — 44 questions (34 answerable, 10 unanswerable). `dku-041`
through `dku-044` are recovery-oriented: the fact lives in one note, and the
question does not name that note (issue #32). Treat those ids as a proposed
split until student-confirmed. Every answerable row must be checked by hand
against the cited `.txt` files. Do not edit a question after it has results;
add a new id.

## Run

```bash
python scripts/run_experiment.py --retrieve-only \
  --gold datasets/dku/gold/questions.jsonl \
  --corpus datasets/dku/corpus

python scripts/run_benchmark.py --config experiments/configs/v2_dku_baseline_vs_loop.json
```
