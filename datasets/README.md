# Datasets

Local corpora for the explorer and for experiments. The UI loads **one corpus at
a time** (ADR 010). Switching the corpus rebuilds the in-memory index so
documents from two worlds never appear in the same top-4.

Listed in `registry.json`.

| Id | What it is | Fiction? |
|---|---|---|
| `harbor` | Harbor Institute campus (`datasets/corpus/`) | yes |
| `dku` | Duke Kunshan public-facts notes | no (leakage; ADR 009) |
| `northhaven-water` | Municipal water utility | yes |
| `orion-grid` | Rural electric cooperative | yes |
| `kestrel-aero` | Aerospace machine shop | yes |
| `porthaven-port` | Seaport authority | yes |
| `lumen-streetcar` | Urban streetcar | yes |
| `nimbus-seed` | Plant genebank | yes |
| `saltwind-coop` | Fishing cooperative | yes |
| `marlow-clinic` | Two-campus outpatient clinic | yes |

Industry worlds are invented so gold is local (ADR 003). Each has dated
near-neighbours (current vs superseded notice) and unanswerable traps (prices,
officer names).

Do not edit a gold row after it has results; add a new id. Harbor snapshot
`experiments/results/20260910T070623/` still scores Harbor only.

Recovery-oriented splits (issue #32) live beside the main gold as
`gold/recovery.jsonl` on DKU and Kestrel. They do not replace the main sets.

Regenerate industry folders (does not touch Harbor or DKU notes, and does not
overwrite an existing `gold/recovery.jsonl`):

```bash
python scripts/emit_industry_corpora.py
```
