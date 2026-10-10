# Software definition of done

This is the checklist for the **software** Signature Work, not the thesis.
Related work stays on issues #15 and #16. Do not add billing, SSO, or LangGraph
here.

Harbor snapshot `experiments/results/20260910T070623/` is historical. Do not
overwrite it.

## Must be true before “software ready”

- [x] PRs [#30](https://github.com/sieguerra/signature-work/pull/30) and [#31](https://github.com/sieguerra/signature-work/pull/31) merged (delete runs + corpus toggle on `main`)
- [x] Loop and verification shipped ([#10](https://github.com/sieguerra/signature-work/issues/10), [#11](https://github.com/sieguerra/signature-work/issues/11) closed via #25/#26)
- [x] [#32](https://github.com/sieguerra/signature-work/issues/32) software: span-check judge, constrained regenerate, `recovery.jsonl`, playground `top_k`. Merged in [#41](https://github.com/sieguerra/signature-work/pull/41). Judge wording and recovery gold still need student confirmation before quoting scores.
- [x] [#33](https://github.com/sieguerra/signature-work/issues/33) explorer Before/After: merged in [#42](https://github.com/sieguerra/signature-work/pull/42)
- [x] At least one **recorded** loop run with `verification.outcome == improved`. Snapshots: Kestrel `experiments/results/20260927T151157/` and DKU `experiments/results/20260927T151544/` ([#39](https://github.com/sieguerra/signature-work/issues/39)). Harbor `20260910T070623` is unchanged. These folders are the record; they are not a thesis conclusion.

## Should be true before quoting numbers

- [x] [#99](https://github.com/sieguerra/signature-work/issues/99) gold audit: Harbor, DKU, and Kestrel `audit.jsonl` rows signed off by the student on 2026-10-11 after the worksheet and AI review in `experiments/gold-audit/`. `tests/test_corpus_registry.py` rejects `substring-search` for those three. The other industry collections are still a substring search and are not used in the study.
- [x] [#100](https://github.com/sieguerra/signature-work/issues/100) full gold on the current loop: Harbor `experiments/results/20261010T203121/`, DKU `20261010T203115/`, Kestrel `20261010T202849/` (`top_k` 4, `max_recoveries` 2). The 27 September folders stay as the `top_k` 1 stress tests.
- [ ] [#38](https://github.com/sieguerra/signature-work/issues/38) hand-labelled judge sample (`n` and agreement counts). Template: `experiments/judge-audit/`
- [ ] [#39](https://github.com/sieguerra/signature-work/issues/39) new timestamped snapshot **after** recovery can change the answer. Do not overwrite Harbor `20260910T070623`

## Later platform, not V1 blockers

- [x] [#34](https://github.com/sieguerra/signature-work/issues/34) PDF ingest — page-aware chunks; OCR / Drive still out of scope
- [x] [#35](https://github.com/sieguerra/signature-work/issues/35) clickable citations — merged in [#43](https://github.com/sieguerra/signature-work/pull/43)
- [x] [#36](https://github.com/sieguerra/signature-work/issues/36) eval pane — merged in [#44](https://github.com/sieguerra/signature-work/pull/44)

Explorer recover-confirm ([#48](https://github.com/sieguerra/signature-work/issues/48), [#51](https://github.com/sieguerra/signature-work/issues/51)), waterfall rewrite display ([#50](https://github.com/sieguerra/signature-work/issues/50)), and DKU rewrite guard ([#52](https://github.com/sieguerra/signature-work/issues/52)) are on `main`.

## Demo path (about 10 minutes)

1. `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
2. `python scripts/run_ui.py` → http://127.0.0.1:8000
3. Open **Test Console**. The sidebar lists Overview, Test Console, Reliability, Data, Configuration, and Integrations.
4. **Retrieve only, no key.** The page title is Duke Kunshan University. The System picker says **No system yet**, because built-in corpora are read-only and are not listed there. Run mode **Retrieve only**, recovery policy **Current v1**, ask `What are breakfast hours at University Dining in the Academic Building?` Retrieved passages appear. Generation is skipped. Without `OPENAI_API_KEY`, Baseline, Confirm recovery, and Auto recovery cannot run.
5. **Confirm recovery (needs a key).** Restart after the key is in `.env`. Stay on Duke Kunshan University, run mode **Confirm recovery**, policy **Current v1**, ask `What time does breakfast end at Halal Dining at the Conference Center?` A diagnosis and a recovery action should appear before rewrite or regenerate runs. **Gap-aware (Guarded)** is a separate policy. Leave it unselected unless you mean to demo that policy.
6. **Recovery contrast (needs a key).** The System picker still will not list Kestrel Aero until a writable system exists, so this contrast is not a click on that picker. Use the Kestrel corpus from the benchmark config, or create a system and upload those notes. Retrieval depth **1**, run mode **Confirm recovery**, ask `What AMS specification does the titanium traveler require?` The first pass may retrieve the 2018 sheet (AMS 4911N). Inspect the run under **Reliability**. Verification may still be `still_failing`. Do not treat one demo as the official result.
7. Cite snapshots by folder name only. Do not narrate “this proves recovery works.” Do not overwrite Harbor `experiments/results/20260910T070623/`.
