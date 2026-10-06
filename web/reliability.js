// Filters and labels for the Reliability investigation page.
// Reads logical-run rows. Does not interpret traces a second time.

(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ReliabilityView = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function filterLogicalRuns(runs, filters) {
    const list = Array.isArray(runs) ? runs : [];
    const spec = filters && typeof filters === "object" ? filters : {};
    const query = String(spec.query || "").trim().toLowerCase();
    return list.filter((run) => runMatches(run || {}, spec, query));
  }

  function runMatches(run, spec, query) {
    if (query && !String(run.query || "").toLowerCase().includes(query)) return false;
    if (!verificationMatches(run, spec.verification || "all")) return false;
    if (!recoveryMatches(run, spec.recovery || "all")) return false;
    if (!actionMatches(run, spec.action || "all")) return false;
    if (!policyMatches(run, spec.policy || "all")) return false;
    if (!diagnosisMatches(run, spec.diagnosis || "all")) return false;
    return true;
  }

  function verificationMatches(run, filter) {
    if (filter === "all") return true;
    if (filter === "needs") return run.verification === "still_failing" || run.verification === "degraded";
    if (filter === "pending") return Boolean(run.recovery_pending);
    if (filter === "not_applicable") return !run.verification && !run.recovery_pending;
    return run.verification === filter;
  }

  function recoveryMatches(run, filter) {
    if (filter === "all") return true;
    if (filter === "required") return Boolean(run.recovery_required);
    if (filter === "none") return !run.recovery_required;
    if (filter === "pending") return Boolean(run.recovery_pending);
    if (filter === "applied") {
      if (typeof run.recovery_applied === "boolean") return run.recovery_applied;
      return (run.recovery || []).length > 0;
    }
    return true;
  }

  function actionMatches(run, filter) {
    if (filter === "all") return true;
    if (filter === "safe_stop") return Boolean(run.safe_stop);
    const actions = run.recovery || [];
    return actions.includes(filter) || run.recovery_pending === filter;
  }

  function policyMatches(run, filter) {
    if (filter === "all") return true;
    const stored = String(run.recovery_policy || "v1");
    if (filter === "gap_aware") return stored === "v2c_gap_aware" || stored === "gap_aware";
    return stored === filter;
  }

  function diagnosisMatches(run, filter) {
    if (filter === "all") return true;
    const diagnoses = run.diagnoses || [];
    if (filter === "unattributed") return Boolean(run.judged) && diagnoses.length === 0;
    return diagnoses.includes(filter);
  }

  function recoveryCases(runs) {
    return (Array.isArray(runs) ? runs : []).filter((run) => run && run.recovery_required);
  }

  function labelAction(action) {
    if (action === "rewrite") return "Rewrite";
    if (action === "expand") return "Expand";
    if (action === "regenerate") return "Regenerate";
    if (action === "abstain") return "Safe abstention";
    return action || "";
  }

  function recoveryPath(run) {
    const actions = ((run && run.recovery) || []).filter(Boolean).map(labelAction);
    if (actions.length) return actions.join(" → ");
    if (run && run.recovery_pending) return labelAction(run.recovery_pending);
    return "";
  }

  function labelRecovery(run) {
    if (!run) return "";
    if (run.recovery_pending && !(run.recovery || []).length) return "Recovery pending";
    const path = recoveryPath(run);
    if (path) {
      const labeled = run.safe_stop ? path.replace(/Safe abstention/g, "Safe stop") : path;
      return run.recovery_applied === false ? `${labeled} (not executed)` : labeled;
    }
    return "No recovery";
  }

  function labelInitialState(state) {
    if (state === "evidence_insufficient") return "Evidence insufficient";
    if (state === "answer_unsupported") return "Answer unsupported";
    if (state === "answer_supported") return "No issue detected";
    if (state === "evidence_sufficient") return "Evidence sufficient";
    if (state === "not_judged") return "Not judged";
    return state || "Not judged";
  }

  function labelVerification(run) {
    if (!run) return "";
    if (run.recovery_pending && !(run.recovery || []).length) return "Pending";
    if (run.verification === "improved") return "Improved";
    if (run.verification === "unchanged") return "Unchanged";
    if (run.verification === "still_failing") return "Still failing";
    if (run.verification === "degraded") return "Degraded";
    return "Not applicable";
  }

  function labelSource(source) {
    const raw = String(source || "").trim().toLowerCase();
    if (raw === "operator") return "Operator-selected";
    if (raw === "policy") return "Automatic policy";
    return raw;
  }

  function labelTrigger(trigger) {
    const raw = String(trigger || "").trim();
    if (!raw) return "";
    return raw
      .split(" · ")
      .map((part) => {
        if (part === "retrieval_signal") return "Retrieval signal";
        if (part === "judge") return "Judge";
        return part;
      })
      .join(" · ");
  }

  function labelDiagnosis(name) {
    if (name === "unsupported_generation") return "Unsupported generation";
    if (name === "retrieval_miss") return "Retrieval miss";
    if (name === "evidence_insufficiency") return "Evidence insufficiency";
    return name || "Not attributed";
  }

  function qualityStatus(run) {
    if (!run || run.abstained || !run.has_answer) return "Not applicable";
    if (run.quality) return "Scored";
    return "Not scored";
  }

  return {
    filterLogicalRuns,
    recoveryCases,
    recoveryPath,
    labelAction,
    labelRecovery,
    labelInitialState,
    labelVerification,
    labelSource,
    labelTrigger,
    labelDiagnosis,
    qualityStatus,
  };
});
