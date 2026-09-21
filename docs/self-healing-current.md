# Self-healing: the workflow as implemented

This describes what the code **actually does** today, not what the ADRs intend.
Every claim cites the file and function that implements it. Where the
implementation falls short of `AGENTS.md`, that is recorded in
[Actual weaknesses](#actual-weaknesses) rather than smoothed over.

Written for issue #63. Snapshot of `main` at the time of writing.

## Contents

- [Shape of the flow](#shape-of-the-flow)
- [Entry points](#entry-points)
- [Inputs](#inputs)
- [Evaluation](#evaluation)
- [Failure detection](#failure-detection)
- [Diagnosis](#diagnosis)
- [Healing](#healing)
- [Validation](#validation)
- [Persistence](#persistence)
- [Human interaction](#human-interaction)
- [UI](#ui)
- [API routes](#api-routes)
- [Tests](#tests)
- [Actual weaknesses](#actual-weaknesses)

## Shape of the flow

```
retrieve ─→ generate ─→ judge ─→ diagnose ─→ select action ─→ apply action
                                                                     │
                                                          re-judge ──┤
                                                                     │
                              if still failing and budget remains ───┤
                                                                     │
                                                            verify ──┴─→ write trace
```

`run_with_recovery` honors `max_recoveries` as a count of applied actions
(issue #67). Default remains 1. When the budget is greater than 1, a
still-failing attempt can escalate to a different action, usually `expand`
(issue #68). Top-level `verification` compares first-pass flags to the final
state; `recovery_attempts` records each step.

## Entry points

There are two, and they differ only in whether the selected action runs
immediately.

| Function | File | Behavior |
|---|---|---|
| `run_with_recovery` | `orchestration/loop.py:96` | Evaluates, selects, and **applies** in one call. Used by the benchmark harness. |
| `run_first_pass` | `orchestration/loop.py:162` | Evaluates and selects, writes the proposal, **does not apply**. |
| `apply_recovery` | `orchestration/loop.py:199` | Applies a proposed action to an existing trace, writing a **new child trace**. |

`run_first_pass` + `apply_recovery` is the confirm-recovery path the explorer
uses by default. Both paths converge on the same `_apply_action`
(`orchestration/loop.py:295`), so the repair logic is shared.

`run_with_recovery` applies `regenerate`, `rewrite`, and `expand` while budget
remains. An `accept` selection is written without a second pass. First-pass
`abstain` is recorded without applying the canned phrase; abstain after a
failed attempt is applied as a stop.

## Inputs

`_first_pass_state` (`orchestration/loop.py:261`) calls `execute_query` in
`pipeline/baseline.py`, which produces a `QueryState`:

- `query` — the original question, always what the judge and generator see
- `retrieval` — a `RetrievalResult` of `ScoredChunk`s from the in-memory index
- `generation` — a `GenerationResult`
- `runtime_evaluation` — judge flags, or `None` when no judge was supplied
- `diagnosis` — a `Diagnosis`, or `None`

`execute_query` takes a separate `search_query` argument. That is how query
rewrite retrieves with different text while still judging against the original
question.

`_query_state_from_trace` (`orchestration/loop.py`) rebuilds a `QueryState`
from a stored trace dict. **This function defines the real integration
contract**: a chunk needs only `chunk_id`, `doc_id`, `title`, `text`, `score`,
and optionally `page`. Anything that can produce that shape can drive the
engine.

## Evaluation

`LLMJudge.judge` (`evaluation/llm_judge.py:77`) makes **one** chat completion
with `response_format={"type": "json_object"}` and `temperature=0`, returning:

- `evidence_sufficient` (bool) — judged from question and evidence alone
- `answer_supported` (bool or null) — null when no answer was generated
- two short rationales

The prompt forbids outside knowledge and states that a fluent answer is not
support. Gold answers are never included.

A deterministic post-check then runs: `constrain_support_to_evidence`
(`evaluation/llm_judge.py:145`) extracts checkable facts from the answer —
clock times, emails, ordinals, spec letters like `AMS 4911N`, and numbers of
three or more digits — and forces `answer_supported=False` when any of them is
absent from the retrieved chunk text. Citations are stripped first so chunk ids
are not mistaken for facts, and explicit abstentions are exempt.

The judge is swappable behind the `GroundingJudge` protocol
(`evaluation/judge.py`); `ScriptedJudge` is the test implementation and never
calls a model.

## Failure detection

There is exactly one detector: the two judge booleans. A run is a candidate for
repair only when `evidence_sufficient` is false or `answer_supported` is false.
No retrieval score, no confidence margin, and no other signal participates.

## Diagnosis

`diagnose_runtime` (`diagnosis/diagnose.py:31`) handles the first pass:

| Judge state | Failure class |
|---|---|
| sufficient, supported | `None` — no failure |
| sufficient, **not** supported | `unsupported_generation` |
| **not** sufficient | `None` — deliberately deferred |
| no answer generated | `None` |

The deferral is intentional per ADR 007: `retrieval_miss` and
`evidence_insufficiency` are indistinguishable before a rewrite, so the first
pass refuses to guess.

`diagnose_after_rewrite` (`diagnosis/diagnose.py:41`) resolves the split once a
second retrieve exists: evidence that became sufficient is `retrieval_miss`,
evidence still insufficient is `evidence_insufficiency`.

`_checked` rejects any class outside the three in `V1_FAILURE_CLASSES`.

## Healing

`select_recovery` (`recovery/policy.py:16`) maps diagnosis to action. It is a
four-branch chain, evaluated in order:

1. `unsupported_generation` → `regenerate`
2. `evidence_insufficiency` → `abstain`
3. evidence not sufficient (no class yet) → `rewrite`
4. judge accepted but retrieval looks weak → `expand`
5. otherwise → `accept`

`select_next_recovery` runs after an applied action that did not improve the
first-pass flags. It never repeats an action already used. Rewrite or
regenerate that still fails prefers `expand`; expand that still fails
regenerates if the new evidence is sufficient but unsupported, otherwise
abstains.

What each action changes:

| Action | Retrieval | Answer |
|---|---|---|
| `accept` | unchanged | unchanged |
| `regenerate` | **unchanged** | new answer from the same chunks, stricter prompt |
| `rewrite` | **new query, new retrieve** | regenerated from the new chunks *if* they are sufficient |
| `expand` | **same query, higher `top_k`** | regenerated from the wider retrieve |
| `abstain` | unchanged | replaced with a fixed string |

`ConstrainedRegenerator` (`recovery/regenerate.py`) is instructed to drop every
claim absent from the evidence and to cite chunk ids.

`LLMQueryRewriter` (`recovery/rewrite.py`) produces a search query only. Two
guards apply: the prompt forbids expanding abbreviations or introducing facts
not in the question, and `guard_rewritten_query` discards any rewrite that adds
`university`, `college`, or `institute` when the original question did not
contain them (issue #52).

The rewrite branch of `_apply_action` runs a **probe**: `execute_query` with
`generate=False` using the rewritten text. If the probe's evidence is
sufficient, a fresh answer is generated from the new chunks. If not, the answer
becomes the canned abstention and the class is `evidence_insufficiency`.

Nothing in the corpus, the index, the prompts, or any configuration is modified
by healing. Only the answer and the retrieved chunk set for that single run
change.

## Validation

`verify_runtime` (`verification/runtime.py:19`) compares the before and after
`RuntimeEvaluation` and returns one of four outcomes:

| Condition | Outcome |
|---|---|
| sufficiency false → true | `improved` |
| sufficiency true → false | `degraded` |
| support false/null → true | `improved` |
| support true → false/null | `degraded` |
| still unsupported or insufficient | `still_failing` |
| no flag changed | `unchanged` |

Verification reads **only** those two booleans, and both sides come from the
same judge. Gold labels are never consulted at runtime; they are used offline
in `experiments/` to score whether the verdict itself was right (ADR 002).

## Persistence

One JSON file per run, written by `write_run` in `pipeline/baseline.py` through
`tracing/tracer.py`, which **refuses to overwrite an existing file**.

Fields relevant to self-healing on `TraceRecord` (`types.py`):
`runtime_evaluation`, `diagnosis`, `recovery`, `verification`,
`previous_answer`, `rewritten_query`, `previous_retrieved_chunks`,
`recovery_status`, `parent_run_id`, `latency_ms`, `probe_evaluation`,
`recovery_attempts`, `first_pass_evaluation`.

`probe_evaluation` holds the rewrite probe's judgment of the new evidence,
made with no answer in hand. It is a different question from
`runtime_evaluation` and is stored separately rather than folded into it.

`recovery_status` is `proposed` or `applied`. A confirmed recovery writes a
**second** file carrying `parent_run_id`, so the first pass stays on disk
unmodified. Traces live under `experiments/output/<corpus-id>/`, which is
gitignored.

There is no database. `api/store.py` scans the directory with `rglob` on each
request.

## Human interaction

In confirm mode the operator sees the diagnosis and the proposed action, then
chooses. `apply_recovery` accepts an `action` override, and
`_decision_to_apply` records `source` as `policy` when the operator agreed with
the proposal or `operator` when they overrode it.

Guards refuse to apply twice, to recover a child run, or to recover a run whose
status is not `proposed`.

## UI

The explorer (`web/`) renders the stored trace. It owns no recovery logic.

- `tracing/steps.py` maps the flat trace into an ordered waterfall
- `web/app.js` `renderRecoverBar` shows the proposal and the action buttons
- Before/After answers, the rewritten query, and first-pass versus post-recovery
  chunks are shown when the trace carries them
- The eval strip counts actions and verification outcomes for the active corpus

## API routes

| Route | Purpose |
|---|---|
| `POST /api/runs` | Run a query. `mode` is `loop`, `loop_confirm`, `baseline`, or `retrieve_only`. Defaults to `loop_confirm`. |
| `POST /api/runs/{run_id}/recover` | Apply the proposed action, optionally overridden. |
| `GET /api/traces` | Run list with parent/child links. |
| `GET /api/traces/{run_id}` | One trace plus derived steps. |
| `DELETE /api/traces/{run_id}` | Delete a run; a parent also deletes its child. |
| `GET /api/eval` | Counts for the active corpus. |
| `POST /api/v1/evaluations` | Judge an externally produced query/answer/contexts. Requires a project API key. Does **not** apply rewrite or expand. |
| `GET /api/v1/evaluations/{run_id}` | Read that evaluation. Scoped to the key's project. |
| `POST /api/projects/{id}/keys` | Create a project key. Plaintext is returned once. |

Dashboard `/api/*` stays unauthenticated for local use. `/api/v1/*` rejects missing or revoked keys with 401. Keys live in `experiments/projects/<id>/keys.json` as SHA-256 hashes, not in `project.json` or `agent_config`.

`loop` and `loop_confirm` require `OPENAI_API_KEY`; `retrieve_only` does not. The v1 adapter uses `LLMJudge` unless a test injects `app.state.grounding_judge`.

## Tests

No test calls a live model. Coverage lives mainly in `tests/test_recovery.py`,
`tests/test_diagnosis.py`, `tests/test_runtime_eval.py`, `tests/test_rewrite.py`,
`tests/test_steps.py`, `tests/test_api.py`, `tests/test_v1_evaluations.py`, and
`tests/test_isolation.py`, using `FakeEmbedder` and `ScriptedJudge`.

## Actual weaknesses

These are observed, not hypothetical. Evidence is the committed Harbor snapshot
`experiments/results/20260910T070623/` and the code paths above.

**1. Repair never ran on an answerable question.** Across 32 questions the
actions were 27 `accept`, 5 `rewrite`, 0 `regenerate`. All five rewrites fired
on questions with `answerable: false`, where the correct output is an
abstention. The repair path has never been exercised on a case where repair was
possible. (Issues #64, #69.)

**2. `regenerate` has never executed in a benchmark.** The action requires
`evidence_sufficient=True` **and** `answer_supported=False` simultaneously,
which did not occur. (Issue #64.)

**3. A failed rewrite could make the answer worse.** `_apply_action` replaced the
generated answer with the canned abstention. In `gold-027` an answer that
explained the dates were not listed became `"I do not know based on the
retrieved documents."` **Fixed in #65:** a first-pass answer the judge called
supported is now kept, and `recovery.outcome_note` records the choice.

**4. Attribution and verification could contradict each other.** Attribution
hardcoded `retrieval_miss` from the probe judgment (evidence only) while
verification compared against a later judge call made with the answer. Two runs
in the snapshot are attributed `retrieval_miss` — meaning the rewrite fixed
retrieval — while verification reports `still_failing`. **Fixed in #66:**
attribution is derived from the same evaluation verification uses, the probe
judgment is persisted as `probe_evaluation`, and a disagreement between the two
calls is recorded in `recovery.outcome_note`. Traces written before that change
still carry the contradiction.

**5. Retry is budgeted, not unbounded.** `max_recoveries` defaults to 1 in
existing Harbor/DKU configs. Auto-loop in the playground and the v3 expand
configs use 2. The orchestrator stops on `improved` or when the budget is
spent. (Issue #67.)

**6. Expand can change the evidence without a rewriter.** `regenerate` still
reuses the same chunks. `expand` widens `top_k` on the current search text.
`decompose` and `rerank` from the V1 spec were never built. (Issue #68.)

**7. Detection has a single point of failure.** Everything downstream depends on
one judge call. A lenient judge silently disables the entire system, and the
corpus is easy enough that `retrieval_hit_rate` was 1.0 in both benchmark
conditions. (Issue #64.)

**8. Verification is self-referential and coarse.** The same judge produces both
sides of the comparison, and only a boolean flip registers as a change, so a
genuinely better answer with unchanged flags reads as `unchanged`.

**9. Recovery can increase fabrication.** In `seed-009`, an unanswerable
question, the post-rewrite answer added a more specific invented figure than the
first-pass answer had.
