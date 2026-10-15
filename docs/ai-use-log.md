# Generative AI Use Log

Record meaningful AI assistance used during Signature Work development.

Minor autocomplete does not need a separate entry unless required by mentor guidance.

## Template

### Date
Tool:

Purpose:

What AI assisted with:

Important suggestions produced:

What I independently decided or changed:

How I verified the result:

---

### Example

Date: 2026-09-01

Tool: Cursor

Purpose: Architecture brainstorming

What AI assisted with:
Compared using LangGraph versus a custom state machine.

Important suggestions produced:
Outlined advantages and disadvantages of both approaches.

What I independently decided or changed:
Selected ______ because ______.

How I verified the result:
Reviewed framework documentation and discussed the architecture with my mentor.

---

Date: 2026-09-10

Tool: Cursor

Purpose: Implement the issue #12 benchmark harness and reuse the corpus index.

What AI assisted with:
Boilerplate for a config-driven two-condition runner, usage counters on OpenAI
wrappers, and tests that do not call the API.

Important suggestions produced:
Embed the corpus once and share the index across questions and query-rewrite
recovery, otherwise latency and cost are dominated by re-embedding.

What I independently decided or changed:
Same gold set; baseline is retrieve-then-generate with no judge; the loop uses
the grounding judge and at most one recovery. Results record quality, latency,
token usage, and a verification-vs-gold F1 table without interpreting them.

How I verified the result:
`pytest` with fake embedder / scripted judge, then a live `run_benchmark.py`
run whose snapshot is under `experiments/results/`.

---

Date: 2026-09-10

Tool: Cursor

Purpose: Thin LangSmith-style UI over the callable core (issue #13).

What AI assisted with:
FastAPI adapter boilerplate, waterfall-step mapping from the existing JSON
trace, and static HTML/CSS/JS for the three-pane explorer.

Important suggestions produced:
Keep the UI as an HTTP adapter plus static files rather than Streamlit or a
React SPA, so the RAG core stays importable without the frontend.

What I independently decided or changed:
Requested a LangSmith-like run list / waterfall / inspector. Confirmed FastAPI
plus static files. No billing or auth.

How I verified the result:
`pytest` for the adapter and page assets; curl against a local server. No
browser automation was available in this environment.

---

Date: 2026-09-10

Tool: Cursor

Purpose: Add a Duke Kunshan University corpus and gold set.

What AI assisted with:
Fetched public DKU pages and drafted original short notes plus gold questions
with contrast pairs (library hours vs 2025 brochure vs 2021 handbook; Academic
Building dining vs Conference Center Halal; Kunshan vs Durham).

Important suggestions produced:
Keep the Harbor corpus and the #12 snapshot. Do not paste full webpages into
the repo. Record pretraining leakage as a limitation of using a real university.

What I independently decided or changed:
Asked for DKU-related data after Harbor results existed. Harbor stays the V1
historical set. New questions use `dku-*` ids.

How I verified the result:
`pytest` gold-loader tests; retrieve-only experiment on the DKU gold set.
Every gold row still needs a hand check against the `.txt` files.

---

Date: 2026-09-16

Tool: Cursor

Purpose: Make recovery actually change the answer (issue #32).

What AI assisted with:
Stricter LLM-judge prompt, a deterministic span check that can override a
lenient `answer_supported=true`, playground `top_k`, recovery gold JSONL, and
tests that do not call the API.

Important suggestions produced:
Keep Harbor gold and `experiments/results/20260910T070623/` frozen. Put new
questions in `recovery.jsonl` with new ids. Use `top_k=1` for the recovery
config if `top_k=4` still first-pass accepts.

What I independently decided or changed:
Confirmed the three issue #32 levers. Gold for underspecified DKU hours/phone
is the current Locations & Hours page; unique brochure facts stay on the
January 2025 guide. Kestrel traveler gold is the 2025 spec letter. The span
check only extracts times, emails, ordinals, spec letters, and 3+ digit
numbers; it does not read gold.

How I verified the result:
`pytest` with fake embedder / fixture judge completions. A live loop run is
extra and must not overwrite the Harbor snapshot.

---

Date: 2026-09-16

Tool: Cursor

Purpose: Show first-pass and post-recovery answers in the explorer (issue #33).

What AI assisted with:
Waterfall mapping from the existing flat `TraceRecord`, storing first-pass
chunks on rewrite, and Before/After rendering in the static explorer.

Important suggestions produced:
Do not invent a first-pass retrieve list. Put recover between the two generate
steps so a demo reads first answer → action → second answer → verify. Stored
evaluate flags after recovery are labeled as such; first-pass evaluate is not
fabricated.

What I independently decided or changed:
Kept recover/verify as the same step kinds. Accept traces still show one
answer. Query inspector shows original vs rewritten search string when present.

How I verified the result:
`pytest` step-mapping and API asset tests. Browser check of accept vs rewrite
runs in the explorer.

---

Date: 2026-09-16

Tool: Cursor

Purpose: Make chunk citations clickable in the explorer (issue #35).

What AI assisted with:
A small citation parser shared in spirit between `swrag.tracing.citations`
and `web/app.js`, plus answer-bar buttons that select the matching retrieve
chunk.

Important suggestions produced:
Link only ids that are in this trace's retrieve lists. Tokens that look like
`{doc_id}::c{nnn}` but are missing get a "not in this retrieve" note instead
of binding to another chunk. Escape all non-citation text.

What I independently decided or changed:
Before-answer citations open the first-pass retrieve when those chunks were
stored. After-answer citations open the post-recovery retrieve. Do not change
the generator prompt.

Date: 2026-09-16

Tool: Cursor

Purpose: Confirm recovery after diagnosis in the explorer (issue #48).

What AI assisted with:
Splitting the loop into `run_first_pass` and `apply_recovery`, HTTP
`loop_confirm` plus `POST /api/runs/{id}/recover`, and explorer buttons
labeled with V1 actions.

Important suggestions produced:
Keep automatic `loop` as the default so benchmarks stay one-shot. Persist
proposals on a first-pass file and write a new child on apply so traces are
never overwritten. Record `recovery.source` as `policy` or `operator`.

What I independently decided or changed:
Operator override is allowed among regenerate / rewrite / abstain / accept.
Accept on first pass is already finished (no button). Proposed traces are not
treated as successful recoveries. Playground default is confirm recovery;
automatic `loop` stays available and is still what benchmarks call.

How I verified the result:
`pytest` with fakes for first-pass vs apply, 409/400 API cases, and a
browser check of the confirm mode and recovery buttons.

---

Date: 2026-09-17

Tool: Cursor

Purpose: Make confirm recovery the playground default.

What AI assisted with:
Dropdown order/default so the explorer starts in `loop_confirm`.

Important suggestions produced:
Do not change the experiment runner; automatic `run_with_recovery` remains
the benchmark path.

What I independently decided or changed:
Manual confirm is the explorer default for now, because automatic rewrite
often ends `still_failing` and the operator should see the proposal first.

How I verified the result:
API asset test for the selected `loop_confirm` option.

---

Date: 2026-09-17

Tool: Cursor

Purpose: Fix explorer mapping when rewrite recovery has an empty first-pass answer (issue #50).

What AI assisted with:
Widening the recovered-trace gate and an Evaluate note for rewrite-retrieve probe flags.

Important suggestions produced:
Do not re-judge the canned abstain on rewrite-fail; that would change stored
verification semantics. Do not change the rewrite prompt in this fix.

What I independently decided or changed:
A trace is recovered if it has a previous answer, a rewritten query, stored
first-pass chunks, or an applied regenerate/rewrite/abstain. The answer bar
still shows the rewritten query when Before is empty.

How I verified the result:
`pytest` waterfall and rewrite-then-abstain history assertions.

---

Date: 2026-09-17

Tool: Cursor

Purpose: Stop query rewrite from expanding DKU into the wrong university (issue #52).

What AI assisted with:
Prompt wording plus a deterministic guard that falls back to the original
question if the rewrite adds university/college/institute tokens.

Important suggestions produced:
Do not look up gold labels. Do not pass corpus registry names into rewrite
in this change (that was option 2).

What I independently decided or changed:
Chose option 1 from the issue: never expand abbreviations; keep DKU as
written unless the expansion is already in the question. The guard is the
testable part.

How I verified the result:
Unit tests for the Dongkuk rewrite and a Harbor rewrite that already
contains Institute.

---

Date: 2026-09-17

Tool: Cursor

Purpose: Update the software demo checklist after merging the open fix PRs (issue #40).

What AI assisted with:
Rewriting checkboxes so merged PRs are marked shipped without claiming a live
`improved` snapshot or a finished gold/judge audit.

Important suggestions produced:
Keep #39, #37 (human sign-off), and #38 (filled labels) unchecked.

What I independently decided or changed:
Demo path uses confirm-recovery as the default and does not promise Verify =
improved on one Kestrel question.

How I verified the result:
Checked GitHub issue/PR state after the merge pass.

---

Date: 2026-09-17

Tool: Cursor

Purpose: Ingest local PDFs as page-citable documents (issue #34).

What AI assisted with:
Loader/extractor boilerplate, a tiny two-page fixture PDF, and tests that do
not call OpenAI.

Important suggestions produced:
pypdf behind a small extract function, not a second extracted-.txt copy
(ADR 009). One document per PDF page so chunk ids stay
`{stem}::p{page}::c{index}`. Skip empty/corrupt PDFs instead of indexing
blank stand-ins. OCR, Drive, and HTML remain out of scope.

What I independently decided or changed:
Followed the issue's loader-protocol design. Existing `.txt` corpora and the
Harbor snapshot stay unchanged. Adding a PDF on disk still requires rebuild.

How I verified the result:
`pytest` including retrieve-only over the fixture PDF. Harbor
`experiments/results/20260910T070623/` untouched.

---

Date: 2026-09-17

Tool: Cursor

Purpose: Fix explorer/API hygiene for issues #55–#59 (cascade delete, run-list
links, eval counts, first-pass diagnosis copy, confirm-recovery API default).

What AI assisted with:
Cascade delete of recovered children, `latency_ms` on playground traces,
eval strip proposed/latency counts, run-list pills, and tests.

Important suggestions produced:
Keep proposed rewrites out of `by_action` so confirm + apply is not two
rewrites. Do not change ADR 007 first-pass miss-vs-gap deferral. Leave
PDF ingest (#34), snapshot (#39), and judge labels (#38) alone.

What I independently decided or changed:
One PR for the five overlapping explorer/API files. API `POST /api/runs`
default matches the explorer (`loop_confirm`). Deleting a child leaves
the parent proposed so recovery can be applied again.

How I verified the result:
`pytest` (no live OpenAI). Harbor snapshot directory untouched.

---

Date: 2026-09-21

Tool: Cursor

Purpose: Implement multi-attempt recovery, expand, and first-pass-fail gold
(issues #67–#69).

What AI assisted with:
Recovery budget loop, `expand` (widen `top_k`), first-pass-fail gold splits,
v3 benchmark configs, explorer labels, and tests.

Important suggestions produced:
Keep default `max_recoveries` at 1 so Harbor/DKU SequenceJudge tests and
committed configs do not escalate. First-pass insufficiency still selects
rewrite (ADR 007). Weak retrieval the judge accepted selects expand. Top-level
verification is first-pass vs final; `recovery_attempts` stores intermediates.
Do not edit existing gold rows.

What I independently decided or changed:
`k=1` expands to 8. Playground auto-loop uses budget 2; Evaluation stays
confirm-recovery. New gold ids only (`ka-020`–`ka-024`, `dku-053`–`dku-057`).
No benchmark snapshot was written.

How I verified the result:
`pytest` including FakeEmbedder ranking of the new gold (miss at `top_k=1`,
hit at `top_k=8`). Harbor `experiments/results/20260910T070623/` untouched.

---

Date: 2026-09-21

Tool: Cursor

Purpose: Ship the external evaluation API, project-scoped hashed keys, and
isolation tests (issues #78–#80).

What AI assisted with:
`POST /api/v1/evaluations` adapter, SHA-256 project keys, playground key UI,
and cross-project isolation tests.

Important suggestions produced:
Keep dashboard `/api/*` unauthenticated. Bind `/api/v1/*` to hashed
`swr_` keys stored in `keys.json`, not `project.json`. Do not apply rewrite
or expand on external runs; name them in `unavailable_actions`. Index cache
key includes corpus id and resolved corpus dir. Isolation tests must not
lock a shared `traces_dir`.

What I independently decided or changed:
Bearer or `X-Api-Key`. Size limits on query/answer/contexts. Recover looks
up the parent trace before requiring `OPENAI_API_KEY`, so a guessed id from
another project is 404. No billing (#81).

How I verified the result:
`pytest` with a scripted judge (no live OpenAI on the v1 path). Harbor
`experiments/results/20260910T070623/` untouched.

---

### 2026-10-15

Tool: Claude Code (Claude Opus)

Purpose: Backend and engine audit, fixes, and the decisions left open by it

What AI assisted with:
Audited the engine, scoring and benchmarks (issues #130 to #148), wrote the
fixes (PRs #149 to #161), reran the three v4 benchmarks live on the hardened
prompts, rescored the frozen snapshots without model calls, and drafted
`docs/results-note.md` from the stored numbers.

Important suggestions produced:
seed-007 relabelled answerable; false-premise rejections count as
abstentions, with a near-neighbour trap for seed-009 (#158); an expand at the
top_k cap does not use the recovery budget (#159); evidence delimited as
untrusted data (#161); report rank-rule agreement, answerable-only as the
headline (#132, #155).

What I independently decided or changed:
I asked Claude to make these decisions on my behalf. I still need to review
each one, and rewrite the results note in my own words before citing it.

How I verified the result:
`pytest` (offline, scripted judge) and CI on every PR. Earlier snapshots in
`experiments/results/` are untouched; the 2026-10-15 reruns are new folders.
The second reviewer for #107 has to be a person and is still open.

---

### 2026-10-16

Tool: Claude Code (Claude Opus)

Purpose: Harder benchmark, cost-matched baseline, wrong-source check, paper revision

What AI assisted with:
Added the wrong-source and provenance checks (#163, #164), per-condition
retrieval depth, the v5 depth sweep configs, and the sweep summary script.
Ran the sweep three times per collection (#165) and rescored earlier runs
(#166). Revised `paper/signature-work.tex` (abstract, methods, results,
discussion, conclusions) from those folders.

Important suggestions produced:
Compare the loop with a plain top_k 8 baseline; report fixed and broken
counts per repeat; disclose the gold-029 relabelling as a false repair.

What I independently decided or changed:
I asked Claude to do this work and draft the paper revision. I still need to
check every number against its folder, own the discussion and conclusions,
and write the Signature Work narrative myself.

How I verified the result:
`pytest` and CI on every PR. Each paper figure is copied from
`experiments/rescored/v5-sweep-20261015/summary.json` or a named rescore
folder.

