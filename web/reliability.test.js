const assert = require("node:assert/strict");
const test = require("node:test");
const {
  filterLogicalRuns,
  recoveryCases,
  recoveryPath,
  labelInitialState,
  labelRecovery,
  labelSource,
  labelVerification,
  presentVerification,
  qualityStatus,
  formatWhen,
  parseRoute,
  routeHash,
} = require("./reliability.js");

function run(overrides) {
  return {
    logical_run_id: "r",
    query: "Library hours",
    judged: true,
    recovery: [],
    recovery_pending: null,
    recovery_required: false,
    verification: null,
    diagnoses: [],
    source: null,
    trigger: null,
    ...overrides,
  };
}

test("confirm parent and child stay one row and auto stays one row", () => {
  const rows = [
    run({ logical_run_id: "parent", query: "Hours?", recovery: ["rewrite"], recovery_required: true, verification: "improved" }),
    run({ logical_run_id: "auto", query: "Seats?", recovery: ["rewrite", "expand"], recovery_required: true, verification: "improved" }),
  ];
  assert.equal(filterLogicalRuns(rows, {}).length, 2);
  assert.equal(recoveryPath(rows[1]), "Rewrite → Expand");
});

test("verification filters stay distinct, including unchanged and needs investigation", () => {
  const rows = [
    run({ logical_run_id: "up", verification: "improved", recovery: ["rewrite"], recovery_required: true }),
    run({ logical_run_id: "same", verification: "unchanged", recovery: ["regenerate"], recovery_required: true }),
    run({ logical_run_id: "fail", verification: "still_failing", recovery: ["rewrite"], recovery_required: true }),
    run({ logical_run_id: "down", verification: "degraded", recovery: ["expand"], recovery_required: true }),
    run({ logical_run_id: "wait", recovery_pending: "expand", recovery_required: true }),
  ];
  assert.deepEqual(filterLogicalRuns(rows, { verification: "improved" }).map((item) => item.logical_run_id), ["up"]);
  assert.deepEqual(filterLogicalRuns(rows, { verification: "unchanged" }).map((item) => item.logical_run_id), ["same"]);
  assert.deepEqual(filterLogicalRuns(rows, { verification: "still_failing" }).map((item) => item.logical_run_id), ["fail"]);
  assert.deepEqual(filterLogicalRuns(rows, { verification: "degraded" }).map((item) => item.logical_run_id), ["down"]);
  assert.deepEqual(filterLogicalRuns(rows, { verification: "needs" }).map((item) => item.logical_run_id), ["fail", "down"]);
  assert.equal(labelVerification(rows[1]), "Unchanged");
  assert.equal(labelVerification(rows[4]), "Pending");
});

test("pending, no-recovery, and accept stay out of applied recovery", () => {
  const pending = run({ recovery_pending: "rewrite", recovery_required: true });
  const accepted = run({ judged: true });
  const applied = run({ recovery: ["expand"], recovery_required: true, verification: "improved" });
  assert.deepEqual(filterLogicalRuns([pending, accepted, applied], { recovery: "pending" }).map((item) => item.recovery_pending), ["rewrite"]);
  assert.deepEqual(filterLogicalRuns([pending, accepted, applied], { recovery: "none" }).map((item) => item.logical_run_id), ["r"]);
  assert.equal(labelRecovery(accepted), "No recovery");
  assert.equal(recoveryCases([pending, accepted, applied]).length, 2);
  assert.equal(filterLogicalRuns([accepted], { recovery: "applied" }).length, 0);
});

test("operator and automatic sources stay distinct", () => {
  assert.equal(labelSource("operator"), "Operator-selected");
  assert.equal(labelSource("policy"), "Automatic policy");
});

test("missing diagnosis is not inferred, and question search is literal", () => {
  const bare = run({ diagnoses: [], query: "Password reset" });
  const named = run({ logical_run_id: "miss", diagnoses: ["retrieval_miss"], query: "Seats" });
  assert.deepEqual(filterLogicalRuns([bare, named], { diagnosis: "unattributed" }).map((item) => item.query), ["Password reset"]);
  assert.deepEqual(filterLogicalRuns([bare, named], { query: "seat" }).map((item) => item.logical_run_id), ["miss"]);
  assert.equal(filterLogicalRuns([run({ judged: false, diagnoses: [] })], { diagnosis: "unattributed" }).length, 0);
});

test("historical single action and abstain still match action filters", () => {
  const historical = run({ recovery: ["rewrite"], recovery_required: true, verification: "still_failing" });
  const abstained = run({ recovery: ["abstain"], recovery_required: true, verification: "still_failing" });
  assert.equal(recoveryPath(historical), "Rewrite");
  assert.equal(filterLogicalRuns([historical, abstained], { action: "abstain" }).length, 1);
  assert.equal(labelRecovery(abstained), "Safe abstention");
});

test("an unexecuted selection is required and not applied", () => {
  const skipped = run({
    recovery: ["expand"],
    recovery_required: true,
    recovery_applied: false,
    verification: null,
  });
  assert.equal(labelRecovery(skipped), "Expand (not executed)");
  assert.equal(filterLogicalRuns([skipped], { recovery: "required" }).length, 1);
  assert.equal(filterLogicalRuns([skipped], { recovery: "applied" }).length, 0);
  assert.equal(filterLogicalRuns([skipped], { verification: "not_applicable" }).length, 1);
});

test("null answer support stays evidence sufficient, and quality is not a zero", () => {
  assert.equal(labelInitialState("evidence_sufficient"), "Evidence sufficient");
  assert.equal(labelInitialState("answer_unsupported"), "Answer unsupported");
  assert.equal(qualityStatus({ has_answer: true, quality: { faithfulness: 0.4 } }), "Scored");
  assert.equal(qualityStatus({ has_answer: true }), "Not scored");
  assert.equal(qualityStatus({ has_answer: true, abstained: true, quality: { context_relevance: 0.2 } }), "Not applicable");
  assert.equal(qualityStatus({ has_answer: false }), "Not applicable");
});

test("gap-aware runs can be filtered without treating a safe stop as a rewrite", () => {
  const rows = [
    run({
      logical_run_id: "gap",
      recovery_policy: "v2c_gap_aware",
      recovery: ["expand", "abstain"],
      safe_stop: true,
      recovery_required: true,
      recovery_applied: true,
      verification: "still_failing",
    }),
    run({
      logical_run_id: "current",
      recovery_policy: "v1",
      recovery: ["rewrite"],
      safe_stop: false,
      recovery_required: true,
      recovery_applied: true,
    }),
  ];
  assert.equal(filterLogicalRuns(rows, { policy: "gap_aware" }).length, 1);
  assert.equal(filterLogicalRuns(rows, { policy: "v1" }).length, 1);
  assert.equal(filterLogicalRuns(rows, { action: "safe_stop" }).length, 1);
  assert.equal(labelRecovery(rows[0]), "Expand → Safe stop");
  assert.equal(presentVerification(rows[0]), "Safe stop");
  assert.equal(labelVerification(rows[0]), "Still failing");
  assert.equal(filterLogicalRuns(rows, { policy: "all" }).length, 2);
});

test("a safe stop stays out of the failure filters but a real still-failing run does not (#117)", () => {
  const rows = [
    run({
      logical_run_id: "gap",
      recovery: ["expand", "abstain"],
      safe_stop: true,
      recovery_required: true,
      recovery_applied: true,
      verification: "still_failing",
    }),
    run({
      logical_run_id: "failing",
      recovery: ["rewrite"],
      safe_stop: false,
      recovery_required: true,
      recovery_applied: true,
      verification: "still_failing",
    }),
    run({
      logical_run_id: "abstained",
      recovery: ["abstain"],
      safe_stop: false,
      recovery_required: true,
      recovery_applied: true,
      verification: "unchanged",
    }),
  ];
  const ids = (filters) => filterLogicalRuns(rows, filters).map((row) => row.logical_run_id);
  assert.deepEqual(ids({ verification: "still_failing" }), ["failing"]);
  assert.deepEqual(ids({ verification: "needs" }), ["failing"]);
  assert.deepEqual(ids({ verification: "degraded" }), []);
  assert.deepEqual(ids({ action: "abstain" }), ["abstained"]);
  assert.deepEqual(ids({ action: "safe_stop" }), ["gap"]);
  assert.deepEqual(ids({ action: "expand" }), ["gap"]);
  assert.deepEqual(ids({ verification: "all" }), ["gap", "failing", "abstained"]);
  assert.equal(labelVerification(rows[0]), "Still failing");
});

test("formatWhen shows a UTC trace time in the viewer's zone, not the raw UTC string", () => {
  const stamp = "2026-10-05T17:35:09.785652+00:00";
  const opts = { locale: "en-US", now: "2026-10-15T00:00:00Z" };
  assert.equal(formatWhen(stamp, { ...opts, timeZone: "Asia/Manila" }), "Oct 6, 01:35 AM");
  assert.equal(formatWhen(stamp, { ...opts, timeZone: "UTC" }), "Oct 5, 05:35 PM");
});

test("formatWhen adds the year only when it is not the current year", () => {
  const out = formatWhen("2025-03-01T12:00:00Z", { locale: "en-US", timeZone: "UTC", now: "2026-10-15T00:00:00Z" });
  assert.equal(out, "Mar 1, 2025, 12:00 PM");
});

test("formatWhen keeps an empty placeholder and passes unparseable text through", () => {
  assert.equal(formatWhen(""), "—");
  assert.equal(formatWhen(null, { empty: "" }), "");
  assert.equal(formatWhen("not a date"), "not a date");
});

const VIEWS = ["overview", "test", "reliability", "data", "configuration", "integrations"];
const ALIASES = { evaluation: "reliability", playground: "test" };

test("parseRoute reads the Reliability tab from the hash", () => {
  assert.deepEqual(parseRoute("#reliability/quality", VIEWS, ALIASES), { view: "reliability", tab: "quality" });
  assert.deepEqual(parseRoute("#reliability", VIEWS, ALIASES), { view: "reliability", tab: "overview" });
  assert.deepEqual(parseRoute("#evaluation", VIEWS, ALIASES), { view: "reliability", tab: "overview" });
  assert.deepEqual(parseRoute("#overview", VIEWS, ALIASES), { view: "overview", tab: "overview" });
});

test("parseRoute keeps an unknown Reliability suffix on Reliability Summary", () => {
  assert.deepEqual(parseRoute("#reliability/nope", VIEWS, ALIASES), { view: "reliability", tab: "overview" });
  assert.deepEqual(parseRoute("#nowhere", VIEWS, ALIASES), { view: "overview", tab: "overview" });
});

test("routeHash gives Summary no suffix and other tabs one", () => {
  assert.equal(routeHash("reliability", "overview"), "#reliability");
  assert.equal(routeHash("reliability", "runs"), "#reliability/runs");
  assert.equal(routeHash("data", "runs"), "#data");
});
