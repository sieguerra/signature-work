# 008 — UI adapter

- decision: Serve a **LangSmith-style trace explorer** as a static page behind a **FastAPI** adapter. The RAG core stays callable from the CLI and from tests without the UI.
- date: 2026-09-10
- status: accepted (student-requested UI; LangSmith-like UX)

## Context

Issue #13 needs a working application UI after the loop already runs from the terminal. The architecture rules require the AI/RAG core to stay independent of the frontend. The student asked for something in the LangSmith family: submit a question, then inspect the run as a timeline of steps.

ADR 001 kept FastAPI out of the first slice. That constraint was for the baseline pipeline, not for this UI increment.

## Alternatives considered

1. **FastAPI + static HTML/CSS/JS** — one Python process; the UI only renders JSON the core already writes. No Node toolchain. Can still do a three-pane explorer (run list, waterfall, inspector).
2. **Streamlit** — fastest to ship; widget layout does not look like a trace product and tends to mix UI with pipeline calls.
3. **Vite + React SPA + FastAPI** — closest clone of LangSmith; adds a second language, a build step, and a lot of surface for one screen.

## Tradeoffs

A hand-built static page will never have LangSmith's component library. A React app would, at the cost of a frontend stack this project does not otherwise need. Streamlit would ship faster and look worse.

FastAPI is a new dependency. It is used only as an HTTP adapter: `src/swrag/api/` imports the core; the core never imports the API.

## Final choice

- FastAPI + uvicorn as the HTTP adapter
- Static explorer under `web/`
- Waterfall steps derived from the flat JSON trace (`swrag.tracing.steps`), not a second tracing format
- No billing, SSO, or team features

## Reason for the choice

It matches the issue (thin UI over a callable core) and the requested UX (run list + step inspector) without introducing a JavaScript framework for a single screen.
