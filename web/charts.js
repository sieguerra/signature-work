// Evaluation overview charts. Colors are CSS variables (--c-*) so charts follow the theme. Plain SVG/HTML, no chart library.
// Every number is computed from runtime trace signals; gold labels never reach the UI.

const CHART_COLORS = {
  passed: "var(--c-pass)",
  flagged: "var(--c-flag)",
  not_judged: "var(--c-none)",
  none: "var(--c-none)",
  proposed: "var(--c-blue)",
  accepted: "var(--c-slate)",
  improved: "var(--c-pass)",
  unchanged: "var(--c-flag)",
  still_failing: "var(--c-fail)",
  degraded: "var(--c-fail-strong)",
  pending: "var(--c-blue)",
  answered: "var(--c-blue)",
  abstained: "var(--c-violet)",
  rewrite: "var(--c-flag)",
  expand: "var(--c-cyan)",
  regenerate: "var(--c-orange)",
  abstain: "var(--c-violet)",
  accept: "var(--c-pass)",
  evidence_insufficiency: "var(--c-flag)",
  retrieval_miss: "var(--c-cyan)",
  unsupported_generation: "var(--c-fail)",
  unattributed: "var(--c-none)",
};

const OUTCOME_LABELS = {
  accepted: "Accepted",
  improved: "Improved",
  unchanged: "Unchanged",
  still_failing: "Still failing",
  degraded: "Degraded",
  pending: "Awaiting confirm",
  none: "No verdict",
};

function chartColor(key) {
  const last = String(key).split(" → ").pop();
  return CHART_COLORS[key] || CHART_COLORS[last] || "var(--c-slate)";
}

function chartEsc(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function pct(part, whole) {
  return whole ? Math.round((100 * part) / whole) : 0;
}

function firstPassKey(run) {
  if (run.first_sufficient == null) return "not_judged";
  return run.first_sufficient && run.first_supported !== false ? "passed" : "flagged";
}

function outcomeKey(run) {
  if (run.status === "proposed") return "pending";
  if (!run.path.length) return run.first_sufficient == null ? "none" : "accepted";
  return run.verification || "none";
}

function tally(items, keyFn) {
  const counts = new Map();
  for (const item of items) {
    const key = keyFn(item);
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return counts;
}

// ---------- Loop steps: one box per stage, plain counts ----------

function stepRow(key, label, count, hint) {
  return `<li title="${chartEsc(hint || "")}"><span class="swatch" style="background:${chartColor(key)}"></span><span class="step-l">${chartEsc(label)}</span><b>${count}</b></li>`;
}

function stepBox(title, lead, rows) {
  return `<div class="step-box"><div class="step-t">${title}</div>${lead ? `<div class="step-lead">${lead}</div>` : ""}<ul>${rows.join("")}</ul></div>`;
}

function loopSteps(runs) {
  const checks = tally(runs, firstPassKey);
  const recovered = runs.filter((run) => run.path.length);
  const proposed = runs.filter((run) => run.status === "proposed").length;
  const skipped = runs.length - recovered.length - proposed;
  const paths = [...tally(recovered, (run) => run.path.join(" → ")).entries()].sort((a, b) => b[1] - a[1]);
  const verdicts = tally(recovered, (run) => run.verification || "none");
  const abstained = runs.filter((run) => run.abstained).length;
  const arrow = `<div class="step-arrow" aria-hidden="true">→</div>`;

  const check = stepBox("1 · Judge checks the first answer", "", [
    stepRow("passed", "Looked fine", checks.get("passed") || 0, "Evidence was enough and the answer was supported"),
    stepRow("flagged", "Flagged a problem", checks.get("flagged") || 0, "Evidence was missing or the answer was not supported"),
    ...(checks.get("not_judged") ? [stepRow("not_judged", "Not judged (baseline)", checks.get("not_judged"))] : []),
  ]);
  const recover = stepBox(
    "2 · Loop tries a fix",
    `${recovered.length} of ${runs.length} runs`,
    [
      ...paths.map(([path, count]) => stepRow(path, path, count)),
      ...(proposed ? [stepRow("proposed", "Waiting for you to confirm", proposed)] : []),
      stepRow("none", "No fix needed", skipped),
    ],
  );
  const verify = stepBox(
    "3 · Judge checks again",
    recovered.length ? `on the ${recovered.length} fixed runs` : "no fixes yet",
    ["improved", "unchanged", "still_failing", "degraded"]
      .filter((key) => verdicts.get(key))
      .map((key) =>
        stepRow(key, OUTCOME_LABELS[key], verdicts.get(key), {
          improved: "The judge's flags got better after the fix",
          unchanged: "The flags did not change",
          still_failing: "Still missing evidence or still unsupported",
          degraded: "The flags got worse after the fix",
        }[key]),
      ),
  );
  const final = stepBox("4 · What the user gets", "", [
    stepRow("answered", "An answer", runs.length - abstained),
    stepRow("abstained", "\u201cI do not know\u201d", abstained, "The loop abstained instead of answering"),
  ]);
  return `<div class="steps">${check}${arrow}${recover}${arrow}${verify}${arrow}${final}</div>`;
}

// ---------- Outcome by first check: one stacked bar per group ----------

const RESULT_LABELS = {
  accepted: "Kept first answer",
  improved: "Fixed: improved",
  unchanged: "Fixed: no change",
  still_failing: "Fixed: still failing",
  degraded: "Fixed: got worse",
  abstained: "Said \u201cI do not know\u201d",
  pending: "Awaiting confirm",
  none: "No verdict",
};

function resultKey(run) {
  if (run.status === "proposed") return "pending";
  if (run.abstained) return "abstained";
  if (!run.path.length) return run.first_sufficient == null ? "none" : "accepted";
  return run.verification || "none";
}

function outcomeByCheck(runs) {
  const groups = [
    ["passed", "Looked fine at first"],
    ["flagged", "Flagged at first"],
    ["not_judged", "Not judged"],
  ];
  const order = Object.keys(RESULT_LABELS);
  const seen = new Set();
  const rows = groups
    .map(([key, label]) => {
      const members = runs.filter((run) => firstPassKey(run) === key);
      if (!members.length) return "";
      const counts = tally(members, resultKey);
      const segments = order
        .filter((result) => counts.get(result))
        .map((result) => {
          seen.add(result);
          const count = counts.get(result);
          const width = (100 * count) / members.length;
          return `<span class="seg" style="width:${width}%;background:${chartColor(result === "accepted" ? "accepted" : result)}" title="${chartEsc(`${RESULT_LABELS[result]}: ${count}`)}">${width >= 9 ? count : ""}</span>`;
        })
        .join("");
      return `<div class="stack-row"><div class="stack-l">${label} <b>${members.length}</b></div><div class="stack">${segments}</div></div>`;
    })
    .join("");
  const legend = order
    .filter((result) => seen.has(result))
    .map((result) => `<li><span class="swatch" style="background:${chartColor(result)}"></span>${RESULT_LABELS[result]}</li>`)
    .join("");
  return `<div class="stacks">${rows}</div><ul class="legend-inline">${legend}</ul>`;
}

// ---------- Donut ----------

function donutSvg(entries, centerLabel) {
  const total = entries.reduce((sum, [, count]) => sum + count, 0);
  const R = 58;
  const r = 38;
  const cx = 70;
  const cy = 70;
  let angle = -Math.PI / 2;
  let arcs = "";
  for (const [key, count] of entries) {
    const sweep = (count / total) * Math.PI * 2;
    const end = angle + sweep;
    const large = sweep > Math.PI ? 1 : 0;
    const p = (rad, radius) => `${cx + radius * Math.cos(rad)},${cy + radius * Math.sin(rad)}`;
    const d =
      entries.length === 1
        ? `M${cx - R},${cy} A${R},${R} 0 1 1 ${cx + R},${cy} A${R},${R} 0 1 1 ${cx - R},${cy} M${cx - r},${cy} A${r},${r} 0 1 0 ${cx + r},${cy} A${r},${r} 0 1 0 ${cx - r},${cy} Z`
        : `M${p(angle, R)} A${R},${R} 0 ${large} 1 ${p(end, R)} L${p(end, r)} A${r},${r} 0 ${large} 0 ${p(angle, r)} Z`;
    arcs += `<path d="${d}" style="fill:${chartColor(key)}" fill-rule="evenodd"><title>${chartEsc(`${OUTCOME_LABELS[key] || key}: ${count}`)}</title></path>`;
    angle = end;
  }
  const legend = entries
    .map(
      ([key, count]) =>
        `<li><span class="swatch" style="background:${chartColor(key)}"></span>${chartEsc(OUTCOME_LABELS[key] || key)}<b>${count}</b><em>${pct(count, total)}%</em></li>`,
    )
    .join("");
  return `<div class="donut"><svg viewBox="0 0 140 140" role="img" aria-label="${chartEsc(centerLabel)}">${arcs}<text x="70" y="68" class="donut-n">${total}</text><text x="70" y="86" class="donut-sub">${chartEsc(centerLabel)}</text></svg><ul class="legend">${legend}</ul></div>`;
}

// ---------- Horizontal bars ----------

function hbars(entries, labelFn = (key) => key) {
  const max = Math.max(1, ...entries.map(([, count]) => count));
  return `<div class="hbars">${entries
    .map(
      ([key, count]) => `<div class="hbar">
        <span class="hbar-label" title="${chartEsc(labelFn(key))}">${chartEsc(labelFn(key))}</span>
        <span class="hbar-track"><span class="hbar-fill" style="width:${(100 * count) / max}%;background:${chartColor(key)}"></span></span>
        <span class="hbar-n">${count}</span>
      </div>`,
    )
    .join("")}</div>`;
}

// ---------- Judge flags before vs after recovery ----------

// The judge marks a bare "I do not know" as supported; the UI counts it as no answer instead.
function backedOrMet(run, key) {
  if (run[key] !== true) return false;
  if (key === "first_supported") return !run.first_abstained;
  if (key === "final_supported") return !run.abstained;
  return true;
}

function beforeAfter(recovered) {
  const n = recovered.length;
  const rows = [
    ["Found enough information", "first_sufficient", "final_sufficient"],
    ["Answer backed by the passages", "first_supported", "final_supported"],
  ];
  return `<div class="ba">${rows
    .map(([label, before, after]) => {
      const b = recovered.filter((run) => backedOrMet(run, before)).length;
      const a = recovered.filter((run) => backedOrMet(run, after)).length;
      return `<div class="ba-row">
        <div class="ba-label">${label}</div>
        <div class="ba-bars">
          <div class="ba-bar"><span class="ba-tag">first try</span><span class="hbar-track"><span class="hbar-fill" style="width:${pct(b, n)}%;background:var(--faint)"></span></span><span class="hbar-n">${b}/${n}</span></div>
          <div class="ba-bar"><span class="ba-tag">after fixes</span><span class="hbar-track"><span class="hbar-fill" style="width:${pct(a, n)}%;background:var(--accent)"></span></span><span class="hbar-n">${a}/${n}</span></div>
        </div>
      </div>`;
    })
    .join("")}<p class="chart-note">A \u201cI do not know\u201d has no answer to back, so it counts as not backed.</p></div>`;
}

// ---------- Answer quality across all judged runs ----------

function qualityOverview(runs) {
  const judged = runs.filter((run) => run.first_sufficient != null);
  if (!judged.length) return `<p class="chart-empty">No judged runs yet. Baseline and retrieve-only runs are not checked.</p>`;
  const n = judged.length;
  const count = (key) => judged.filter((run) => backedOrMet(run, key)).length;
  const abstained = judged.filter((run) => run.abstained).length;
  const meter = (label, hint, before, after) => `<div class="qo-row">
      <div class="qo-ask">${label}<small>${hint}</small></div>
      <div class="qo-bars">
        <div class="ba-bar"><span class="ba-tag">first try</span><span class="hbar-track"><span class="hbar-fill" style="width:${pct(before, n)}%;background:var(--faint)"></span></span><span class="hbar-n">${pct(before, n)}%</span></div>
        <div class="ba-bar"><span class="ba-tag">what the user got</span><span class="hbar-track"><span class="hbar-fill" style="width:${pct(after, n)}%;background:var(--accent)"></span></span><span class="hbar-n">${pct(after, n)}%</span></div>
      </div>
    </div>`;
  return `<div class="qo">
    ${meter("Found enough information", "The passages contained what the question needed.", count("first_sufficient"), count("final_sufficient"))}
    ${meter("Answer backed by the passages", "Every claim came from what it read.", count("first_supported"), count("final_supported"))}
    <p class="chart-note">Out of ${n} judged run${n === 1 ? "" : "s"}. An \u201cI do not know\u201d has no answer to back, so it counts as not backed${abstained ? ` (${abstained} run${abstained === 1 ? "" : "s"} ended that way)` : ""}. Open any run below to see the judge's reasons.</p>
  </div>`;
}

// ---------- Run timeline ----------

function timelineSvg(runs) {
  const barW = 14;
  const step = 20;
  const H = 150;
  const base = H - 18;
  const W = Math.max(640, runs.length * step + 50);
  const max = Math.max(1, ...runs.map((run) => run.latency_ms || 0));
  let bars = "";
  runs.forEach((run, index) => {
    const x = 40 + index * step;
    const h = run.latency_ms ? Math.max(3, ((base - 10) * run.latency_ms) / max) : 3;
    const outcome = outcomeKey(run);
    const color = run.abstained ? chartColor("abstained") : chartColor(outcome);
    const tip = `${run.query}\n${(OUTCOME_LABELS[outcome] || outcome)}${run.path.length ? ` · ${run.path.join(" → ")}` : ""}${run.abstained ? " · abstained" : ""}\n${run.latency_ms ? `${(run.latency_ms / 1000).toFixed(1)} s` : "no latency"}`;
    bars += `<rect class="tl-bar" data-chart-run="${chartEsc(run.run_id)}" x="${x}" y="${base - h}" width="${barW}" height="${h}" rx="2" style="fill:${color}"><title>${chartEsc(tip)}</title></rect>`;
    if (run.path.length) {
      bars += `<text x="${x + barW / 2}" y="${base + 12}" class="tl-steps">${run.path.length}</text>`;
    }
  });
  const axis = `<line x1="36" x2="${W - 6}" y1="${base}" y2="${base}" class="tl-axis"/><text x="32" y="16" class="tl-y">${(max / 1000).toFixed(1)}s</text><text x="32" y="${base}" class="tl-y">0</text>`;
  return `<svg class="chart-svg tl" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMinYMid meet" role="img" aria-label="Latency per run, oldest to newest">${axis}${bars}</svg>`;
}

// ---------- Run list with a diagram button per run ----------

function runTable(runs) {
  const rows = [...runs]
    .reverse()
    .map((run) => {
      const result = resultKey(run);
      const steps = run.path.length ? run.path.join(" → ") : run.status === "proposed" ? `proposed: ${run.proposed_action}` : "no fix";
      const when = run.timestamp ? window.ReliabilityView.formatWhen(run.timestamp) : "";
      return `<tr>
        <td class="rt-q" title="${chartEsc(run.query)}">${chartEsc(run.query)}</td>
        <td><span class="swatch" style="background:${chartColor(firstPassKey(run))}"></span>${firstPassKey(run) === "passed" ? "looked fine" : firstPassKey(run) === "flagged" ? "flagged" : "not judged"}</td>
        <td class="rt-steps">${chartEsc(steps)}</td>
        <td><span class="swatch" style="background:${chartColor(result)}"></span>${chartEsc(RESULT_LABELS[result] || result)}</td>
        <td class="rt-when">${chartEsc(when)}</td>
        <td><button type="button" class="ghost rt-open" data-chart-run="${chartEsc(run.run_id)}">View diagram</button></td>
      </tr>`;
    })
    .join("");
  return `<div class="rt-wrap"><table class="rt"><thead><tr><th>Question</th><th>First check</th><th>Fixes</th><th>Result</th><th>When</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

// ---------- Page ----------

function renderEvalOverview(root, payload, scoringProgress) {
  const runs = (payload && payload.runs) || [];
  if (!runs.length) {
    root.innerHTML = `<div class="empty">No runs for this system yet. Run a query in Test Console, then open Runs.</div>`;
    return;
  }
  const judged = runs.filter((run) => run.first_sufficient != null);
  const recovered = runs.filter((run) => run.path.length);
  const improved = recovered.filter((run) => run.verification === "improved").length;
  const abstained = runs.filter((run) => run.abstained).length;
  const flagged = judged.filter((run) => firstPassKey(run) === "flagged").length;
  const proposed = runs.filter((run) => run.status === "proposed").length;
  const latencies = runs.map((run) => run.latency_ms).filter((value) => value != null);
  const meanLatency = latencies.length ? latencies.reduce((a, b) => a + b, 0) / latencies.length : null;

  const kpi = (label, value, sub) =>
    `<div class="kpi"><div class="kpi-v">${value}</div><div class="kpi-l">${label}</div>${sub ? `<div class="kpi-s">${sub}</div>` : ""}</div>`;

  const outcomes = [...tally(recovered, (run) => run.verification || "none").entries()].sort((a, b) => b[1] - a[1]);
  const classes = [...tally(recovered, (run) => run.failure_class || "unattributed").entries()].sort((a, b) => b[1] - a[1]);
  const actionCounts = new Map();
  recovered.forEach((run) => run.path.forEach((action) => actionCounts.set(action, (actionCounts.get(action) || 0) + 1)));
  const actions = [...actionCounts.entries()].sort((a, b) => b[1] - a[1]);
  const paths = [...tally(recovered, (run) => run.path.join(" → ")).entries()].sort((a, b) => b[1] - a[1]);

  const card = (title, body, cls = "") =>
    `<section class="chart-card ${cls}"><h3>${title}</h3>${body}</section>`;
  const none = (text) => `<p class="chart-empty">${text}</p>`;

  root.innerHTML = `
    <div class="kpis">
      ${kpi("Runs", runs.length)}
      ${kpi("Flagged on first pass", flagged, judged.length ? `${pct(flagged, judged.length)}% of judged` : "no judge runs")}
      ${kpi("Recovered", recovered.length, proposed ? `${proposed} awaiting confirm` : "")}
      ${kpi("Improved", improved, recovered.length ? `${pct(improved, recovered.length)}% of recovered` : "")}
      ${kpi("Abstained", abstained, `${pct(abstained, runs.length)}% of runs`)}
      ${kpi("Mean latency", meanLatency == null ? "–" : `${(meanLatency / 1000).toFixed(1)}s`)}
    </div>
    ${card("Quality scores", metricsOverview(runs, scoringProgress), "wide metrics-card")}
    ${card("Judge's checks (what the loop acts on)", qualityOverview(runs), "wide")}
    ${card("How the loop handled these runs", loopSteps(runs), "wide")}
    ${card("What happened, split by the first check", outcomeByCheck(runs) + `<p class="chart-note">A run can look fine to the judge and still get a fix when retrieval scores were weak.</p>`, "wide")}
    <div class="chart-grid">
      ${card("Verification verdicts", recovered.length ? donutSvg(outcomes, "recovered") : none("No recovered runs yet."))}
      ${card("Did the fixes help? (fixed runs only)", recovered.length ? beforeAfter(recovered) : none("No recovered runs yet."))}
      ${card("Failure classes", classes.length ? hbars(classes, (key) => key.replaceAll("_", " ")) : none("No failures attributed yet."))}
      ${card("Recovery actions used", actions.length ? hbars(actions) + `<h4>Paths</h4>` + hbars(paths) : none("No recovery actions applied yet."))}
    </div>
    ${card("Runs over time", timelineSvg(runs) + `<p class="chart-note">Bar height is latency; color is the verdict (purple = abstained); the number under a bar is how many recovery steps ran. Click a bar to open its trace.</p>`, "wide")}
    ${card("Every run", runTable(runs), "wide")}
    <p class="chart-disclaimer">Quality here comes from the AI judge, which never sees the correct answers. It tells you whether answers were grounded in the documents, not whether they were right. Correctness against an answer key comes from the benchmark.</p>
  `;
}

// ---------- Single-run diagram ----------

function judgePill(label, value) {
  const tone = value === true ? "ok" : value === false ? "bad" : "na";
  const word = value === true ? "yes" : value === false ? "no" : "n/a";
  return `<span class="jp ${tone}">${label} <b>${word}</b></span>`;
}

function judgePills(evaluation, abstainedAnswer) {
  if (!evaluation) return `<span class="jp na">not judged</span>`;
  const backed = abstainedAnswer ? `<span class="jp na">no answer given</span>` : judgePill("answer backed", evaluation.answer_supported);
  return judgePill("enough info", evaluation.evidence_sufficient) + backed;
}

function verdictPill(outcome) {
  if (!outcome) return "";
  return `<span class="vp" style="--c:${chartColor(outcome)}">${chartEsc(OUTCOME_LABELS[outcome] || outcome)}</span>`;
}

function snippet(text, limit = 160) {
  const value = String(text || "").trim();
  if (!value) return "(no answer)";
  return value.length > limit ? `${value.slice(0, limit)}…` : value;
}

function uniqueDocs(chunks) {
  const seen = [];
  for (const chunk of chunks || []) {
    const name = chunk.title || chunk.doc_id;
    if (name && !seen.includes(name)) seen.push(name);
  }
  return seen;
}

function docChips(names, limit = 4) {
  const shown = names.slice(0, limit).map((name) => `<span class="doc-chip">${chartEsc(name)}</span>`).join("");
  const more = names.length > limit ? `<span class="doc-chip more">+${names.length - limit}</span>` : "";
  return `<div class="doc-chips">${shown}${more}</div>`;
}

function runNode(kicker, title, body, tone) {
  return `<div class="rn" style="--c:${chartColor(tone)}"><div class="rn-k">${kicker}</div><div class="rn-t">${title}</div>${body}</div>`;
}

function attemptDetail(attempt) {
  if (attempt.executed === false) return "Selected, not executed";
  const params = attempt.parameters || {};
  if (attempt.action === "rewrite") {
    return attempt.rewritten_query ? `New search: \u201c${chartEsc(snippet(attempt.rewritten_query, 120))}\u201d` : "Rewrote the search query";
  }
  if (attempt.action === "expand") {
    return params.from_k && params.to_k ? `Searched wider: ${params.from_k} → ${params.to_k} chunks` : `Searched wider (top_k ${attempt.top_k})`;
  }
  if (attempt.action === "regenerate") return "Rewrote the answer from the same evidence";
  if (attempt.action === "abstain") return "Stopped and said \u201cI do not know\u201d";
  return chartEsc(attempt.action || "");
}

function runAttempts(trace) {
  const version = trace && trace.trace_schema_version;
  if (typeof version === "number" && Number.isInteger(version) && version > 2) return [];
  const attempts = (trace.recovery_attempts || []).filter((item) => item && item.action);
  if (attempts.length) return attempts;
  const recovery = trace.recovery || {};
  if (trace.recovery_status === "proposed" || !recovery.action || recovery.action === "accept") return [];
  return [
    {
      action: recovery.action,
      top_k: trace.top_k,
      parameters: recovery.parameters,
      rewritten_query: trace.rewritten_query,
      retrieved_doc_ids: (trace.retrieved_chunks || []).map((chunk) => chunk.doc_id),
      verification: trace.verification,
      outcome_note: recovery.outcome_note,
    },
  ];
}

function passageList(chunks, highlight, limit = 8) {
  if (!chunks.length) return `<p class="chart-empty">Nothing was retrieved.</p>`;
  const max = Math.max(0.0001, ...chunks.map((chunk) => chunk.score || 0));
  const row = (chunk, index) => {
    const isNew = highlight && highlight.has(chunk.chunk_id);
    const part = String(chunk.chunk_id || "").split("::").pop();
    const tip = `Rank ${index + 1} · similarity ${(chunk.score || 0).toFixed(3)} · passage ${part}`;
    return `<details class="pg${isNew ? " new" : ""}">
      <summary>
        <span class="pg-head"><span class="pg-rank">${index + 1}</span><span class="pg-doc">${chartEsc(chunk.title || chunk.doc_id || "unknown")}</span>${isNew ? `<span class="pg-new">new</span>` : ""}<span class="pg-bar" title="${chartEsc(tip)}"><span style="width:${(100 * (chunk.score || 0)) / max}%"></span></span></span>
        <span class="pg-snip">\u201c${chartEsc(snippet(chunk.text, 110))}\u201d</span>
      </summary>
      <div class="pg-text">${chartEsc(chunk.text || "")}</div>
    </details>`;
  };
  const shown = chunks.slice(0, limit).map(row).join("");
  const rest = chunks.length > limit
    ? `<details class="pg-more"><summary>Show ${chunks.length - limit} more</summary>${chunks.slice(limit).map((chunk, i) => row(chunk, i + limit)).join("")}</details>`
    : "";
  return `<div class="pgs">${shown}${rest}</div>`;
}

// ---------- Quality scores: faithfulness, answer relevance, context relevance ----------

const METRICS = [
  { key: "faithfulness", name: "Faithfulness", hint: "How much of the answer is backed by the passages." },
  { key: "answer_relevance", name: "Answer relevance", hint: "How directly the answer addresses the question." },
  { key: "context_relevance", name: "Context relevance", hint: "How many of the passages it read were actually useful." },
];

function metricTone(value) {
  if (value == null) return "na";
  return value >= 0.8 ? "ok" : value >= 0.5 ? "warn" : "bad";
}

function metricText(value) {
  return value == null ? "–" : `${Math.round(value * 100)}%`;
}

function metricTile(metric, value, { firstValue = null, showFirst = false, emptyNote = "", note = "" } = {}) {
  const tone = metricTone(value);
  const first = showFirst
    ? `<div class="mt-first">first try <b>${firstValue == null ? "no answer" : metricText(firstValue)}</b> → after fixes <b>${metricText(value)}</b></div>`
    : note
      ? `<div class="mt-first">${chartEsc(note)}</div>`
      : "";
  return `<div class="mt ${tone}">
    <div class="mt-name">${metric.name}</div>
    <div class="mt-v">${metricText(value)}</div>
    <div class="mt-meter"><span style="width:${value == null ? 0 : Math.round(value * 100)}%"></span></div>
    <div class="mt-hint">${value == null && emptyNote ? chartEsc(emptyNote) : metric.hint}</div>
    ${first}
  </div>`;
}

function claimList(scored, chunks) {
  const claims = (scored && scored.claims) || [];
  if (!claims.length) return "";
  const rank = new Map(chunks.map((chunk, index) => [chunk.chunk_id, { index: index + 1, title: chunk.title || chunk.doc_id }]));
  const rows = claims
    .map((claim) => {
      const source = claim.chunk_id && rank.get(claim.chunk_id);
      const where = claim.supported
        ? source ? `found in passage ${source.index} (${chartEsc(source.title)})` : "backed by the passages"
        : "not found in the passages";
      return `<li class="${claim.supported ? "ok" : "bad"}"><span class="cl-mark">${claim.supported ? "✓" : "✗"}</span><span class="cl-text">${chartEsc(claim.claim)}</span><span class="cl-where">${where}</span></li>`;
    })
    .join("");
  return `<h4>What the answer claims</h4><ul class="claims">${rows}</ul>`;
}

function metricsCard(entry, { recovered, abstained, finalChunks, hasAnswer }) {
  const head = `<h3>Quality scores</h3>`;
  if (!hasAnswer) {
    return `<section class="chart-card metrics-card">${head}<p class="chart-empty">Retrieve-only runs have no answer to score.</p></section>`;
  }
  if (!entry || entry.status === "loading") {
    return `<section class="chart-card metrics-card">${head}<p class="chart-empty"><span class="spinner"></span> Scoring this run… (one extra model call, a few seconds)</p></section>`;
  }
  if (entry.status === "error") {
    return `<section class="chart-card metrics-card">${head}<p class="chart-empty">Could not score this run: ${chartEsc(entry.error)}</p><button type="button" class="ghost" data-score-run>Try again</button></section>`;
  }
  const saved = entry.data || {};
  const final = saved.final || {};
  const first = recovered ? saved.first : null;
  const emptyFor = (key) => {
    if (abstained && key !== "context_relevance") return "It said it does not know, so there is no answer to score.";
    if (key === "faithfulness" && !(final.claims || []).length) return "The answer makes no factual claims to check.";
    return "";
  };
  const tiles = METRICS.map((metric) =>
    metricTile(metric, final[metric.key], {
      firstValue: first ? first[metric.key] : null,
      showFirst: Boolean(first),
      emptyNote: emptyFor(metric.key),
    }),
  ).join("");
  const when = saved.scored_at ? window.ReliabilityView.formatWhen(saved.scored_at) : "";
  return `<section class="chart-card metrics-card">
    ${head}
    <div class="mts">${tiles}</div>
    ${claimList(final, finalChunks)}
    <div class="mt-foot">
      <p class="chart-note">Scored by ${chartEsc(saved.model || "an AI model")} after the run${when ? ` (${chartEsc(when)} UTC)` : ""}. It reads the question, the passages and the answer, never the correct answer. The loop does not use these scores, and they have not been checked against human ratings yet.</p>
      <button type="button" class="ghost" data-score-run>Score again</button>
    </div>
  </section>`;
}

function metricsOverview(runs, progress) {
  const answered = runs.filter((run) => run.has_answer);
  const scored = runs.filter((run) => run.quality);
  const missing = answered.length - scored.length;
  const mean = (key) => {
    const values = scored.map((run) => run.quality[key]).filter((value) => value != null);
    return values.length ? { value: values.reduce((a, b) => a + b, 0) / values.length, n: values.length } : { value: null, n: 0 };
  };
  const button = progress
    ? `<span class="chart-note"><span class="spinner"></span> Scoring ${progress.done} of ${progress.total}…</span>`
    : missing > 0
      ? `<button type="button" class="ghost" data-score-all>Score ${missing} unscored run${missing === 1 ? "" : "s"}</button>`
      : "";
  if (!scored.length) {
    return `<p class="chart-empty">No runs scored yet. Open a run to score it, or score them all at once (one model call per run).</p>${button}`;
  }
  const tiles = METRICS.map((metric) => {
    const { value, n } = mean(metric.key);
    return metricTile(metric, value, { note: `average of ${n} run${n === 1 ? "" : "s"}` });
  }).join("");
  return `<div class="mts">${tiles}</div>
    <div class="mt-foot"><p class="chart-note">Averages over ${scored.length} scored run${scored.length === 1 ? "" : "s"}, using the answer the user got. Runs that said \u201cI do not know\u201d have no faithfulness or answer-relevance score and are left out of those two averages. These averages are model scores. The loop does not use them, and a person has not checked them against human ratings.</p>${button}</div>`;
}

// ---------- Quality check: the judge's verdicts in plain words ----------

function verdictBadge(value, abstainedAnswer) {
  if (abstainedAnswer) return `<span class="qv na">No answer given</span>`;
  if (value === true) return `<span class="qv ok">Yes</span>`;
  if (value === false) return `<span class="qv bad">No</span>`;
  return `<span class="qv na">Not checked</span>`;
}

function searchClarity(signal) {
  if (!signal || signal.top_score == null) return null;
  if (signal.weak_top) {
    return { tone: "bad", word: "Weak", why: "Even the best passage was a poor match for the question, so the answer may not be in these documents." };
  }
  if (signal.ambiguous_top) {
    return { tone: "warn", word: "Close call", why: "The top two passages matched the question almost equally, so the search could not tell which one is the right source." };
  }
  return { tone: "ok", word: "Clear", why: "The best passage stood out from the rest." };
}

function qualityCard({ trace, firstEval, finalEval, recovered, abstained, firstAbstained }) {
  const why = (text, firstText) =>
    `<div class="q-why">${text ? chartEsc(text) : `<span class="faint">No reason recorded.</span>`}${recovered && firstText && firstText !== text ? `<div class="q-why-first">First try: ${chartEsc(firstText)}</div>` : ""}</div>`;
  const cols = (first, final) => (recovered ? `<div>${first}</div><div>${final}</div>` : `<div>${final}</div>`);

  const rows = [];
  if (firstEval || finalEval) {
    rows.push(`<div class="q-row">
      <div class="q-ask">Did it find enough information?<small>Do the passages contain what the question needs?</small></div>
      ${cols(verdictBadge(firstEval && firstEval.evidence_sufficient), verdictBadge(finalEval && finalEval.evidence_sufficient))}
      ${why(finalEval && finalEval.sufficiency_rationale, firstEval && firstEval.sufficiency_rationale)}
    </div>`);
    rows.push(`<div class="q-row">
      <div class="q-ask">Is the answer backed by the passages?<small>Every claim in the answer should come from what it read.</small></div>
      ${cols(verdictBadge(firstEval && firstEval.answer_supported, firstAbstained), verdictBadge(finalEval && finalEval.answer_supported, abstained))}
      ${why(abstained ? "It said it does not know, so there was no answer to check." : finalEval && finalEval.support_rationale, firstEval && firstEval.support_rationale)}
    </div>`);
  }
  const clarity = searchClarity(trace.retrieval_signal);
  if (clarity) {
    const badge = `<span class="qv ${clarity.tone}">${clarity.word}</span>`;
    rows.push(`<div class="q-row">
      <div class="q-ask">How clear was the search?<small>Measured on the first search, from match scores alone.</small></div>
      ${recovered ? `<div>${badge}</div><div class="faint">–</div>` : `<div>${badge}</div>`}
      <div class="q-why">${chartEsc(clarity.why)}</div>
    </div>`);
  }
  if (!rows.length) {
    return `<section class="chart-card quality-card"><h3>Judge's checks</h3><p class="chart-empty">This run was not judged (baseline or retrieve-only mode).</p></section>`;
  }
  const judge = (finalEval || firstEval || {}).model;
  return `<section class="chart-card quality-card">
    <h3>Judge's checks <span class="h-sub">what the loop acts on</span></h3>
    <div class="q-grid${recovered ? "" : " single"}">
      <div class="q-row q-head"><div></div>${recovered ? "<div>First try</div><div>After fixes</div>" : "<div>Result</div>"}<div>Why</div></div>
      ${rows.join("")}
    </div>
    <p class="chart-note">Checked by an AI judge${judge ? ` (${chartEsc(judge)})` : ""} that reads the question, the passages and the answer. It never sees the correct answer, so these are grounding checks, not a correctness score.</p>
  </section>`;
}

const DOC_PALETTE = ["var(--c-blue)", "var(--c-pass)", "var(--c-flag)", "var(--c-fail)", "var(--c-violet)", "var(--c-cyan)", "var(--c-orange)", "var(--c-slate)"];

function ring(slices, centerTop, centerSub, size = 120) {
  const total = slices.reduce((sum, slice) => sum + slice.count, 0);
  const c = size / 2;
  const R = c - 4;
  const r = R - 16;
  let angle = -Math.PI / 2;
  const point = (rad, radius) => `${c + radius * Math.cos(rad)},${c + radius * Math.sin(rad)}`;
  const arcs = slices
    .filter((slice) => slice.count > 0)
    .map((slice, _, shown) => {
      const title = `<title>${chartEsc(`${slice.label}: ${slice.count}`)}</title>`;
      if (shown.length === 1) {
        return `<circle cx="${c}" cy="${c}" r="${(R + r) / 2}" fill="none" style="stroke:${slice.color}" stroke-width="${R - r}">${title}</circle>`;
      }
      const sweep = (slice.count / total) * Math.PI * 2;
      const end = angle + sweep;
      const large = sweep > Math.PI ? 1 : 0;
      const d = `M${point(angle, R)} A${R},${R} 0 ${large} 1 ${point(end, R)} L${point(end, r)} A${r},${r} 0 ${large} 0 ${point(angle, r)} Z`;
      angle = end;
      return `<path d="${d}" style="fill:${slice.color}">${title}</path>`;
    })
    .join("");
  const track = total ? "" : `<circle cx="${c}" cy="${c}" r="${(R + r) / 2}" fill="none" style="stroke:var(--c-track)" stroke-width="${R - r}"/>`;
  return `<svg class="ring" viewBox="0 0 ${size} ${size}" role="img" aria-label="${chartEsc(centerSub)}">${track}${arcs}<text x="${c}" y="${c + 2}" class="ring-n${String(centerTop).length > 4 ? " small" : ""}">${chartEsc(centerTop)}</text><text x="${c}" y="${c + 18}" class="ring-sub">${chartEsc(centerSub)}</text></svg>`;
}

function ringLegend(slices) {
  return `<ul class="legend">${slices
    .filter((slice) => slice.count > 0)
    .map((slice) => `<li><span class="swatch" style="background:${slice.color}"></span><span class="step-l">${chartEsc(slice.label)}</span><b>${slice.count}</b></li>`)
    .join("")}</ul>`;
}

function checksPassed(evaluation) {
  if (!evaluation) return null;
  return [evaluation.evidence_sufficient === true, evaluation.answer_supported === true].filter(Boolean).length;
}

function checksRing(evaluation, label, abstainedFinal) {
  const passed = checksPassed(evaluation);
  if (passed == null) return ring([], "–", label);
  if (abstainedFinal) {
    const sufficient = evaluation.evidence_sufficient === true;
    return ring(
      [
        { label: sufficient ? "evidence enough" : "evidence still not enough", count: 1, color: sufficient ? "var(--c-pass)" : "var(--c-fail)" },
        { label: "no answer to check", count: 1, color: "var(--c-violet)" },
      ],
      "no answer",
      label,
      110,
    );
  }
  const color = passed === 2 ? "var(--c-pass)" : passed === 1 ? "var(--c-flag)" : "var(--c-fail)";
  return ring(
    [
      { label: "checks passed", count: passed, color },
      { label: "failed", count: 2 - passed, color: "var(--c-track)" },
    ],
    `${passed}/2`,
    label,
    110,
  );
}

function runCircles({ firstEval, finalEval, recovered, firstChunks, finalChunks, added, abstained, firstAbstained }) {
  const checks = `<section class="chart-card circle-card"><h3>Quality checks passed</h3>
    <div class="rings">${checksRing(firstEval, "first try", recovered ? firstAbstained : abstained)}${recovered ? `<span class="rn-arrow">→</span>${checksRing(finalEval, "after fixes", abstained)}` : ""}</div>
    <p class="chart-note">Out of the two checks above: enough information, and answer backed by the passages.${abstained || firstAbstained ? " Purple means it said it does not know, so there was no answer to check." : ""}</p></section>`;

  let evidence = "";
  if (recovered && added) {
    const finalIds = new Set(finalChunks.map((chunk) => chunk.chunk_id));
    const kept = finalChunks.length - added.size;
    const dropped = firstChunks.filter((chunk) => !finalIds.has(chunk.chunk_id)).length;
    const slices = [
      { label: "kept from first try", count: kept, color: "var(--c-none)" },
      { label: "new from the fixes", count: added.size, color: "var(--c-blue)" },
    ];
    evidence = `<section class="chart-card circle-card"><h3>Passages after the fixes</h3>
      <div class="rings">${ring(slices, String(finalChunks.length), "passages")}${ringLegend(slices)}</div>
      ${dropped ? `<p class="chart-note">${dropped} passage${dropped === 1 ? "" : "s"} from the first try dropped out.</p>` : ""}</section>`;
  }

  const byDoc = tally(finalChunks, (chunk) => chunk.title || chunk.doc_id || "unknown");
  const docSlices = [...byDoc.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([label, count], index) => ({ label, count, color: DOC_PALETTE[index % DOC_PALETTE.length] }));
  const docs = `<section class="chart-card circle-card"><h3>Where the ${recovered ? "final " : ""}passages came from</h3>
    <div class="rings">${ring(docSlices, String(docSlices.length), docSlices.length === 1 ? "document" : "documents")}${ringLegend(docSlices)}</div></section>`;

  return `<div class="run-circles">${checks}${evidence}${docs}</div>`;
}

function renderRunDiagram(root, trace, quality) {
  if (!trace) {
    root.innerHTML = "";
    return;
  }
  const attempts = runAttempts(trace);
  const recovered = attempts.length > 0;
  const proposed = trace.recovery_status === "proposed" ? (trace.recovery || {}).action : null;
  const firstEval = trace.first_pass_evaluation || (recovered ? null : trace.runtime_evaluation);
  const firstChunks = trace.previous_retrieved_chunks || trace.retrieved_chunks || [];
  const finalChunks = trace.retrieved_chunks || [];
  const firstAnswer = recovered && trace.previous_answer != null ? trace.previous_answer : trace.answer;
  const firstFine = firstEval && firstEval.evidence_sufficient && firstEval.answer_supported !== false;
  const saysUnknown = (text) => String(text || "").trim().toLowerCase().startsWith("i do not know");
  const abstained = saysUnknown(trace.answer);
  const firstAbstained = saysUnknown(firstAnswer);
  const arrow = `<div class="rn-arrow" aria-hidden="true">→</div>`;

  const nodes = [
    runNode("Question", chartEsc(snippet(trace.query, 140)), "", "none"),
    runNode(
      "Step 1 · first try",
      `Read ${firstChunks.length} passage${firstChunks.length === 1 ? "" : "s"}`,
      `${docChips(uniqueDocs(firstChunks))}<div class="rn-a">\u201c${chartEsc(snippet(firstAnswer))}\u201d</div><div class="rn-pills">${judgePills(firstEval, firstAbstained)}</div>`,
      firstEval == null ? "none" : firstFine ? "passed" : "flagged",
    ),
  ];
  attempts.forEach((attempt, index) => {
    const outcome = attempt.verification && attempt.verification.outcome;
    const docs = [...new Set(attempt.retrieved_doc_ids || [])];
    nodes.push(
      runNode(
        `Fix ${index + 1}`,
        chartEsc(attempt.action),
        `<div class="rn-d">${attemptDetail(attempt)}</div>${docs.length && attempt.action !== "abstain" ? `<div class="rn-d faint">${docs.length} document${docs.length === 1 ? "" : "s"} in view</div>` : ""}<div class="rn-pills">${verdictPill(outcome)}</div>${attempt.outcome_note ? `<div class="rn-d faint">${chartEsc(attempt.outcome_note)}</div>` : ""}`,
        attempt.action,
      ),
    );
  });
  if (proposed) {
    nodes.push(runNode("Proposed fix", chartEsc(proposed), `<div class="rn-d">Waiting for you to confirm it below.</div>`, "proposed"));
  }
  const finalOutcome = recovered ? trace.verification && trace.verification.outcome : null;
  nodes.push(
    runNode(
      "Result",
      abstained ? "Said \u201cI do not know\u201d" : recovered ? "Answer after fixes" : proposed ? "Current answer" : "Kept the first answer",
      `<div class="rn-a">\u201c${chartEsc(snippet(trace.answer))}\u201d</div>${recovered ? `<div class="rn-pills">${judgePills(trace.runtime_evaluation, abstained)}</div><div class="rn-pills">${verdictPill(finalOutcome)}</div>` : ""}${trace.latency_ms ? `<div class="rn-d faint">${(trace.latency_ms / 1000).toFixed(1)} s total</div>` : ""}`,
      abstained ? "abstained" : finalOutcome || (firstFine ? "accepted" : "none"),
    ),
  );

  const firstIds = new Set(firstChunks.map((chunk) => chunk.chunk_id));
  const added = recovered ? new Set(finalChunks.filter((chunk) => !firstIds.has(chunk.chunk_id)).map((chunk) => chunk.chunk_id)) : null;
  const firstDocs = uniqueDocs(firstChunks);
  const finalDocs = uniqueDocs(finalChunks);
  const changedEvidence = recovered && trace.previous_retrieved_chunks;

  const evidence = changedEvidence
    ? `<div class="run-charts">
        <section class="chart-card"><h3>What it read on the first try</h3>${passageList(firstChunks)}</section>
        <section class="chart-card"><h3>What it read after the fixes</h3>${passageList(finalChunks, added)}<p class="chart-note">${added.size} passage${added.size === 1 ? "" : "s"} marked <b>new</b> came from the fixes. Documents: ${firstDocs.length} → ${finalDocs.length}.</p></section>
      </div>`
    : `<div class="run-charts one"><section class="chart-card"><h3>What it read</h3>${passageList(finalChunks)}</section></div>`;

  const finalEval = recovered ? trace.runtime_evaluation : firstEval;
  root.innerHTML = `
    <div class="run-flow">${nodes.join(arrow)}</div>
    ${metricsCard(quality, { recovered, abstained, finalChunks, hasAnswer: Boolean(String(trace.answer || "").trim()) })}
    ${qualityCard({ trace, firstEval, finalEval, recovered, abstained, firstAbstained })}
    ${runCircles({ firstEval, finalEval, recovered, firstChunks, finalChunks, added, abstained, firstAbstained })}
    ${evidence}
    <p class="chart-note">Passages are ranked by how closely their wording matches the question; a longer bar is a closer match. That is how the search ranks them, not a quality score. Click a passage to read it.</p>
  `;
}

function renderQualityBoard(root, payload, scoringProgress) {
  const runs = (payload && payload.runs) || [];
  const note = `<p class="rel-note">Runtime verification determines whether recovery changed the runtime judge state. Post-hoc quality scores are separate model-generated analysis and do not influence recovery decisions.</p>`;
  if (!runs.length) {
    root.innerHTML = `${note}<p class="chart-empty">No runs for this system yet. Run a test in Test Console, then score it here.</p>`;
    return;
  }
  const rows = runs
    .map((run) => {
      const status = window.ReliabilityView
        ? ReliabilityView.qualityStatus(run)
        : run.quality
          ? "Scored"
          : "Not scored";
      const scores = status === "Scored"
        ? METRICS.map((metric) => {
            const value = run.quality[metric.key];
            return `${metric.name} ${value == null ? "—" : metricText(value)}`;
          }).join(" · ")
        : "";
      const scoreButton = status === "Not scored"
        ? `<button type="button" class="ghost" data-score-run-id="${chartEsc(run.run_id)}">Score</button>`
        : "";
      return `<tr>
        <td>${chartEsc(run.query || "(empty)")}</td>
        <td>${chartEsc(status)}</td>
        <td>${chartEsc(scores)}</td>
        <td>${scoreButton}<button type="button" class="ghost" data-chart-run="${chartEsc(run.run_id)}">Inspect</button></td>
      </tr>`;
    })
    .join("");
  root.innerHTML = `${note}
    ${metricsOverview(runs, scoringProgress)}
    <table class="rel-table">
      <thead><tr><th>Question</th><th>Quality</th><th>Scores</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}
