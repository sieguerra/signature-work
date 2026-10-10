# Reliability trace schema

`write_run` stamps `trace_schema_version: 2`. A missing or null version is a legacy file. Legacy files are not rewritten.

The runtime is unchanged. The trace records what the loop already did.

## What one file is

Top-level `query`, `retrieved_chunks`, `answer`, `runtime_evaluation`, `diagnosis`, `verification`, and `latency_ms` are the **final** state. Readers that only need the outcome use those fields.

`initial` is the **first pass**, and only when a later attempt replaced it. When `initial` is null, the top-level fields are the only state (retrieve-only, baseline, accept, or a confirm proposal that was not applied).

`recovery_attempts` is the ordered list of recovery attempts. Index `0` is the first attempt. Top-level `verification` compares the first pass with the final state. Each attempt's `verification` compares the state **before that attempt** with the state **after it**. Those are different facts.

`run_mode` is one of `retrieve_only`, `baseline`, `loop_confirm`, `loop` when the caller is one of those paths. Null means the writer was not one of those paths (external evaluation). Do not infer a mode from the shape of a version-2 file that left it null.

## Attempt fields

| Field | Meaning |
| --- | --- |
| `answer_relation` | `generated` (this attempt produced the answer from its evidence), `kept_previous` (a new retrieve happened but the previous answer was kept), `abstained`, `unchanged` (the action did not replace the answer), `none` (no answer was produced) |
| `evidence_relation` | `replaced` (new retrieve, full `retrieved_chunks` stored), `widened` (higher `top_k`, full chunks stored), `unchanged` (no chunk copy; use the previous attempt, or `initial.retrieved_chunks`) |
| `evaluation_source` | `judge` (a judge call on this attempt's answer), `probe` (the rewrite's no-answer evidence judge), `carried` (no new judge call) |
| `probe_evaluation` | Present only on a rewrite that probed. Not the same object as `runtime_evaluation`. |
| `executed` | False when expand is already at the widest `top_k`, or regenerate/rewrite was skipped because generation is off. The attempt is still listed because the controller selected it. |
| `search_query` | The query sent to the index, when a retrieve happened. Omitted when it did not. |
| `source` | `policy` or `operator`. |
| `usage` | Present only when a usage capture was open. Omitted tokens are not the same as a false flag. Trace `usage` is the whole run. Attempt `usage` is only that attempt, so the two must not be added together. |

`answer_supported: null` means the judge did not check support. It is not false.

## Confirm mode

The parent file is the proposal. It has no `initial` and no attempts. The child file sets `parent_run_id` to the parent's `run_id`, copies the parent into `initial`, and stores the one applied attempt. That parent id is the logical run id. A separate `logical_run_id` field is not written, so it cannot drift from `parent_run_id`.

## What the loop actually does

A rewrite whose probe calls the new evidence sufficient generates a new answer, then stops if verification says the run improved. A rewrite whose probe stays insufficient does **not** generate an intermediate answer: it keeps a supported first answer or abstains. Expand is what generates the next answer in the rewrite-then-expand path. The trace records that. It does not invent an answer the model did not produce.

An exception before `write_run` returns leaves no file. The runtime does not persist a half-finished attempt. There is no `started` / `failed` lifecycle because those states are not recoverable after the process throws.

Terminal abstention runs after the recovery budget and makes no judge call. Its attempt uses `evaluation_source: carried` and sets `answer_supported` to null.

## Legacy reads

`first_pass_diagnosis` returns `initial.diagnosis` when present. On a legacy recovered trace it returns nothing, because the top-level diagnosis may be the post-recovery class. On a legacy file with no attempts, the top-level diagnosis is the first pass.

`retrieval_signal` on the trace stays the first-pass signal. Later attempts do not replace it.

## Not in the trace

Gold answers, answerability, gold F1, and benchmark success labels are not written. `question_id` is only the id the experiment runner already passed in. Provider config records `api_key_present`, never the key.

Queries, passage text, and answers are retained. That is required for this local research system. Those fields are the sensitive content if this trace is later stored for a customer. Authentication secrets are not. The provider block stores `api_key_present` and never the key, a bearer token, or an `Authorization` header.

## Usage accounting

Trace `usage` is the whole run. Each attempt's `usage` is only that attempt. Consumers must not add them together.

`usage` is omitted when no capture was open, and when a capture was open but no chat or embedding call happened. A call whose provider response omitted `usage` keeps `chat_calls` or `embedding_calls` and sets the token fields to null with `tokens_observed: false`. A numeric zero is written only when a usage object was seen. Missing tokens are not a measured zero.

Confirm mode: the parent file's usage is the first pass. The child file's usage is the applied attempt's capture, which is the child's whole run. The child's attempt usage is that same attempt. Adding parent usage to child usage describes the logical run. Adding the child's top-level usage to its attempt usage double-counts the child.

## Writes

`write_trace` writes a partial file, fsyncs it, then links it to `{run_id}.json`. The link fails if that name exists, so a finished trace is not overwritten and a crash during the write does not leave a truncated `{run_id}.json`. A leftover `.{run_id}.json.partial` is not a `*.json` file, so loaders do not treat it as a completed run. An exception before `write_run` still leaves no trace file. There is no crash journal.

## Schema versions this code does not know

`trace_schema_version: 999` (any integer above 2) is not read as version 2. `initial`, attempt `answer_relation`, and attempt evidence are not interpreted. The file can still be listed from its top-level `run_id`, `query`, and `answer`. The Test Console marks it unsupported and does not build a recovery path from it. There is no migration.

## What a verifier must not assume

`executed: false` means the controller selected the action and the operation did not run. The attempt stays in order. It is not an applied recovery. Overview's verified-improved rate ignores it. A top-level `verification` compares the first pass with the final state; it does not by itself prove that an attempt executed. When nothing executed, that comparison can be `unchanged` because the state did not change.

`evaluation_source: carried` means no new judge call. `answer_supported: null` on that evaluation is still null. A carried abstention is not a fresh judgment that the answer is unsupported.

`probe_evaluation` judged the rewritten evidence before an answer existed. It is not an evaluation of the attempt's answer.

`kept_previous` means the answer text was not generated from the attempt's new evidence. `abstained` is the canonical abstention string, not a generated answer.
