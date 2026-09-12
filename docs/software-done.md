# Software definition of done

This is the checklist for the **software** Signature Work, not the thesis.
Related work stays on issues #15 and #16. Do not add billing, SSO, or LangGraph
here.

Harbor snapshot `experiments/results/20260910T070623/` is historical. Do not
overwrite it.

## Must be true before “software ready”

- [x] PRs [#30](https://github.com/sieguerra/signature-work/pull/30) and [#31](https://github.com/sieguerra/signature-work/pull/31) merged (delete runs + corpus toggle on `main`)
- [x] Loop and verification shipped ([#10](https://github.com/sieguerra/signature-work/issues/10), [#11](https://github.com/sieguerra/signature-work/issues/11) closed via #25/#26)
- [ ] [#32](https://github.com/sieguerra/signature-work/issues/32): at least one recorded loop run with `verification.outcome == improved` (or an explicit recorded failure after a good-faith attempt). Open PR: [#41](https://github.com/sieguerra/signature-work/pull/41). Judge wording and new gold ids need student confirmation.
- [ ] [#33](https://github.com/sieguerra/signature-work/issues/33): that run shows before/after in the explorer. Open PR: [#42](https://github.com/sieguerra/signature-work/pull/42)

## Should be true before quoting numbers

- [ ] [#37](https://github.com/sieguerra/signature-work/issues/37) gold audit (every cited id checked against the notes)
- [ ] [#38](https://github.com/sieguerra/signature-work/issues/38) hand-labelled judge sample (`n` and agreement counts)
- [ ] [#39](https://github.com/sieguerra/signature-work/issues/39) new timestamped snapshot **after** #32. Do not overwrite Harbor `20260910T070623`

## Later platform, not V1 blockers

- [#34](https://github.com/sieguerra/signature-work/issues/34) PDF ingest
- [#35](https://github.com/sieguerra/signature-work/issues/35) clickable citations — open PR [#43](https://github.com/sieguerra/signature-work/pull/43)
- [#36](https://github.com/sieguerra/signature-work/issues/36) eval pane — open PR [#44](https://github.com/sieguerra/signature-work/pull/44)

## Demo path (about 10 minutes)

1. `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
2. `python scripts/run_ui.py` → http://127.0.0.1:8000
3. **Retrieve-only, no key:** mode Retrieve only, Harbor or DKU, ask `When is the Harbor Institute Library open on Saturday?` You should see chunks, generate skipped.
4. **Corpus-gap abstain (needs key):** corpus Duke Kunshan, mode Loop, ask `What time does breakfast end at Halal Dining at the Conference Center?` You should see rewrite then `I do not know based on the retrieved documents.`
5. **Recovery that changes the answer (needs key, after #32/#41):** corpus Kestrel Aero, `top_k=1` if that control is on the branch, ask `What AMS specification letter is required for titanium plate on current Hangar 2 jobs?` You should see first-pass 2018 traveler, rewrite, then AMS 4911R, Verify = improved. In the explorer (after #33/#42) Before and After are both visible.
6. Cite snapshots by folder name only. Do not narrate “this proves recovery works.”
