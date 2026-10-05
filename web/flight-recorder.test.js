const assert = require("node:assert/strict");
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

test("mode notes do not promise unlimited healing", () => {
  assert.match(modeNote("loop"), /configured recovery limit/);
  assert.match(modeNote("loop_confirm"), /until you confirm/);
  assert.match(modeNote("baseline"), /No recovery/);
  assert.match(modeNote("retrieve_only"), /without generating/);
});
