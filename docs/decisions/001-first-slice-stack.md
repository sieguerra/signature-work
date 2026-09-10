# 001 — First-slice stack

- decision: Use Python for the RAG core, in-memory embeddings over local files for retrieval, and OpenAI for embeddings and generation.
- date: 2026-09-10
- status: accepted (student-confirmed for V1 first slice)

## Context

The repository was docs-only. The first working slice needs a runnable baseline: ingest a tiny local corpus, retrieve, generate an answer, and write a trace. This decision is only for that slice. Later ADRs can change the retriever, models, or agent framework without rewriting the whole project if interfaces stay narrow.

## Alternatives considered

### Language

1. **Python** — standard for RAG research, evaluation, and experiments; UI can be a separate app later.
2. **TypeScript end-to-end** — one language if the UI comes first; weaker research and evaluation ecosystem.

### Retrieval

1. **In-memory embeddings + local files** — no extra database; enough for a toy corpus; easy to swap later behind an `Index` interface.
2. **Chroma or FAISS from day one** — closer to a “real” stack; extra moving part before a pipeline exists.
3. **Keyword search only (BM25)** — simplest; weaker if later claims assume embeddings.

### Generation / embeddings provider

1. **OpenAI API** — one key for chat and embeddings; easy to run locally with `.env`.
2. **Anthropic + local embeddings** — splits providers.
3. **Local Ollama** — no cloud API; more setup and weaker embedding story for a first slice.

## Tradeoffs

Python plus OpenAI adds a paid API dependency and is not “production scale.” In-memory retrieval will not serve a large corpus. Those costs are acceptable because V1 explicitly outscopes production infrastructure, and the first slice is a handful of documents.

A vector database now would make the first slice harder to explain and debug. BM25 would postpone embedding-based retrieval that the later pipeline is likely to need.

## Final choice

- Language: **Python 3.11+**, package `swrag` under `src/`
- Retrieval: **in-memory cosine similarity** over OpenAI embeddings of local `.txt` files
- Models (defaults): **`text-embedding-3-small`** and **`gpt-4o-mini`**
- Types: **dataclasses** (no Pydantic in this slice)
- No LangChain, LangGraph, Chroma, or FastAPI in this slice

## Reason for the choice

The student confirmed this stack for GitHub issue #1. It is the smallest setup that still produces a real RAG answer and a structured trace, while keeping ingestion, retrieval, generation, and tracing as separate modules.
