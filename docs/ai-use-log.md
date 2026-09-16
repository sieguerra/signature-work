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
treated as successful recoveries.

How I verified the result:
`pytest` with fakes for first-pass vs apply, 409/400 API cases, and a
browser check of the confirm mode and recovery buttons.



