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
- [ ] At least one **recorded** loop run with `verification.outcome == improved` (or an explicit recorded failure after a good-faith attempt). That recorded snapshot is [#39](https://github.com/sieguerra/signature-work/issues/39). Do not invent it.

## Should be true before quoting numbers

- [ ] [#37](https://github.com/sieguerra/signature-work/issues/37) gold audit: `audit.jsonl` files are a **substring search**, not your sign-off. Confirm spans yourself.
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
3. **Retrieve-only, no key:** mode Retrieve only, Harbor or DKU, ask `When is the Harbor Institute Library open on Saturday?` You should see chunks, generate skipped.
4. **Confirm recovery (needs key):** corpus Duke Kunshan, default mode **Loop (confirm recovery)**, ask `What time does breakfast end at Halal Dining at the Conference Center?` Diagnosis and a labeled recovery button should appear before rewrite/regenerate runs.
5. **Recovery contrast (needs key):** corpus Kestrel Aero, `top_k=1`, ask `What AMS specification does the titanium traveler require?` First-pass may retrieve the 2018 sheet (AMS 4911N). Confirm rewrite/regenerate and inspect Before/After. Verify may still be `still_failing`; do not treat one demo as the official result.
6. Cite snapshots by folder name only. Do not narrate “this proves recovery works.”
