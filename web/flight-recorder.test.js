const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { buildFlight, modeNote } = require("./flight-recorder.js");

function chunk(id, score) {
  return { chunk_id: id, title: id, score, text: `text ${id}` };
}

test("retrieve only is query then retrieve, with no generate or judge", () => {
  const flight = buildFlight([
    {
      run_id: "r",
      query: "When does it open?",
      model: "none",
      answer: "",
      top_k: 4,
      retrieved_chunks: [chunk("a", 0.4)],
    },
  ]);
  assert.equal(flight.status, "retrieve_only");
  assert.deepEqual(flight.phases.map((phase) => phase.key), ["initial"]);
  assert.deepEqual(
    flight.phases[0].steps.map((step) => step.kind),
    ["query", "retrieve", "diagnose"]
  );
  assert.equal(flight.after, null);
  assert.equal(flight.verification, null);
});

test("baseline retrieves and generates without a reliability loop", () => {
  const flight = buildFlight([
    {
      run_id: "b",
      query: "Hours?",
      model: "gpt-4o-mini",
      answer: "Until 10.",
      top_k: 4,
      retrieved_chunks: [chunk("a", 0.5)],
    },
  ]);
  assert.equal(flight.status, "baseline");
  assert.deepEqual(
    flight.phases[0].steps.map((step) => step.kind),
    ["query", "retrieve", "generate", "diagnose"]
  );
  assert.equal(flight.attemptCount, 0);
});

test("an accepted judged run needs no recovery", () => {
  const flight = buildFlight([
    {
      run_id: "ok",
      query: "Hours?",
      model: "gpt-4o-mini",
      answer: "Until 10.",
      runtime_evaluation: { evidence_sufficient: true, answer_supported: true },
      recovery: { action: "accept", source: "policy" },
      recovery_status: "applied",
      retrieved_chunks: [chunk("a", 0.8)],
    },
  ]);
  assert.equal(flight.status, "no_recovery_needed");
  assert.equal(flight.attemptCount, 0);
  assert.equal(flight.verification, null);
  assert.equal(flight.before.evaluation.answer_supported, true);
});

test("a proposed recovery is not shown as applied", () => {
  const flight = buildFlight([
    {
      run_id: "parent",
      query: "Hours?",
      model: "gpt-4o-mini",
      answer: "On the moon.",
      runtime_evaluation: { evidence_sufficient: false, answer_supported: null },
      diagnosis: { failure_class: null, rationale: "not split on first pass" },
      recovery: { action: "expand", reason: "weak scores", trigger: "retrieval_signal", source: "policy" },
      recovery_status: "proposed",
      retrieval_signal: { weak_top: true, ambiguous_top: false, reason: "Top score is low.", top_score: 0.04 },
      retrieved_chunks: [chunk("a", 0.04)],
    },
  ]);
  assert.equal(flight.status, "recovery_proposed");
  assert.equal(flight.pending.action, "expand");
  assert.equal(flight.pending.source, "Automatic policy");
  assert.equal(flight.attemptCount, 0);
  assert.equal(flight.after, null);
  assert.equal(flight.before.evaluation.answer_supported, null);
  assert.equal(flight.before.diagnosis, "Diagnosis not yet attributed.");
  assert.equal(flight.retrievalWarning.weakTop, true);
  assert.equal(flight.retrievalWarning.triggeredRecovery, true);
});

test("confirm parent and child are one flight", () => {
  const flight = buildFlight([
    {
      run_id: "parent",
      query: "Hours?",
      model: "gpt-4o-mini",
      answer: "On the moon.",
      runtime_evaluation: { evidence_sufficient: true, answer_supported: false },
      diagnosis: { failure_class: "unsupported_generation" },
      recovery: { action: "regenerate", source: "policy", trigger: "judge" },
      recovery_status: "proposed",
      retrieved_chunks: [chunk("a", 0.7)],
      latency_ms: 100,
    },
    {
      run_id: "child",
      parent_run_id: "parent",
      query: "Hours?",
      model: "gpt-4o-mini",
      answer: "Until 10.",
      previous_answer: "On the moon.",
      runtime_evaluation: { evidence_sufficient: true, answer_supported: true },
      recovery: { action: "regenerate", source: "operator", trigger: "judge" },
      recovery_status: "applied",
      verification: { outcome: "improved" },
      retrieved_chunks: [chunk("a", 0.7)],
      latency_ms: 40,
    },
  ]);
  assert.equal(flight.joined, true);
  assert.deepEqual(flight.traceIds, ["parent", "child"]);
  assert.equal(flight.pending, null);
  assert.equal(flight.verification, "improved");
  assert.equal(flight.status, "improved");
  assert.equal(flight.before.answer, "On the moon.");
  assert.equal(flight.after.answer, "Until 10.");
  assert.equal(flight.attempts[0].action, "regenerate");
  assert.equal(flight.attempts[0].source, "Operator-selected");
  assert.equal(flight.evidence.added.length, 0);
  assert.equal(flight.evidence.removed.length, 0);
  assert.equal(flight.latencyMs, 140);
  assert.ok(flight.phases.some((phase) => phase.action === "regenerate"));
});

test("rewrite then expand stays two attempts", () => {
  const flight = buildFlight([
    {
      run_id: "auto",
      query: "Seats?",
      model: "gpt-4o-mini",
      answer: "400 seats.",
      previous_answer: "I do not know based on the retrieved documents.",
      first_pass_evaluation: { evidence_sufficient: false, answer_supported: null },
      runtime_evaluation: { evidence_sufficient: true, answer_supported: true },
      previous_retrieved_chunks: [chunk("old", 0.2)],
      retrieved_chunks: [chunk("old", 0.2), chunk("new", 0.6)],
      rewritten_query: "how many library seats",
      recovery: { action: "expand", source: "policy", trigger: "judge" },
      recovery_status: "applied",
      recovery_attempts: [
        {
          action: "rewrite",
          trigger: "judge",
          source: "policy",
          attributed_class: "retrieval_miss",
          rewritten_query: "how many library seats",
          verification: { outcome: "unchanged" },
        },
        {
          action: "expand",
          trigger: "judge",
          source: "policy",
          top_k: 8,
          verification: { outcome: "improved" },
        },
      ],
      verification: { outcome: "improved" },
      top_k: 8,
    },
  ]);
  assert.deepEqual(
    flight.attempts.map((item) => item.action),
    ["rewrite", "expand"]
  );
  assert.equal(flight.attempts[0].verification, "unchanged");
  assert.equal(flight.attempts[0].source, "Automatic policy");
  assert.equal(flight.verification, "improved");
  assert.equal(flight.before.evaluation.evidence_sufficient, false);
  assert.equal(flight.before.evaluation.answer_supported, null);
  assert.equal(flight.after.evaluation.answer_supported, true);
  assert.equal(flight.after.rewrittenQuery, "how many library seats");
  assert.equal(flight.evidence.added[0].chunk_id, "new");
  assert.equal(flight.evidence.retained[0].chunk_id, "old");
  assert.ok(flight.phases.filter((phase) => phase.key.startsWith("recovery-")).length === 2);
});

test("historical applied rewrite without recovery_attempts still renders", () => {
  const flight = buildFlight([
    {
      run_id: "old",
      query: "Seats?",
      model: "gpt-4o-mini",
      answer: "Still unknown.",
      previous_answer: "Guess.",
      recovery: { action: "rewrite", source: "policy", attributed_class: "evidence_insufficiency" },
      recovery_status: "applied",
      verification: { outcome: "still_failing" },
      rewritten_query: "seat count",
      retrieved_chunks: [chunk("a", 0.1)],
      previous_retrieved_chunks: [chunk("b", 0.1)],
    },
  ]);
  assert.equal(flight.attempts.length, 1);
  assert.equal(flight.attempts[0].historical, true);
  assert.equal(flight.attempts[0].action, "rewrite");
  assert.equal(flight.verification, "still_failing");
  assert.equal(flight.status, "still_failing");
  assert.equal(flight.evidence.removed[0].chunk_id, "b");
  assert.equal(flight.evidence.added[0].chunk_id, "a");
});

test("unchanged and degraded stay distinct from improved", () => {
  const unchanged = buildFlight([
    {
      run_id: "u",
      query: "Q",
      model: "gpt-4o-mini",
      answer: "Same",
      previous_answer: "Same",
      recovery: { action: "regenerate", source: "policy" },
      recovery_status: "applied",
      verification: { outcome: "unchanged" },
      first_pass_evaluation: { evidence_sufficient: false, answer_supported: false },
      runtime_evaluation: { evidence_sufficient: false, answer_supported: false },
      retrieved_chunks: [],
    },
  ]);
  const degraded = buildFlight([
    {
      run_id: "d",
      query: "Q",
      model: "gpt-4o-mini",
      answer: "Worse",
      previous_answer: "Better",
      recovery: { action: "expand", source: "policy" },
      recovery_status: "applied",
      verification: { outcome: "degraded" },
      first_pass_evaluation: { evidence_sufficient: true, answer_supported: true },
      runtime_evaluation: { evidence_sufficient: false, answer_supported: false },
      retrieved_chunks: [chunk("a", 0.2)],
      previous_retrieved_chunks: [chunk("a", 0.4)],
    },
  ]);
  assert.equal(unchanged.status, "unchanged");
  assert.equal(degraded.status, "degraded");
  assert.equal(degraded.before.evaluation.evidence_sufficient, true);
  assert.equal(degraded.after.evaluation.evidence_sufficient, false);
});

test("abstention is labeled and not dropped", () => {
  const flight = buildFlight([
    {
      run_id: "abs",
      query: "Q",
      model: "abstain",
      answer: "I do not know based on the retrieved documents.",
      previous_answer: "A guess.",
      recovery: { action: "abstain", source: "policy" },
      recovery_status: "applied",
      verification: { outcome: "still_failing" },
      first_pass_evaluation: { evidence_sufficient: false, answer_supported: null },
      runtime_evaluation: { evidence_sufficient: false, answer_supported: null },
      retrieved_chunks: [chunk("a", 0.1)],
    },
  ]);
  assert.equal(flight.after.abstained, true);
  assert.equal(flight.verification, "still_failing");
  assert.equal(flight.attempts[0].action, "abstain");
  assert.ok(flight.phases.some((phase) => phase.action === "abstain"));
});

test("explicit mode and attempt answers replace inference", () => {
  const flight = buildFlight([
    {
      run_id: "v2",
      run_mode: "loop",
      query: "Hours?",
      model: "gpt-4o-mini",
      answer: "answer C",
      trace_schema_version: 2,
      initial: {
        query: "Hours?",
        answer: "answer A",
        retrieved_chunks: [chunk("old", 0.2)],
        runtime_evaluation: { evidence_sufficient: false, answer_supported: null },
        diagnosis: {
          failure_class: null,
          rationale: "Evidence was judged insufficient. retrieval_miss vs evidence_insufficiency is not diagnosed on the first pass.",
        },
      },
      first_pass_evaluation: { evidence_sufficient: false, answer_supported: null },
      runtime_evaluation: { evidence_sufficient: true, answer_supported: true },
      retrieved_chunks: [chunk("new", 0.8)],
      recovery: { action: "expand", source: "policy" },
      recovery_status: "applied",
      verification: { outcome: "improved" },
      recovery_attempts: [
        {
          index: 0,
          action: "rewrite",
          source: "policy",
          answer: "answer B",
          answer_relation: "generated",
          evidence_relation: "replaced",
          runtime_evaluation: { evidence_sufficient: false, answer_supported: false },
          evaluation_source: "judge",
          verification: { outcome: "still_failing" },
          rewritten_query: "library hours",
          executed: true,
        },
        {
          index: 1,
          action: "expand",
          source: "policy",
          answer: "answer C",
          answer_relation: "generated",
          evidence_relation: "widened",
          runtime_evaluation: { evidence_sufficient: true, answer_supported: true },
          evaluation_source: "judge",
          verification: { outcome: "improved" },
          top_k: 12,
          executed: true,
        },
      ],
    },
  ]);
  assert.equal(flight.runMode, "loop");
  assert.equal(flight.before.answer, "answer A");
  assert.equal(flight.before.chunks[0].chunk_id, "old");
  assert.match(flight.before.diagnosis, /not diagnosed on the first pass/);
  assert.equal(flight.attempts[0].answer, "answer B");
  assert.equal(flight.attempts[0].verification, "still_failing");
  assert.equal(flight.attempts[1].answer, "answer C");
  assert.equal(flight.attempts[1].verification, "improved");
  const rewrite = flight.phases.find((phase) => phase.action === "rewrite");
  assert.ok(rewrite.steps.some((step) => step.detail.includes("answer B")));
  assert.ok(rewrite.steps.some((step) => step.outcome === "still_failing"));
});

test("a kept answer is not shown as generated from the new evidence", () => {
  const flight = buildFlight([
    {
      run_id: "kept",
      run_mode: "loop",
      query: "Hours?",
      model: "gpt-4o-mini",
      answer: "Saturday hours.",
      initial: {
        answer: "Saturday hours.",
        retrieved_chunks: [chunk("old", 0.4)],
        diagnosis: { failure_class: null, rationale: "thin" },
      },
      recovery: { action: "rewrite", source: "policy" },
      recovery_status: "applied",
      verification: { outcome: "still_failing" },
      retrieved_chunks: [chunk("new", 0.2)],
      recovery_attempts: [
        {
          action: "rewrite",
          source: "policy",
          answer: "Saturday hours.",
          answer_relation: "kept_previous",
          evidence_relation: "replaced",
          verification: { outcome: "still_failing" },
          executed: true,
        },
      ],
    },
  ]);
  const rewrite = flight.phases.find((phase) => phase.action === "rewrite");
  assert.ok(rewrite.steps.some((step) => step.title === "Kept previous answer"));
  assert.equal(rewrite.steps.some((step) => step.title === "Answer"), false);
});

test("mode notes do not promise unlimited healing", () => {
  assert.match(modeNote("loop"), /configured recovery limit/);
  assert.match(modeNote("loop_confirm"), /until you confirm/);
  assert.match(modeNote("baseline"), /No recovery/);
  assert.match(modeNote("retrieve_only"), /without generating/);
});

test("an unexecuted attempt is not a successful recovery", () => {
  const flight = buildFlight([
    {
      run_id: "r",
      trace_schema_version: 2,
      run_mode: "loop",
      query: "When is the library open?",
      answer: "Saturday hours.",
      model: "scripted",
      runtime_evaluation: { evidence_sufficient: true, answer_supported: true },
      initial: {
        answer: "Saturday hours.",
        retrieved_chunks: [chunk("a", 0.01)],
        diagnosis: { failure_class: null, rationale: "weak retrieval" },
        runtime_evaluation: { evidence_sufficient: true, answer_supported: true },
      },
      verification: { outcome: "unchanged" },
      recovery_attempts: [
        {
          action: "expand",
          executed: false,
          answer: "Saturday hours.",
          answer_relation: "unchanged",
          evidence_relation: "unchanged",
          evaluation_source: "carried",
        },
      ],
    },
  ]);
  assert.equal(flight.status, "not_executed");
  assert.equal(flight.attemptCount, 1);
  assert.equal(flight.attempts[0].executed, false);
  assert.equal(flight.after, null);
  assert.ok(flight.phases.some((phase) => phase.steps.some((step) => step.title === "Not executed")));
});

test("a future schema is not interpreted as version 2", () => {
  const flight = buildFlight([
    {
      run_id: "future",
      trace_schema_version: 999,
      query: "When is the library open?",
      answer: "Saturday hours.",
      initial: { answer: "do not use", diagnosis: { failure_class: "invented_class" } },
      recovery_attempts: [{ action: "rewrite", answer_relation: "generated", executed: true }],
    },
  ]);
  assert.equal(flight.unsupportedSchema, true);
  assert.equal(flight.status, "unsupported_schema");
  assert.equal(flight.attemptCount, 0);
  assert.equal(flight.before.diagnosis, "Unsupported trace schema.");
});

test("a safe stop shows the recovery decision without changing a legacy attempt", () => {
  const flight = buildFlight([
    {
      run_id: "stop",
      query: "What is the fee?",
      model: "gpt-4o-mini",
      answer: "I do not know based on the retrieved documents.",
      top_k: 12,
      retrieved_chunks: [chunk("a", 0.5)],
      runtime_evaluation: { evidence_sufficient: false, answer_supported: null },
      recovery_attempts: [
        {
          action: "expand",
          reason: "expand first",
          executed: true,
          top_k: 12,
          answer_relation: "generated",
          answer: "maybe",
        },
        {
          action: "abstain",
          reason: "the retrieved sources say the requested information is not provided",
          executed: true,
          answer_relation: "abstained",
          answer: "I do not know based on the retrieved documents.",
          parameters: { stop_reason: "the retrieved sources say the requested information is not provided" },
        },
      ],
    },
  ]);
  const titles = flight.phases.map((phase) => phase.title);
  assert.ok(titles.includes("Recovery · Safe stop"));
  const stop = flight.phases.find((phase) => phase.title === "Recovery · Safe stop");
  assert.ok(stop.steps.some((step) => step.title === "Recovery decision"));
});

test("legacy corpus files still build a flight", () => {
  const corpus = JSON.parse(
    fs.readFileSync(path.join(__dirname, "../tests/fixtures/traces/legacy_corpus.json"), "utf8")
  );
  const byName = Object.fromEntries(corpus.map((item) => [item.name, item.trace]));
  const parent = buildFlight([byName.confirm_parent, byName.confirm_child]);
  assert.equal(parent.joined, true);
  assert.equal(parent.attempts[0].action, "regenerate");
  assert.equal(parent.attempts[0].sourceRaw, "operator");
  const multi = buildFlight([byName.multi_attempt]);
  assert.deepEqual(multi.attempts.map((item) => item.action), ["rewrite", "expand"]);
  const nullSupport = buildFlight([byName.null_answer_supported]);
  assert.equal(nullSupport.before.evaluation.answer_supported, null);
  const abstain = buildFlight([byName.abstain]);
  assert.equal(abstain.after.abstained, true);
  for (const item of corpus) {
    assert.ok(buildFlight([item.trace]), item.name);
  }
});

test("a gap-aware stop shows the decision signals and is not an improved answer", () => {
  const flight = buildFlight([
    {
      run_id: "gap",
      query: "What is the fee?",
      run_mode: "loop",
      recovery_policy: "v2c_gap_aware",
      model: "gpt-4o-mini",
      answer: "I do not know based on the retrieved documents. I couldn't find sufficient support for that answer in the available sources.",
      top_k: 12,
      retrieved_chunks: [chunk("a", 0.4)],
      runtime_evaluation: { evidence_sufficient: false, answer_supported: null },
      verification: { outcome: "still_failing" },
      recovery_attempts: [
        { action: "expand", executed: true, top_k: 12, answer_relation: "generated", answer: "maybe" },
        {
          action: "abstain",
          executed: true,
          answer_relation: "abstained",
          answer: "I do not know based on the retrieved documents. I couldn't find sufficient support.",
          parameters: {
            stop_reason: "the retrieved sources give more than one value and the question does not choose one",
            conflict_signal: true,
            neighbor_signal: false,
            decision_source: "deterministic_b1",
            recovery_opportunity: "CONFLICT",
          },
        },
      ],
    },
  ]);
  assert.equal(flight.status, "safe_stop");
  assert.equal(flight.recoveryPolicy, "v2c_gap_aware");
  assert.equal(flight.after.abstained, true);
  const stop = flight.phases.find((phase) => phase.title === "Recovery · Safe stop");
  assert.ok(stop.steps.some((step) => step.title === "Conflict signal"));
  assert.ok(stop.steps.some((step) => step.title === "Decision source" && step.detail === "deterministic_b1"));
  const page = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");
  assert.match(page, /Gap-aware \(Guarded\)/);
  assert.match(page, /value="v1" selected/);
  assert.match(page, /not the default/);
});

test("a conditional rewrite stays a rewrite and missing usage is not shown as zero", () => {
  const flight = buildFlight([
    {
      run_id: "rewrite",
      query: "bench rental",
      run_mode: "loop",
      recovery_policy: "v2c_gap_aware",
      model: "gpt-4o-mini",
      answer: "5 reed tokens",
      top_k: 12,
      retrieved_chunks: [chunk("bench", 0.8)],
      runtime_evaluation: { evidence_sufficient: false, answer_supported: false },
      verification: { outcome: "improved" },
      recovery_attempts: [
        {
          action: "expand",
          executed: true,
          top_k: 12,
          answer_relation: "generated",
          answer: "not printed",
        },
        {
          action: "rewrite",
          executed: true,
          answer_relation: "generated",
          answer: "5 reed tokens",
          parameters: {
            recovery_opportunity: "LIKELY_QUERY_MISMATCH",
            decision_source: "deterministic_b1",
          },
        },
      ],
    },
  ]);
  const titles = flight.phases.map((phase) => phase.title);
  assert.ok(titles.includes("Recovery · Rewrite"));
  assert.equal(titles.includes("Recovery · Safe stop"), false);
  assert.equal(flight.status, "improved");
  const source = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
  const match = source.match(/function formatUsage\(usage\) \{[\s\S]*?\n\}/);
  assert.ok(match);
  const formatUsage = new Function(`${match[0]}; return formatUsage;`)();
  assert.equal(formatUsage(null), "Token usage unavailable");
  assert.equal(
    formatUsage({ tokens_observed: false, prompt_tokens: null, completion_tokens: null }),
    "Token usage unavailable"
  );
  assert.equal(formatUsage({ tokens_observed: true, prompt_tokens: 12, completion_tokens: 4 }), "12 prompt tokens · 4 completion tokens");
});

test("a safe-stop phase reads as one status, with the verifier result labeled as recorded (#114)", () => {
  const { presentStep } = require("./flight-recorder.js");
  const flight = buildFlight([
    {
      run_id: "gap-stop",
      query: "What is the fee?",
      run_mode: "loop",
      recovery_policy: "v2c_gap_aware",
      answer: "I do not know based on the retrieved documents.",
      retrieved_chunks: [chunk("a", 0.4)],
      runtime_evaluation: { evidence_sufficient: false, answer_supported: null },
      verification: { outcome: "still_failing" },
      recovery_attempts: [
        { action: "expand", executed: true, top_k: 12, answer_relation: "generated", answer: "maybe" },
        {
          action: "abstain",
          executed: true,
          answer_relation: "abstained",
          answer: "I do not know based on the retrieved documents.",
          verification: { outcome: "still_failing" },
          parameters: {
            stop_reason: "the retrieved sources give more than one value and the question does not choose one",
            conflict_signal: true,
            decision_source: "deterministic_b1",
            recovery_opportunity: "CONFLICT",
          },
        },
      ],
    },
  ]);
  assert.equal(flight.status, "safe_stop");
  const stop = flight.phases.find((phase) => phase.title === "Recovery · Safe stop");
  const verify = stop.steps.find((step) => step.kind === "verify");
  assert.equal(verify.outcome, "still_failing");
  const titles = stop.steps.map((step) => presentStep(stop, step, flight.status).title);
  assert.ok(!titles.includes("Still failing"));
  assert.ok(!titles.includes("Safe abstention"));
  assert.ok(!titles.includes("Attempt check"));
  assert.ok(titles.includes("Verifier recorded"));
  assert.ok(titles.includes("Stopped answer"));
  assert.match(presentStep(stop, verify, flight.status).detail, /^Still failing\. Bounded recovery stopped/);
});

test("a still-failing run that is not a safe stop keeps its own words", () => {
  const { presentStep } = require("./flight-recorder.js");
  const phase = { key: "verification", title: "Runtime verification" };
  const step = { kind: "verify", title: "Still failing", detail: "x", outcome: "still_failing" };
  assert.equal(presentStep(phase, step, "still_failing").title, "Still failing");
});

test("loop map: a regenerate that improved reads flagged judge, done recover, passing verify", () => {
  const { loopStages } = require("./flight-recorder.js");
  const flight = buildFlight([
    {
      run_id: "loop-1",
      query: "When does the library open?",
      run_mode: "loop",
      answer: "Dude, 8 to 10.",
      retrieved_chunks: [chunk("a", 0.6)],
      first_pass_evaluation: { evidence_sufficient: true, answer_supported: false },
      runtime_evaluation: { evidence_sufficient: true, answer_supported: true },
      recovery: { action: "regenerate" },
      recovery_status: "applied",
      verification: { outcome: "improved" },
      recovery_attempts: [{ action: "regenerate", executed: true, answer_relation: "generated", answer: "8:00 to 22:00." }],
    },
  ]);
  const stages = Object.fromEntries(loopStages(flight).map((stage) => [stage.key, stage]));
  assert.deepEqual(Object.keys(stages), ["retrieve", "generate", "judge", "diagnose", "recover", "verify"]);
  assert.equal(stages.retrieve.state, "done");
  assert.equal(stages.retrieve.note, "1 passage");
  assert.equal(stages.judge.state, "flagged");
  assert.equal(stages.judge.note, "Answer unsupported");
  assert.equal(stages.recover.state, "done");
  assert.equal(stages.recover.note, "Regenerate");
  assert.equal(stages.verify.state, "pass");
});

test("loop map: retrieve only skips everything after retrieval", () => {
  const { loopStages } = require("./flight-recorder.js");
  const flight = buildFlight([{ run_id: "r", query: "q", run_mode: "retrieve_only", retrieved_chunks: [chunk("a", 0.5), chunk("b", 0.4)] }]);
  const states = loopStages(flight).map((stage) => `${stage.key}:${stage.state}`);
  assert.deepEqual(states, ["retrieve:done", "generate:skipped", "judge:skipped", "diagnose:skipped", "recover:skipped", "verify:skipped"]);
});

test("loop map with no run is the idle outline", () => {
  const { loopStages } = require("./flight-recorder.js");
  assert.ok(loopStages(null).every((stage) => stage.state === "idle"));
});

test("timeline places a confirmed child after its parent and nests recovery work", () => {
  const { timelineRows } = require("./flight-recorder.js");
  const flight = buildFlight([
    {
      run_id: "t1",
      query: "q",
      run_mode: "loop",
      latency_ms: 1000,
      retrieved_chunks: [chunk("a", 0.5)],
      first_pass_evaluation: { evidence_sufficient: true, answer_supported: false },
      runtime_evaluation: { evidence_sufficient: true, answer_supported: true },
      recovery: { action: "regenerate" },
      recovery_status: "applied",
      verification: { outcome: "improved" },
      recovery_attempts: [{ action: "regenerate", executed: true, answer_relation: "generated", answer: "a" }],
      stage_timings: [
        { stage: "retrieve", attempt: null, started_ms: 0, duration_ms: 100 },
        { stage: "generate", attempt: null, started_ms: 100, duration_ms: 400 },
        { stage: "judge", attempt: null, started_ms: 500, duration_ms: 200 },
        { stage: "recover", attempt: 0, action: "regenerate", started_ms: 700, duration_ms: 290 },
        { stage: "judge", attempt: 0, started_ms: 760, duration_ms: 200 },
        { stage: "verify", attempt: null, started_ms: 990, duration_ms: 1 },
      ],
    },
  ]);
  const line = timelineRows(flight);
  assert.equal(line.totalMs, 1000);
  assert.deepEqual(line.rows.map((row) => row.label), ["Retrieve", "Generate", "Judge", "Recover · Regenerate", "Judge", "Verify"]);
  assert.equal(line.rows[3].depth, 0);
  assert.equal(line.rows[4].depth, 1);
  assert.equal(line.rows[1].left, 10);
  assert.equal(line.rows[1].width, 40);
});

test("timeline is absent on runs recorded before stage timings existed", () => {
  const { timelineRows } = require("./flight-recorder.js");
  const flight = buildFlight([{ run_id: "old", query: "q", run_mode: "retrieve_only", retrieved_chunks: [chunk("a", 0.5)] }]);
  assert.equal(flight.timings, null);
  assert.equal(timelineRows(flight), null);
});

test("live stages follow streamed start and end events", () => {
  const { liveStages } = require("./flight-recorder.js");
  const events = [
    { type: "stage_start", stage: "retrieve" },
    { type: "stage_end", stage: "retrieve", duration_ms: 120 },
    { type: "stage_start", stage: "generate" },
  ];
  const stages = Object.fromEntries(liveStages(events).map((stage) => [stage.key, stage]));
  assert.equal(stages.retrieve.state, "done");
  assert.equal(stages.retrieve.ms, 120);
  assert.equal(stages.generate.state, "running");
  assert.equal(stages.judge.state, "idle");
  const later = liveStages([
    ...events,
    { type: "stage_end", stage: "generate", duration_ms: 300 },
    { type: "stage_start", stage: "recover", action: "regenerate" },
    { type: "stage_end", stage: "recover", action: "regenerate", duration_ms: 50, status: "error" },
  ]);
  const recover = later.find((stage) => stage.key === "recover");
  assert.equal(recover.state, "fail");
  assert.equal(recover.note, "Regenerate");
});
