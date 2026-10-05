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

  function buildFlight(traces) {
    const list = (Array.isArray(traces) ? traces : []).filter((item) => item && typeof item === "object");
    if (!list.length) return null;
    const pending = pendingRecovery(list);
    const attempts = attemptRecords(list);
    const applied = attempts.length > 0;
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
      status: runStatus(list, pending, applied, verification, afterAnswer),
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
        title: `Recovery · ${labelAction(attempt.action)}`,
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

  function runStatus(list, pending, applied, verification, afterAnswer) {
    if (pending) return "recovery_proposed";
    if (isAbstention(afterAnswer, list[list.length - 1]) && applied) return verification || "abstained";
    if (verification) return verification;
    if (!applied) {
      const evaluation = evaluationOf(list[0].runtime_evaluation) || evaluationOf(list[0].first_pass_evaluation);
      if (!evaluation && !String(list[0].answer || "").trim()) return "retrieve_only";
      if (!evaluation) return "baseline";
      return "no_recovery_needed";
    }
    return "applied";
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
    return String(answer || "").trim() === ABSTAIN_ANSWER;
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

  return {
    ABSTAIN_ANSWER,
    ACTION_EFFECT,
    MODE_NOTES,
    buildFlight,
    modeNote,
    labelAction,
    labelOutcome,
    sourceLabel,
  };
});
