// Read-only description of one logical run for the Test Console.
// No DOM. Does not invent stages the traces do not contain.

(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FlightRecorder = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const ABSTAIN_ANSWER = "I do not know based on the retrieved documents.";

  const MODE_NOTES = {
    retrieve_only: "Retrieve evidence without generating or evaluating.",
    baseline: "Retrieve and generate once. No recovery.",
    loop_confirm: "Evaluate the first response and propose recovery. Nothing is applied until you confirm.",
    loop: "Evaluate the first response and automatically attempt up to the configured recovery limit when needed.",
  };

  const ACTION_EFFECT = {
    regenerate: "Regenerate the answer from the same evidence. Retrieval does not change.",
    rewrite: "Rewrite the retrieval query and retrieve again. The original question is still what gets judged.",
    expand: "Retrieve again with a higher top_k, then generate from the wider evidence.",
    abstain: "Stop and abstain instead of answering from the retrieved documents.",
  };

  function modeNote(mode) {
    return MODE_NOTES[mode] || "";
  }

  function schemaVersion(trace) {
    const value = trace && trace.trace_schema_version;
    if (typeof value !== "number" || !Number.isInteger(value) || value < 1) return 1;
    return value;
  }

  function buildFlight(traces) {
    const list = (Array.isArray(traces) ? traces : []).filter((item) => item && typeof item === "object");
    if (!list.length) return null;
    if (list.some((trace) => schemaVersion(trace) > 2)) return unsupportedFlight(list);
    const pending = pendingRecovery(list);
    const attempts = attemptRecords(list);
    const applied = attempts.some((item) => item.executed !== false);
    const beforeChunks = initialChunks(list);
    const afterChunks = finalChunks(list);
    const beforeEval = initialEval(list);
    const afterEval = finalEval(list);
    const beforeAnswer = initialAnswer(list, applied);
    const afterAnswer = applied ? String(list[list.length - 1].answer || "") : "";
    const verification = finalVerification(list, applied);
    const signal = retrievalWarning(list);
    return {
      query: String(list[0].query || ""),
      traceIds: list.map((trace) => String(trace.run_id || "")).filter(Boolean),
      joined: list.length > 1,
      topK: numberOrNull(list[list.length - 1].top_k),
      latencyMs: sumLatency(list),
      attempts,
      attemptCount: attempts.length,
      pending,
      verification,
      status: runStatus(list, pending, applied, verification, afterAnswer, attempts),
      before: {
        query: String(list[0].query || ""),
        chunks: beforeChunks,
        answer: beforeAnswer,
        evaluation: beforeEval,
        diagnosis: initialDiagnosis(list, applied),
      },
      after: applied
        ? {
            rewrittenQuery: rewrittenQuery(list, attempts),
            chunks: afterChunks,
            answer: afterAnswer,
            evaluation: afterEval,
            abstained: isAbstention(afterAnswer, list[list.length - 1]),
          }
        : null,
      evidence: applied ? diffChunks(beforeChunks, afterChunks) : null,
      retrievalWarning: signal,
      phases: phasesFor(list, beforeChunks, beforeAnswer, beforeEval, attempts, verification, applied),
      runMode: explicitMode(list),
      timings: stageTimings(list),
      recoveryPolicy: explicitPolicy(list),
    };
  }

  function phasesFor(list, chunks, answer, evaluation, attempts, verification, applied) {
    const initial = {
      key: "initial",
      title: "Initial attempt",
      steps: [
        { kind: "query", title: "Query", detail: String(list[0].query || "") },
        { kind: "retrieve", title: "Retrieve", detail: chunkDetail(chunks) },
      ],
    };
    if (showsGenerate(list[0], answer, applied)) {
      initial.steps.push({
        kind: "generate",
        title: "Generate",
        detail: clip(answer || "(empty)"),
      });
    }
    if (evaluation) {
      initial.steps.push({ kind: "judge", title: "Judge", detail: judgeDetail(evaluation) });
    }
    initial.steps.push({
      kind: "diagnose",
      title: "Diagnosis",
      detail: initialDiagnosis(list, applied),
    });
    const phases = [initial];
    attempts.forEach((attempt, index) => {
      phases.push({
        key: `recovery-${index}`,
        title: attempt.stopReason
          ? "Recovery · Safe stop"
          : `Recovery · ${labelAction(attempt.action)}`,
        action: attempt.action,
        steps: attemptSteps(attempt),
      });
    });
    if (verification) {
      phases.push({
        key: "verification",
        title: "Runtime verification",
        steps: [
          {
            kind: "verify",
            title: labelOutcome(verification),
            detail: "Compares runtime judge flags from the first pass to the final state. Not ground-truth correctness.",
            outcome: verification,
          },
        ],
      });
    }
    return phases;
  }

  function attemptSteps(attempt) {
    const steps = [
      {
        kind: "recover",
        title: labelAction(attempt.action),
        detail: ACTION_EFFECT[attempt.action] || attempt.reason || "",
      },
    ];
    if (attempt.reason) {
      steps.push({ kind: "why", title: "Why", detail: attempt.reason });
    }
    if (attempt.stopReason) {
      steps.push({ kind: "why", title: "Recovery decision", detail: attempt.stopReason });
    }
    if (attempt.conflictSignal) {
      steps.push({
        kind: "why",
        title: "Conflict signal",
        detail: "Candidate diagnosis recorded on the trace. The answer does not treat it as a proven conflict.",
      });
    }
    if (attempt.neighborSignal) {
      steps.push({
        kind: "why",
        title: "Neighboring evidence",
        detail: "A retrieved figure appears to be about a different entity than the question.",
      });
    }
    if (attempt.decisionSource) {
      steps.push({ kind: "source", title: "Decision source", detail: attempt.decisionSource });
    }
    if (attempt.trigger === "retrieval_signal") {
      steps.push({ kind: "trigger", title: "Trigger", detail: "Retrieval signal" });
    }
    if (attempt.source) {
      steps.push({ kind: "source", title: attempt.source, detail: "" });
    }
    if (attempt.executed === false) {
      steps.push({
        kind: "why",
        title: "Not executed",
        detail: "The action did not change the run.",
      });
    }
    if (attempt.action === "rewrite" && attempt.rewrittenQuery) {
      steps.push({
        kind: "retrieve",
        title: "Rewritten retrieval query",
        detail: attempt.rewrittenQuery,
      });
    }
    if (attempt.action === "expand" && attempt.topK != null) {
      steps.push({
        kind: "retrieve",
        title: "Wider retrieval",
        detail: `top_k ${attempt.topK}`,
      });
    }
    if (attempt.answerRelation === "kept_previous") {
      steps.push({
        kind: "generate",
        title: "Kept previous answer",
        detail: clip(attempt.answer || ""),
      });
    } else if (attempt.answerRelation === "generated") {
      steps.push({
        kind: "generate",
        title: attempt.action === "regenerate" ? "Answer regenerated" : "Answer",
        detail: clip(attempt.answer || "Same evidence."),
      });
    } else if (attempt.action === "regenerate") {
      steps.push({
        kind: "generate",
        title: "Answer regenerated",
        detail: "Same evidence.",
      });
    }
    if (attempt.answerRelation === "abstained" || attempt.action === "abstain") {
      steps.push({
        kind: "abstain",
        title: "Safe abstention",
        detail: attempt.answer || ABSTAIN_ANSWER,
      });
    }
    if (attempt.evaluation) {
      steps.push({
        kind: "judge",
        title: attempt.evaluationSource === "probe" ? "Probe judge" : "Judge",
        detail: judgeDetail(attempt.evaluation),
      });
    }
    if (attempt.verification) {
      steps.push({
        kind: "verify",
        title: "Attempt check",
        detail: labelOutcome(attempt.verification),
        outcome: attempt.verification,
      });
    }
    if (attempt.attributedClass) {
      steps.push({
        kind: "diagnose",
        title: "Attributed class",
        detail: attempt.attributedClass,
      });
    }
    return steps;
  }

  function showsGenerate(trace, answer, applied) {
    const model = String(trace.model || "");
    if (model === "none" && !String(answer || "").trim() && !applied) return false;
    if (!applied && model === "none" && !String(trace.answer || "").trim()) return false;
    return Boolean(String(answer || "").trim() || (model && model !== "none") || applied);
  }

  function pendingRecovery(list) {
    if (list.some((trace) => appliedOnTrace(trace).length)) return null;
    for (const trace of list) {
      if (trace.recovery_status !== "proposed") continue;
      const recovery = dict(trace.recovery);
      const action = actionName(recovery.action);
      if (!action || action === "accept" || action === "none") continue;
      const diagnosis = dict(trace.diagnosis);
      return {
        action,
        reason: String(recovery.reason || ""),
        trigger: String(recovery.trigger || ""),
        source: sourceLabel(recovery.source),
        sourceRaw: String(recovery.source || ""),
        diagnosis: diagnosis.failure_class || null,
        diagnosisRationale: String(diagnosis.rationale || ""),
        effect: ACTION_EFFECT[action] || "",
        runId: String(trace.run_id || ""),
      };
    }
    return null;
  }

  function attemptRecords(list) {
    const records = [];
    for (const trace of list) {
      const stored = (Array.isArray(trace.recovery_attempts) ? trace.recovery_attempts : []).filter(
        (item) => item && typeof item === "object"
      );
      if (stored.length) {
        stored.forEach((item) => {
          const action = actionName(item.action);
          if (!action || action === "accept" || action === "none") return;
          const recovery = dict(trace.recovery);
          records.push({
            action,
            verification: outcomeOf(item.verification),
            trigger: String(item.trigger || recovery.trigger || ""),
            source: sourceLabel(item.source || recovery.source),
            sourceRaw: String(item.source || recovery.source || ""),
            attributedClass: item.attributed_class || null,
            rewrittenQuery: item.rewritten_query || null,
            topK: numberOrNull(item.top_k),
            reason: String(item.reason || recovery.reason || ""),
            stopReason: stopReason(item),
            conflictSignal: signalFlag(item, "conflict_signal"),
            neighborSignal: signalFlag(item, "neighbor_signal"),
            decisionSource: signalText(item, "decision_source"),
            opportunity: signalText(item, "recovery_opportunity"),
            historical: false,
            answer: item.answer != null ? String(item.answer) : "",
            answerRelation: String(item.answer_relation || ""),
            evidenceRelation: String(item.evidence_relation || ""),
            evaluation: evaluationOf(item.runtime_evaluation),
            evaluationSource: String(item.evaluation_source || ""),
            executed: item.executed !== false,
          });
        });
        continue;
      }
      const actions = appliedOnTrace(trace);
      if (!actions.length) continue;
      const recovery = dict(trace.recovery);
      records.push({
        action: actions[0],
        verification: outcomeOf(trace.verification),
        trigger: String(recovery.trigger || ""),
        source: sourceLabel(recovery.source),
        sourceRaw: String(recovery.source || ""),
        attributedClass: recovery.attributed_class || null,
        rewrittenQuery: trace.rewritten_query || null,
        topK: numberOrNull(trace.top_k),
        reason: String(recovery.reason || ""),
        stopReason: stopReason(recovery),
        conflictSignal: signalFlag(recovery, "conflict_signal"),
        neighborSignal: signalFlag(recovery, "neighbor_signal"),
        decisionSource: signalText(recovery, "decision_source"),
        opportunity: signalText(recovery, "recovery_opportunity"),
        historical: true,
      });
    }
    return records;
  }

  function appliedOnTrace(trace) {
    const stored = (Array.isArray(trace.recovery_attempts) ? trace.recovery_attempts : []).filter(
      (item) => item && typeof item === "object"
    );
    if (stored.length) {
      return stored
        .filter((item) => item.executed !== false)
        .map((item) => actionName(item.action))
        .filter((action) => action && action !== "accept" && action !== "none");
    }
    if (trace.recovery_status === "proposed") return [];
    const action = actionName(dict(trace.recovery).action);
    if (!action || action === "accept" || action === "none") return [];
    return [action];
  }

  function explicitInitial(list) {
    for (const trace of list) {
      if (schemaVersion(trace) !== 2) continue;
      if (trace.initial && typeof trace.initial === "object") return trace.initial;
    }
    return null;
  }

  function explicitMode(list) {
    const root = list.find((trace) => !trace.parent_run_id) || list[0];
    const mode = String((root && root.run_mode) || "").trim();
    if (mode) return mode;
    for (const trace of list) {
      const other = String(trace.run_mode || "").trim();
      if (other) return other;
    }
    return null;
  }

  function initialChunks(list) {
    const initial = explicitInitial(list);
    if (initial && Array.isArray(initial.retrieved_chunks)) return initial.retrieved_chunks;
    for (const trace of list) {
      if (Array.isArray(trace.previous_retrieved_chunks)) return trace.previous_retrieved_chunks;
    }
    const first = list[0];
    return Array.isArray(first.retrieved_chunks) ? first.retrieved_chunks : [];
  }

  function finalChunks(list) {
    const last = list[list.length - 1];
    return Array.isArray(last.retrieved_chunks) ? last.retrieved_chunks : [];
  }

  function initialAnswer(list, applied) {
    const initial = explicitInitial(list);
    if (initial && initial.answer != null) return String(initial.answer);
    for (const trace of list) {
      if (trace.previous_answer != null && String(trace.previous_answer).length) {
        return String(trace.previous_answer);
      }
    }
    if (list.length > 1) return String(list[0].answer || "");
    if (applied) return "";
    return String(list[0].answer || "");
  }

  function initialEval(list) {
    const initial = explicitInitial(list);
    const stored = initial ? evaluationOf(initial.runtime_evaluation) : null;
    if (stored) return stored;
    const root = list.find((trace) => !trace.parent_run_id) || list[0];
    const firstPass = evaluationOf(root.first_pass_evaluation);
    if (firstPass) return firstPass;
    const recovered = list.some((trace) => appliedOnTrace(trace).length);
    if (!recovered || root.recovery_status === "proposed") return evaluationOf(root.runtime_evaluation);
    return null;
  }

  function finalEval(list) {
    for (let index = list.length - 1; index >= 0; index -= 1) {
      const evaluation = evaluationOf(list[index].runtime_evaluation);
      if (evaluation) return evaluation;
    }
    return null;
  }

  function evaluationOf(value) {
    if (!value || typeof value !== "object" || typeof value.evidence_sufficient !== "boolean") return null;
    const supported = value.answer_supported;
    return {
      evidence_sufficient: value.evidence_sufficient,
      answer_supported: supported === true || supported === false ? supported : null,
    };
  }

  function initialDiagnosis(list, applied) {
    const initial = explicitInitial(list);
    const stored = initial ? dict(initial.diagnosis) : null;
    if (stored && (stored.failure_class || stored.rationale)) {
      return stored.failure_class ? String(stored.failure_class) : String(stored.rationale);
    }
    if (!applied) {
      const diagnosis = dict(list[0].diagnosis);
      return diagnosis.failure_class ? String(diagnosis.failure_class) : "Diagnosis not yet attributed.";
    }
    const root = list.find((trace) => !trace.parent_run_id) || list[0];
    if (root.recovery_status === "proposed") {
      const diagnosis = dict(root.diagnosis);
      return diagnosis.failure_class ? String(diagnosis.failure_class) : "Diagnosis not yet attributed.";
    }
    return "Diagnosis not yet attributed.";
  }

  function finalVerification(list, applied) {
    if (!applied) return null;
    for (let index = list.length - 1; index >= 0; index -= 1) {
      if (!appliedOnTrace(list[index]).length) continue;
      const outcome = outcomeOf(list[index].verification);
      if (outcome) return outcome;
    }
    return null;
  }

  function stopReason(item) {
    const parameters = item && item.parameters;
    if (!parameters || typeof parameters !== "object") return "";
    return String(parameters.stop_reason || "");
  }

  function rewrittenQuery(list, attempts) {
    const fromAttempt = attempts.map((item) => item.rewrittenQuery).filter(Boolean);
    if (fromAttempt.length) return String(fromAttempt[fromAttempt.length - 1]);
    for (const trace of list) {
      if (trace.rewritten_query) return String(trace.rewritten_query);
    }
    return null;
  }

  function retrievalWarning(list) {
    for (const trace of list) {
      const signal = dict(trace.retrieval_signal);
      if (!signal.weak_top && !signal.ambiguous_top) continue;
      const recovery = dict(trace.recovery);
      return {
        weakTop: Boolean(signal.weak_top),
        ambiguousTop: Boolean(signal.ambiguous_top),
        reason: String(signal.reason || ""),
        topScore: numberOrNull(signal.top_score),
        runnerUpScore: numberOrNull(signal.runner_up_score),
        triggeredRecovery: recovery.trigger === "retrieval_signal" || trace.recovery_attempts
          ? attemptsTriggered(trace)
          : recovery.trigger === "retrieval_signal",
      };
    }
    for (const trace of list) {
      if (dict(trace.recovery).trigger === "retrieval_signal") {
        return {
          weakTop: false,
          ambiguousTop: false,
          reason: String(dict(trace.recovery).reason || "Retrieval looked unreliable."),
          topScore: null,
          runnerUpScore: null,
          triggeredRecovery: true,
        };
      }
    }
    return null;
  }

  function attemptsTriggered(trace) {
    const recovery = dict(trace.recovery);
    if (recovery.trigger === "retrieval_signal") return true;
    const stored = Array.isArray(trace.recovery_attempts) ? trace.recovery_attempts : [];
    return stored.some((item) => item && item.trigger === "retrieval_signal");
  }

  function runStatus(list, pending, applied, verification, afterAnswer, attempts) {
    if (pending) return "recovery_proposed";
    if (applied && (attempts || []).some((attempt) => attempt.stopReason)) return "safe_stop";
    if (isAbstention(afterAnswer, list[list.length - 1]) && applied) return verification || "abstained";
    if (verification) return verification;
    if (!applied) {
      if (attempts && attempts.length) return "not_executed";
      const evaluation = evaluationOf(list[0].runtime_evaluation) || evaluationOf(list[0].first_pass_evaluation);
      if (!evaluation && !String(list[0].answer || "").trim()) return "retrieve_only";
      if (!evaluation) return "baseline";
      return "no_recovery_needed";
    }
    return "applied";
  }

  function unsupportedFlight(list) {
    const last = list[list.length - 1];
    return {
      query: String(list[0].query || ""),
      traceIds: list.map((trace) => String(trace.run_id || "")).filter(Boolean),
      joined: list.length > 1,
      topK: null,
      latencyMs: null,
      attempts: [],
      attemptCount: 0,
      pending: null,
      verification: null,
      status: "unsupported_schema",
      before: {
        query: String(list[0].query || ""),
        chunks: [],
        answer: String((last && last.answer) || ""),
        evaluation: null,
        diagnosis: "Unsupported trace schema.",
      },
      after: null,
      evidence: null,
      retrievalWarning: null,
      phases: [],
      runMode: null,
      unsupportedSchema: true,
    };
  }

  function diffChunks(before, after) {
    const afterIds = new Set(after.map(chunkKey));
    const beforeIds = new Set(before.map(chunkKey));
    return {
      retained: before.filter((chunk) => afterIds.has(chunkKey(chunk))),
      removed: before.filter((chunk) => !afterIds.has(chunkKey(chunk))),
      added: after.filter((chunk) => !beforeIds.has(chunkKey(chunk))),
    };
  }

  function chunkKey(chunk) {
    if (!chunk || typeof chunk !== "object") return "";
    return String(chunk.chunk_id || chunk.doc_id || "");
  }

  function isAbstention(answer, trace) {
    if (trace && String(trace.model || "") === "abstain") return true;
    return String(answer || "").trim().toLowerCase().startsWith("i do not know");
  }

  function signalFlag(item, key) {
    const parameters = item && item.parameters;
    return Boolean(parameters && typeof parameters === "object" && parameters[key]);
  }

  function signalText(item, key) {
    const parameters = item && item.parameters;
    if (!parameters || typeof parameters !== "object") return "";
    return String(parameters[key] || "");
  }

  function explicitPolicy(list) {
    const root = list.find((trace) => !trace.parent_run_id) || list[0];
    const stored = String((root && root.recovery_policy) || "").trim();
    return stored || "v1";
  }

  function outcomeOf(value) {
    if (!value || typeof value !== "object" || value.outcome == null) return null;
    const text = String(value.outcome).trim();
    return text || null;
  }

  function sourceLabel(value) {
    const raw = String(value || "").trim().toLowerCase();
    if (raw === "operator") return "Operator-selected";
    if (raw === "policy") return "Automatic policy";
    return raw ? raw : "";
  }

  function labelAction(action) {
    if (action === "rewrite") return "Rewrite";
    if (action === "expand") return "Expand";
    if (action === "regenerate") return "Regenerate";
    if (action === "abstain") return "Abstain";
    return action || "Recovery";
  }

  function labelOutcome(outcome) {
    if (outcome === "improved") return "Improved";
    if (outcome === "unchanged") return "Unchanged";
    if (outcome === "still_failing") return "Still failing";
    if (outcome === "degraded") return "Degraded";
    return outcome || "";
  }

  function judgeDetail(evaluation) {
    const evidence = evaluation.evidence_sufficient ? "Evidence sufficient" : "Evidence insufficient";
    let support = "Answer support not checked";
    if (evaluation.answer_supported === true) support = "Answer supported";
    if (evaluation.answer_supported === false) support = "Answer unsupported";
    return `${evidence}. ${support}.`;
  }

  function chunkDetail(chunks) {
    const count = chunks.length;
    return count === 1 ? "1 passage" : `${count} passages`;
  }

  function clip(value) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    if (text.length <= 140) return text;
    return `${text.slice(0, 139)}…`;
  }

  function sumLatency(list) {
    const values = list
      .map((trace) => trace.latency_ms)
      .filter((value) => typeof value === "number" && !Number.isNaN(value));
    if (!values.length) return null;
    return values.reduce((sum, value) => sum + value, 0);
  }

  function numberOrNull(value) {
    return typeof value === "number" && !Number.isNaN(value) ? value : null;
  }

  function dict(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function actionName(value) {
    return String(value || "").trim().toLowerCase();
  }

  // The agent loop as six stages, each with what happened on this run. Drawn
  // as the loop map at the top of a Test Console run. States: done, flagged
  // (the judge or diagnosis found a problem), pass / fail / neutral / safe
  // (verification), pending (proposed, not applied), skipped (not part of
  // this run). Never invents a stage the trace does not show.
  const LOOP_STAGES = [
    ["retrieve", "Retrieve"],
    ["generate", "Generate"],
    ["judge", "Judge"],
    ["diagnose", "Diagnose"],
    ["recover", "Recover"],
    ["verify", "Verify"],
  ];

  function loopStages(flight) {
    if (!flight) return LOOP_STAGES.map(([key, label]) => ({ key, label, state: "idle", note: "" }));
    const initial = (flight.phases || []).find((phase) => phase.key === "initial") || { steps: [] };
    const has = (kind) => initial.steps.some((step) => step.kind === kind);
    const step = (kind) => initial.steps.find((item) => item.kind === kind);
    const evaluation = flight.before && flight.before.evaluation;
    const flagged = Boolean(
      evaluation && (evaluation.evidence_sufficient === false || evaluation.answer_supported === false)
    );
    const attempts = (flight.attempts || []).filter((attempt) => attempt.executed !== false);
    const stages = {};

    stages.retrieve = { state: has("retrieve") ? "done" : "skipped", note: has("retrieve") ? step("retrieve").detail : "" };
    stages.generate = has("generate")
      ? { state: "done", note: "Answer drafted" }
      : { state: "skipped", note: flight.runMode === "retrieve_only" ? "Retrieve only" : "" };
    if (!evaluation) stages.judge = { state: "skipped", note: "Not judged" };
    else if (flagged) {
      stages.judge = {
        state: "flagged",
        note: evaluation.evidence_sufficient === false ? "Evidence insufficient" : "Answer unsupported",
      };
    } else stages.judge = { state: "done", note: "Looks grounded" };

    const recoveryNeeded = flagged || attempts.length > 0 || Boolean(flight.pending);
    if (!recoveryNeeded) stages.diagnose = { state: "skipped", note: evaluation ? "Nothing to diagnose" : "" };
    else {
      const raw = String((flight.before && flight.before.diagnosis) || "");
      const attributed = raw && raw !== "Diagnosis not yet attributed.";
      stages.diagnose = { state: attributed ? "flagged" : "done", note: attributed ? DIAGNOSIS_LABELS[raw] || raw : "Not attributed" };
    }

    if (flight.pending) stages.recover = { state: "pending", note: `${labelAction(flight.pending.action)} proposed` };
    else if (attempts.length) {
      const path = attempts.map((attempt) => (attempt.stopReason ? "Safe stop" : labelAction(attempt.action)));
      stages.recover = { state: "done", note: path.join(" → ") };
    } else stages.recover = { state: "skipped", note: evaluation && !flagged ? "Not needed" : "" };

    const outcome = flight.status === "safe_stop" ? "safe_stop" : flight.verification;
    const verifyState = {
      improved: "pass",
      unchanged: "neutral",
      still_failing: "fail",
      degraded: "fail",
      safe_stop: "safe",
    }[outcome];
    stages.verify = verifyState
      ? { state: verifyState, note: outcome === "safe_stop" ? "Safe stop" : labelOutcome(outcome) }
      : { state: "skipped", note: "" };

    return LOOP_STAGES.map(([key, label]) => ({ key, label, ...stages[key] }));
  }

  const DIAGNOSIS_LABELS = {
    unsupported_generation: "Unsupported generation",
    retrieval_miss: "Retrieval miss",
    evidence_insufficiency: "Evidence insufficiency",
  };

  // Stage timings across the traces of one logical run. Each trace's offsets
  // start at its own run, so a confirmed child is placed after its parent.
  // Returns null when no trace recorded timings (older runs).
  function stageTimings(list) {
    let offset = 0;
    const rows = [];
    let seen = false;
    for (const trace of list) {
      const items = Array.isArray(trace.stage_timings) ? trace.stage_timings : null;
      if (items) {
        seen = true;
        items.forEach((item) => {
          const start = Number(item.started_ms);
          const duration = Number(item.duration_ms);
          if (!Number.isFinite(start) || !Number.isFinite(duration)) return;
          rows.push({
            stage: String(item.stage || ""),
            attempt: item.attempt == null ? null : Number(item.attempt),
            action: item.action ? String(item.action) : null,
            status: item.status === "error" ? "error" : "ok",
            startMs: offset + start,
            durationMs: duration,
          });
        });
      }
      const latency = Number(trace.latency_ms);
      if (Number.isFinite(latency)) offset += latency;
    }
    if (!seen) return null;
    return rows.sort((a, b) => a.startMs - b.startMs);
  }

  // Waterfall rows for the timeline: label, depth (recovery work nests under
  // its attempt), and left / width as percentages of the whole run.
  function timelineRows(flight) {
    const rows = (flight && flight.timings) || null;
    if (!rows || !rows.length) return null;
    const total = Math.max(
      Number(flight.latencyMs) || 0,
      ...rows.map((row) => row.startMs + row.durationMs),
      1
    );
    const label = (row) => {
      const base = { retrieve: "Retrieve", generate: "Generate", judge: "Judge", diagnose: "Diagnose", recover: "Recover", verify: "Verify" }[row.stage] || row.stage;
      if (row.stage === "recover" && row.action) return `${base} · ${labelAction(row.action)}`;
      return base;
    };
    return {
      totalMs: total,
      rows: rows.map((row) => ({
        stage: row.stage,
        label: label(row),
        depth: row.attempt != null && row.stage !== "recover" ? 1 : 0,
        attempt: row.attempt,
        status: row.status,
        startMs: row.startMs,
        durationMs: row.durationMs,
        left: (100 * row.startMs) / total,
        width: Math.max(0.6, (100 * row.durationMs) / total),
      })),
    };
  }

  // Live progress from streamed stage events: the state of each loop stage
  // while the run is still going.
  function liveStages(events) {
    const states = Object.fromEntries(LOOP_STAGES.map(([key]) => [key, { state: "idle", ms: null, note: "" }]));
    for (const event of events || []) {
      const key = event && event.stage;
      if (!states[key]) continue;
      // A stage can run again inside a recovery attempt. The node keeps the
      // total time across runs and how many times it ran.
      const prior = states[key];
      if (event.type === "stage_start") {
        states[key] = {
          state: "running",
          ms: prior.ms,
          count: prior.count || 0,
          note: key === "recover" && event.action ? labelAction(event.action) : prior.note,
        };
      } else if (event.type === "stage_end") {
        const ms = Number(event.duration_ms);
        states[key] = {
          state: event.status === "error" ? "fail" : "done",
          ms: Number.isFinite(ms) ? (prior.ms || 0) + ms : prior.ms,
          count: (prior.count || 0) + 1,
          note: key === "recover" && event.action ? labelAction(event.action) : prior.note,
        };
      }
    }
    return LOOP_STAGES.map(([key, label]) => ({ key, label, ...states[key] }));
  }

  const SAFE_STOP_NOTE = "Bounded recovery stopped because sufficient support was not found.";

  // How one flight step reads on screen. Inside a safe stop the heading is the
  // status, so the attempt's stored verifier words are introduced as the
  // recorded result instead of a second status, and the abstention is the
  // stopped answer. step.outcome is left alone for anything that reads data.
  function presentStep(phase, step, flightStatus) {
    const safePhase = String((phase && phase.title) || "") === "Recovery · Safe stop";
    const safeVerify = flightStatus === "safe_stop" && phase && phase.key === "verification";
    if (safeVerify || (safePhase && step.kind === "verify")) {
      const stored = safeVerify ? step.title : step.detail;
      return {
        title: "Verifier recorded",
        detail: `${stored || "Verifier result"}. ${SAFE_STOP_NOTE} This stored result stays in the trace and is not a second status.`,
      };
    }
    if (safePhase && step.kind === "abstain") {
      return { title: "Stopped answer", detail: step.detail || "" };
    }
    return { title: step.title || "", detail: step.detail || "" };
  }

  return {
    ABSTAIN_ANSWER,
    ACTION_EFFECT,
    MODE_NOTES,
    buildFlight,
    modeNote,
    labelAction,
    labelOutcome,
    presentStep,
    loopStages,
    LOOP_STAGES,
    timelineRows,
    liveStages,
    SAFE_STOP_NOTE,
    sourceLabel,
  };
});
