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

