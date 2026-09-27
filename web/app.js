const state = {
  meta: null,
  corpora: [],
  traces: [],
  selectedId: null,
  trace: null,
  steps: [],
  selectedStep: null,
  selectedChunkId: null,
  childRunId: null,
  loading: false,
  recovering: false,
  view: "playground",
  documents: [],
  messages: [],
  inspectCollapsed: false,
  navCollapsed: false,
  uploads: [],
  draftConfig: { instructions: "", chat_model: "gpt-4o-mini", top_k: 4 },
  keys: [],
  revealedKey: null,
};

const CHAT_MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"];

const ACTION_LABELS = {
  regenerate: "Regenerate from evidence",
  rewrite: "Rewrite query and retrieve",
  expand: "Widen retrieval (higher top_k)",
  abstain: "Abstain",
  accept: "Keep first-pass answer",
};

const V1_ACTIONS = ["regenerate", "rewrite", "expand", "abstain", "accept"];

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function showError(message) {
  ["error-banner", "pg-error"].forEach((id) => {
    const banner = $(id);
    if (!banner) return;
    if (!message) {
      banner.classList.add("hidden");
      banner.textContent = "";
      return;
    }
    banner.textContent = message;
    banner.classList.remove("hidden");
  });
}

const VIEWS = ["playground", "knowledge", "agent", "evaluation", "api"];

function currentView() {
  const hash = location.hash.replace("#", "");
  return VIEWS.includes(hash) ? hash : "playground";
}

function applyView() {
  state.view = currentView();
  const app = document.getElementById("app");
  app.dataset.view = state.view;
  app.classList.toggle("inspect-collapsed", state.inspectCollapsed);
  app.classList.toggle("nav-collapsed", state.navCollapsed);
  document.querySelectorAll(".view-link").forEach((link) => {
    const view = (link.getAttribute("href") || "").replace("#", "");
    link.classList.toggle("active", view === state.view);
  });
  const collapse = $("pg-collapse");
  if (collapse) collapse.textContent = state.inspectCollapsed ? "Show inspector" : "Collapse";
  const navCollapse = $("nav-collapse");
  if (navCollapse) {
    const label = state.navCollapsed ? "Expand sidebar" : "Collapse sidebar";
    navCollapse.setAttribute("aria-label", label);
    navCollapse.title = label;
  }
}

async function api(path, options) {
  const response = await fetch(path, options);
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail = payload && payload.detail ? payload.detail : `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

async function loadMeta() {
  state.meta = await api("/api/meta");
  const official = state.meta.official_openai ? "OpenAI" : "custom backend";
  const key = state.meta.api_key_present ? "key on" : "no key";
  const docs = state.meta.doc_count != null ? `${state.meta.doc_count} docs` : "";
  const industry = state.meta.corpus_industry ? `${state.meta.corpus_industry} · ` : "";
  $("top-meta").textContent =
    `${industry}${docs} · ${state.meta.configured_chat_model} · ${official} · ${key}`.replace(
      /^ · /,
      ""
    );
  const sub = $("brand-sub");
  if (sub) sub.textContent = state.meta.corpus_label || "Workspace";
  if (!state.meta.api_key_present) {
    $("mode").value = "retrieve_only";
    if ($("pg-mode")) $("pg-mode").value = "retrieve_only";
  }
  syncDraftConfig();
  renderExamples();
}

async function loadCorpora() {
  const payload = await api("/api/corpora");
  state.corpora = payload.corpora || [];
  const select = $("corpus");
  const active = payload.active_id || (state.meta && state.meta.corpus_id) || "";
  const groups = [];
  const seen = new Set();
  state.corpora.forEach((item) => {
    const group = item.group || "Other";
    if (!seen.has(group)) {
      seen.add(group);
      groups.push(group);
    }
  });
  select.innerHTML = groups
    .map((group) => {
      const options = state.corpora
        .filter((item) => (item.group || "Other") === group)
        .map((item) => {
          const selected = item.id === active ? " selected" : "";
          return `<option value="${escapeHtml(item.id)}"${selected}>${escapeHtml(item.label)}</option>`;
        })
        .join("");
      return `<optgroup label="${escapeHtml(group)}">${options}</optgroup>`;
    })
    .join("");
}

function renderExamples() {
  const examples = (state.meta && state.meta.examples) || [];
  $("example-chips").innerHTML = examples
    .map(
      (question) =>
        `<button type="button" class="chip" data-q="${escapeHtml(question)}">${escapeHtml(question)}</button>`
    )
    .join("");
}

async function switchCorpus(corpusId) {
  if (!corpusId || (state.meta && corpusId === state.meta.corpus_id)) return;
  showError("");
  $("corpus").disabled = true;
  try {
    await api("/api/corpus", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: corpusId }),
    });
    clearSelection();
    state.messages = [];
    state.uploads = [];
    await loadMeta();
    await loadCorpora();
    await loadTraces();
    await loadDocuments().catch(() => {
      state.documents = [];
    });
    state.revealedKey = null;
    await loadKeys();
    if (state.traces.length) {
      await selectRun(state.traces[0].run_id);
    } else {
      render();
    }
    renderPlaygroundKnowledge();
  } finally {
    $("corpus").disabled = false;
  }
}

function pill(kind, label) {
  if (!label) return "";
  return `<span class="pill ${escapeHtml(kind || "")}">${escapeHtml(label)}</span>`;
}

function renderRunList() {
  const deleteAll = $("delete-all-runs");
  if (deleteAll) {
    deleteAll.disabled = !state.traces.length;
  }
  const root = $("run-list");
  if (!state.traces.length) {
    root.innerHTML =
      `<div class="empty"><strong>No runs yet</strong>Ask a question to write a trace. Existing files under experiments/output also appear here.</div>`;
    return;
  }
  root.innerHTML = state.traces
    .map((item) => {
      const active = item.run_id === state.selectedId ? " active" : "";
      const child = item.parent_run_id ? " child-run" : "";
      const when = (item.timestamp || "").replace("T", " ").slice(0, 19);
      return `<div class="run-item${active}${child}" data-id="${escapeHtml(item.run_id)}">
        <button type="button" class="run-select">
          <div class="q">${escapeHtml(item.query || "(no query)")}</div>
          <div class="meta">
            ${pill(item.action, item.action)}
            ${item.recovery_status === "proposed" ? pill("warn", "proposed") : ""}
            ${item.child_run_id ? pill("ok", "has recovery") : ""}
            ${item.parent_run_id ? pill("ok", "after recovery") : ""}
            ${pill(item.verification, item.verification)}
            <span>${escapeHtml(when)}</span>
          </div>
        </button>
        <button type="button" class="run-delete" data-id="${escapeHtml(item.run_id)}" aria-label="Delete run" title="Delete run">×</button>
      </div>`;
    })
    .join("");
}

function knownChunkIds() {
  const ids = new Set();
  const trace = state.trace || {};
  (trace.retrieved_chunks || []).forEach((chunk) => {
    if (chunk && chunk.chunk_id) ids.add(chunk.chunk_id);
  });
  (trace.previous_retrieved_chunks || []).forEach((chunk) => {
    if (chunk && chunk.chunk_id) ids.add(chunk.chunk_id);
  });
  return ids;
}

function looksLikeChunkId(token) {
  return /^\S+::c\d+$/.test(token);
}

function formatAnswerHtml(text, preferredPass) {
  const value = text || "";
  if (!value) return { html: "", missing: [] };
  const ids = knownChunkIds();
  const token = /\[([^\[\]]+)\]/g;
  let cursor = 0;
  let html = "";
  const missing = [];
  let match;
  while ((match = token.exec(value))) {
    if (match.index > cursor) {
      html += escapeHtml(value.slice(cursor, match.index));
    }
    const chunkId = match[1];
    const raw = match[0];
    if (ids.has(chunkId)) {
      const active = chunkId === state.selectedChunkId ? " active" : "";
      const passAttr = preferredPass
        ? ` data-cite-pass="${escapeHtml(preferredPass)}"`
        : "";
      html += `<button type="button" class="cite${active}" data-chunk-id="${escapeHtml(chunkId)}"${passAttr} aria-label="Open chunk ${escapeHtml(chunkId)}">${escapeHtml(raw)}</button>`;
    } else if (looksLikeChunkId(chunkId)) {
      html += `<span class="cite-missing" title="not in this retrieve">${escapeHtml(raw)}</span>`;
      if (!missing.includes(chunkId)) missing.push(chunkId);
    } else {
      html += escapeHtml(raw);
    }
    cursor = match.index + match[0].length;
  }
  if (cursor < value.length) {
    html += escapeHtml(value.slice(cursor));
  }
  return { html, missing };
}

function missingCitationNote(missing) {
  if (!missing.length) return "";
  const labels = missing.map((id) => `[${id}]`).join(", ");
  return `<div class="answer-meta">Not in this retrieve: ${escapeHtml(labels)}</div>`;
}

function answerBlock(text, preferredPass) {
  const parsed = formatAnswerHtml(text, preferredPass);
  return `<div class="answer-block">${parsed.html}</div>${missingCitationNote(parsed.missing)}`;
}

function renderAnswer() {
  const bar = $("answer-bar");
  if (!state.trace) {
    bar.classList.add("hidden");
    return;
  }
  bar.classList.remove("hidden");
  $("answer-run-id").textContent = state.trace.run_id || "";
  const after = (state.trace.answer || "").trim() || "(no generated answer)";
  const before = (state.trace.previous_answer || "").trim();
  const rewritten = (state.trace.rewritten_query || "").trim();
  const firstChunks = (state.trace.previous_retrieved_chunks || []).length;
  const action = state.trace.recovery && state.trace.recovery.action;
  const outcome = state.trace.verification && state.trace.verification.outcome;
  const recovered = Boolean(before || rewritten || firstChunks || action === "expand");
  const attempts = ((state.trace && state.trace.recovery_attempts) || [])
    .map((item) => item && item.action)
    .filter(Boolean);
  const attemptLine =
    attempts.length > 1
      ? `<div class="answer-meta">Attempts: ${escapeHtml(attempts.join(" → "))}</div>`
      : "";
  if (!recovered) {
    $("answer-text").innerHTML = answerBlock(after);
    return;
  }
  const rewriteLine = rewritten
    ? `<div class="answer-meta">Rewritten query: ${escapeHtml(rewritten)}</div>`
    : "";
  const sameNote =
    before && after === before
      ? `<div class="answer-meta">Before and after are the same text. Recovery did not change the answer.</div>`
      : "";
  const beforeColumn = before
    ? `<div>
        <div class="answer-label">Before</div>
        ${answerBlock(before, "first")}
      </div>`
    : "";
  $("answer-text").innerHTML = `<div class="answer-pills">${pill(action, action)}${pill(outcome, outcome)}</div>
    ${rewriteLine}
    ${attemptLine}
    ${sameNote}
    <div class="answer-split">
      ${beforeColumn}
      <div>
        <div class="answer-label">${before ? "After" : "Answer"}</div>
        ${answerBlock(after, before ? "after_recovery" : null)}
      </div>
    </div>`;
}

function proposedAction() {
  const recovery = (state.trace && state.trace.recovery) || {};
  return recovery.action || "";
}

function recoverMarkup() {
  const status = state.trace && state.trace.recovery_status;
  const action = proposedAction();
  const canPropose = Boolean(state.trace && status === "proposed" && action && action !== "accept");
  if (!canPropose) return "";
  const recovery = (state.trace && state.trace.recovery) || {};
  const diagnosis = (state.trace && state.trace.diagnosis) || {};
  const klass = diagnosis.failure_class;
  const rationale = diagnosis.rationale || "";
  let note = rationale;
  if (recovery.trigger === "retrieval_signal") {
    note = recovery.reason || "Retrieval looks unreliable even though the judge accepted.";
  } else if (klass) {
    note = rationale ? `${klass} — ${rationale}` : klass;
  } else if (action === "expand") {
    note =
      rationale ||
      "Widen top_k and retrieve again. Same question, more neighbours.";
  } else if (action === "rewrite") {
    note =
      rationale ||
      "First-pass evidence is insufficient. Rewrite splits retrieval miss from corpus gap.";
  } else if (!note) {
    note = "No failure class on this pass.";
  }
  if (state.childRunId) {
    return `<div class="recover-kicker">Recovery</div>
      <p class="recover-note">Already applied on ${escapeHtml(state.childRunId)}.</p>
      <div class="recover-actions">
        <button type="button" class="primary" data-open-child="${escapeHtml(state.childRunId)}">Open recovered run</button>
      </div>`;
  }
  const others = V1_ACTIONS.filter((item) => item !== action);
  const secondary = others
    .map(
      (item) =>
        `<button type="button" class="ghost" data-recover="${escapeHtml(item)}" ${
          state.recovering ? "disabled" : ""
        }>${escapeHtml(ACTION_LABELS[item] || item)}</button>`
    )
    .join("");
  return `<div class="recover-kicker">Proposed recovery</div>
    <p class="recover-note">${escapeHtml(note)}</p>
    <div class="recover-actions">
      <button type="button" class="primary" data-recover="${escapeHtml(action)}" ${
        state.recovering ? "disabled" : ""
      }>${escapeHtml(ACTION_LABELS[action] || action)}</button>
      ${secondary}
    </div>`;
}

function renderRecoverBar() {
  const root = $("recover-bar");
  if (!root) return;
  const html = recoverMarkup();
  if (!html) {
    root.classList.add("hidden");
    root.innerHTML = "";
    return;
  }
  root.classList.remove("hidden");
  root.innerHTML = html;
}

function renderWaterfall() {
  const root = $("waterfall");
  if (state.loading) {
    root.innerHTML = `<li class="empty"><strong>Running</strong>Waiting on the core. This can take several seconds.</li>`;
    return;
  }
  if (!state.steps.length) {
    root.innerHTML = `<li class="empty"><strong>No trace selected</strong>Run a question or pick a run from the left.</li>`;
    return;
  }
  root.innerHTML = state.steps
    .map((step, index) => {
      const active = state.selectedStep && state.selectedStep.id === step.id ? " active" : "";
      return `<li class="step ${escapeHtml(step.status)}${active}">
        <button type="button" class="step-btn" data-step="${escapeHtml(step.id)}">
          <div class="step-title">
            <span>${String(index + 1).padStart(2, "0")}  ${escapeHtml(step.title)}</span>
            ${pill(step.status, step.status)}
          </div>
          <div class="step-summary">${escapeHtml(step.summary)}</div>
        </button>
      </li>`;
    })
    .join("");
}

function flagPills(evaluation) {
  if (!evaluation) return "";
  const bits = [
    ["evidence_sufficient", evaluation.evidence_sufficient],
    ["answer_supported", evaluation.answer_supported],
  ];
  return `<div class="flags">${bits
    .map(([name, value]) => {
      const kind = value === true ? "ok" : value === false ? "error" : "warn";
      return pill(kind, `${name.replaceAll("_", " ")}: ${value === null || value === undefined ? "n/a" : value}`);
    })
    .join("")}</div>`;
}

function renderChunks(chunks) {
  if (!chunks || !chunks.length) {
    return `<div class="empty">No chunks retrieved.</div>`;
  }
  return chunks
    .map((chunk) => {
      const width = Math.max(4, Math.min(100, Math.round((chunk.score || 0) * 100)));
      const selected = chunk.chunk_id && chunk.chunk_id === state.selectedChunkId;
      const active = selected ? " selected" : "";
      const cited = selected ? `<span class="pill ok">cited</span>` : "";
      const page = chunk.page ? `<span class="pill">p. ${escapeHtml(String(chunk.page))}</span>` : "";
      const title = chunk.title
        ? `<div class="chunk-title">${escapeHtml(chunk.title)}</div>`
        : "";
      return `<article class="chunk${active}" data-chunk-id="${escapeHtml(chunk.chunk_id || "")}">
        <div class="chunk-head">
          <span>${escapeHtml(chunk.chunk_id || "")}${page}</span>
          <span>${cited}${Number(chunk.score || 0).toFixed(3)}</span>
        </div>
        ${title}
        <div class="score"><span style="width:${width}%"></span></div>
        <div class="chunk-text">${escapeHtml(chunk.text || "")}</div>
      </article>`;
    })
    .join("");
}

function kv(rows) {
  const body = rows
    .filter((row) => row[1] !== undefined && row[1] !== null && row[1] !== "")
    .map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(String(value))}</dd>`)
    .join("");
  return body ? `<dl class="kv">${body}</dl>` : "";
}

function renderInspector() {
  const root = $("inspector");
  const label = $("inspector-label");
  if (!state.selectedStep) {
    label.textContent = "Inspector";
    root.innerHTML = `<div class="empty"><strong>Inspect a step</strong>Click retrieve, evaluate, recover, or verify to see the payload.</div>`;
    return;
  }
  const step = state.selectedStep;
  label.textContent = step.title;
  const data = step.payload || {};
  if (step.kind === "query") {
    const rewritten = data.rewritten_query;
    root.innerHTML =
      kv([["question id", data.question_id]]) +
      `<p class="pane-label">Question</p><div class="block">${escapeHtml(data.query || "(empty)")}</div>` +
      (rewritten
        ? `<p class="pane-label">Rewritten query</p><div class="block">${escapeHtml(rewritten)}</div>`
        : "");
    return;
  }
  if (step.kind === "retrieve") {
    const cited = state.selectedChunkId;
    const citedNote = cited
      ? retrieveHasChunk(step, cited)
        ? cited
        : `${cited} (not in this retrieve)`
      : "";
    const signal = data.retrieval_signal || {};
    root.innerHTML =
      kv([
        ["top_k", data.top_k],
        ["embedding model", data.embedding_model],
        ["pass", data.pass],
        ["note", data.note],
        ["cited", citedNote],
        ["retrieval signal", signal.reason],
        ["top score", signal.top_score],
        ["relative margin", signal.relative_margin],
        ["weak top", signal.weak_top],
        ["ambiguous top", signal.ambiguous_top],
      ]) + renderChunks(data.chunks);
    return;
  }
  if (step.kind === "evaluate") {
    root.innerHTML =
      flagPills(data) +
      kv([
        ["judge", data.judge],
        ["model", data.model],
        ["sufficiency", data.sufficiency_rationale],
        ["support", data.support_rationale],
        ["note", data.note],
      ]);
    return;
  }
  if (step.kind === "generate") {
    const parsed = formatAnswerHtml(data.answer || "(empty)", data.pass);
    root.innerHTML =
      kv([
        ["model", data.model],
        ["pass", data.pass],
      ]) +
      `<div class="block">${parsed.html}</div>` +
      missingCitationNote(parsed.missing);
    return;
  }
  if (step.kind === "recover") {
    const previous = data.previous_answer
      ? formatAnswerHtml(data.previous_answer, "first")
      : null;
    root.innerHTML =
      kv([
        ["action", data.action],
        ["trigger", data.trigger],
        ["source", data.source],
        ["recovery status", data.recovery_status],
        ["attributed class", data.attributed_class],
        ["reason", data.reason],
        ["rewritten query", data.rewritten_query],
        ["attempts", Array.isArray(data.recovery_attempts) && data.recovery_attempts.length
          ? data.recovery_attempts.map((item) => item && item.action).filter(Boolean).join(" → ")
          : ""],
        ["expand", data.parameters && (data.parameters.from_k + " → " + data.parameters.to_k)],
      ]) +
      (previous
        ? `<p class="pane-label">Previous answer</p><div class="block">${previous.html}</div>${missingCitationNote(previous.missing)}`
        : "");
    return;
  }
  root.innerHTML = kv(Object.entries(data).map(([key, value]) => [key.replaceAll("_", " "), stringify(value)]));
}

function stringify(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function render() {
  renderRunList();
  renderAnswer();
  renderRecoverBar();
  renderWaterfall();
  renderInspector();
  renderPlaygroundChat();
  renderPlaygroundInspect();
  if (typeof renderCanvas === "function") {
    renderCanvas();
    renderNodeInspector();
  }
}

async function loadTraces() {
  const payload = await api("/api/traces");
  state.traces = payload.traces || [];
  await loadEval();
  renderRunList();
}

async function loadEval() {
  const strip = $("eval-strip");
  if (!strip) return;
  const payload = await api("/api/eval");
  const actions = Object.entries(payload.by_action || {})
    .map(([name, count]) => `${name}=${count}`)
    .join(" · ");
  const verifies = Object.entries(payload.by_verification || {})
    .map(([name, count]) => `${name}=${count}`)
    .join(" · ");
  const proposed = payload.proposed ? ` · proposed=${payload.proposed}` : "";
  const latency =
    payload.mean_latency_ms == null ? "" : ` · mean latency ${Math.round(payload.mean_latency_ms)}ms`;
  strip.textContent = `n=${payload.n} · abstain=${payload.abstain}${proposed}${actions ? ` · ${actions}` : ""}${verifies ? ` · ${verifies}` : ""}${latency}`;
}

async function selectRun(runId) {
  showError("");
  const payload = await api(`/api/traces/${encodeURIComponent(runId)}`);
  state.selectedId = runId;
  state.trace = payload.trace;
  state.steps = payload.steps || [];
  state.selectedStep = state.steps[0] || null;
  state.selectedChunkId = null;
  state.childRunId = payload.child_run_id || null;
  render();
}

function clearSelection() {
  state.selectedId = null;
  state.trace = null;
  state.steps = [];
  state.selectedStep = null;
  state.selectedChunkId = null;
  state.childRunId = null;
}

async function deleteRun(runId) {
  const item = (state.traces || []).find((row) => row.run_id === runId);
  const childId =
    (item && item.child_run_id) || (state.selectedId === runId ? state.childRunId : null);
  const message = childId
    ? `Delete this run and its recovered child from disk?\n${runId}\n${childId}`
    : `Delete this run from disk?\n${runId}`;
  const ok = window.confirm(message);
  if (!ok) return;
  showError("");
  await api(`/api/traces/${encodeURIComponent(runId)}`, { method: "DELETE" });
  const wasSelected = state.selectedId === runId || state.selectedId === childId;
  if (wasSelected) {
    clearSelection();
  }
  await loadTraces();
  if (wasSelected && state.traces.length) {
    await selectRun(state.traces[0].run_id);
    return;
  }
  render();
}

async function deleteAllRuns() {
  const n = state.traces.length;
  if (!n) return;
  const ok = window.confirm(
    `Delete all ${n} run${n === 1 ? "" : "s"} from disk?\nThis cannot be undone.`
  );
  if (!ok) return;
  showError("");
  await api("/api/traces", { method: "DELETE" });
  clearSelection();
  await loadTraces();
  render();
}

function readTopK(fromPlayground) {
  const field = fromPlayground ? $("pg-top-k") : $("top-k");
  const raw = Number(field.value);
  if (!Number.isInteger(raw) || raw < 1 || raw > 20) {
    return null;
  }
  return raw;
}

async function applyRecovery(action) {
  if (!state.selectedId || !action || state.recovering) return;
  showError("");
  state.recovering = true;
  renderRecoverBar();
  try {
    const payload = await api(`/api/runs/${encodeURIComponent(state.selectedId)}/recover`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    state.recovering = false;
    state.selectedId = payload.run_id;
    state.trace = payload.trace;
    state.steps = payload.steps || [];
    state.selectedStep = state.steps.find((step) => step.id === "recover") || state.steps[0] || null;
    state.childRunId = payload.child_run_id || null;
    if (state.view === "playground") {
      state.messages.push({
        role: "assistant",
        text: (payload.trace && payload.trace.answer) || payload.answer || retrieveFallback(payload),
        runId: payload.run_id,
      });
    }
    await loadTraces();
    render();
  } catch (error) {
    state.recovering = false;
    renderRecoverBar();
    showError(error.message || String(error));
  }
}

async function runQuestion(fromPlayground) {
  const questionEl = fromPlayground ? $("pg-question") : $("question");
  const modeEl = fromPlayground ? $("pg-mode") : $("mode");
  const runButtons = fromPlayground
    ? [$("pg-send"), $("pg-run")].filter(Boolean)
    : [$("run-btn")];
  const question = questionEl.value.trim();
  if (!question) {
    showError("Enter a question.");
    return;
  }
  const topK = readTopK(fromPlayground);
  if (topK === null) {
    showError("top_k must be an integer from 1 to 20.");
    return;
  }
  showError("");
  if (fromPlayground) {
    state.messages.push({ role: "user", text: question });
    canvasState.note = "";
  }
  state.loading = true;
  runButtons.forEach((button) => {
    button.disabled = true;
  });
  render();
  try {
    const payload = await api("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        mode: modeEl.value,
        top_k: topK,
      }),
    });
    state.loading = false;
    state.selectedId = payload.run_id;
    state.trace = payload.trace;
    state.steps = payload.steps || [];
    state.selectedStep = state.steps.find((step) => step.id === "recover") || state.steps[0] || null;
    state.childRunId = payload.child_run_id || null;
    if (fromPlayground) {
      state.messages.push({
        role: "assistant",
        text: (payload.trace && payload.trace.answer) || payload.answer || retrieveFallback(payload),
        runId: payload.run_id,
      });
      questionEl.value = "";
    }
    await loadTraces();
    render();
  } catch (error) {
    state.loading = false;
    if (fromPlayground) {
      state.messages.push({ role: "assistant", text: error.message || String(error), error: true });
    }
    renderWaterfall();
    renderPlaygroundChat();
    renderPlaygroundInspect();
    renderCanvas();
    renderNodeInspector();
    showError(error.message || String(error));
  } finally {
    runButtons.forEach((button) => {
      button.disabled = false;
    });
  }
}

async function loadDocuments() {
  const payload = await api("/api/documents");
  state.documents = payload.documents || [];
}

async function loadKeys() {
  state.keys = [];
  const id = state.meta && state.meta.corpus_id;
  if (!id || !state.meta.writable) return;
  const payload = await api(`/api/projects/${encodeURIComponent(id)}/keys`);
  state.keys = payload.keys || [];
}

async function createProjectKey() {
  const id = state.meta && state.meta.corpus_id;
  if (!id || !state.meta.writable) return;
  const payload = await api(`/api/projects/${encodeURIComponent(id)}/keys`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  state.revealedKey = payload.key || null;
  await loadKeys();
  renderPlaygroundKnowledge();
}

async function revokeProjectKey(keyId) {
  const id = state.meta && state.meta.corpus_id;
  if (!id || !keyId) return;
  const ok = window.confirm("Revoke this API key? External evaluations using it will stop immediately.");
  if (!ok) return;
  await api(`/api/projects/${encodeURIComponent(id)}/keys/${encodeURIComponent(keyId)}`, {
    method: "DELETE",
  });
  state.revealedKey = null;
  await loadKeys();
  renderPlaygroundKnowledge();
}

async function copyRevealedKey() {
  if (!state.revealedKey) return;
  try {
    await navigator.clipboard.writeText(state.revealedKey);
  } catch {
    showError("Could not copy the key. Select it and copy manually.");
  }
}

async function createPlaygroundProject(name) {
  const payload = await api("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  clearSelection();
  state.messages = [];
  state.uploads = [];
  await loadMeta();
  await loadCorpora();
  await loadTraces();
  await loadDocuments();
  state.revealedKey = null;
  await loadKeys();
  $("corpus").value = payload.active_id;
  render();
  renderPlaygroundKnowledge();
}

async function uploadFiles(fileList) {
  const files = [...fileList];
  if (!files.length) return;
  showError("");
  for (const file of files) {
    const name = file.name || "";
    if (!/\.(txt|pdf)$/i.test(name)) {
      state.uploads = [{ name, status: "failed", error: "Only .txt and .pdf files can be uploaded." }];
      renderPlaygroundKnowledge();
      showError("Only .txt and .pdf files can be uploaded.");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      state.uploads = [{ name, status: "failed", error: "File is larger than 8 MB." }];
      renderPlaygroundKnowledge();
      showError("File is larger than 8 MB.");
      return;
    }
    state.uploads = [{ name, status: "indexing" }];
    renderPlaygroundKnowledge();
    try {
      const body = new FormData();
      body.append("file", file, file.name);
      await api("/api/documents", { method: "POST", body });
      state.uploads = [{ name, status: "ready" }];
    } catch (error) {
      state.uploads = [{ name, status: "failed", error: error.message || String(error) }];
      renderPlaygroundKnowledge();
      throw error;
    }
  }
  await loadMeta();
  await loadDocuments();
  renderPlaygroundKnowledge();
}

async function deleteDocument(name) {
  await api(`/api/documents/${encodeURIComponent(name)}`, { method: "DELETE" });
  await loadMeta();
  await loadDocuments();
  renderPlaygroundKnowledge();
}

async function deletePlaygroundProject() {
  const id = state.meta && state.meta.corpus_id;
  if (!id || !state.meta.writable) return;
  const ok = window.confirm(`Delete project ${state.meta.corpus_label} and its documents?`);
  if (!ok) return;
  await api(`/api/projects/${encodeURIComponent(id)}`, { method: "DELETE" });
  clearSelection();
  state.messages = [];
  state.uploads = [];
  await loadMeta();
  await loadCorpora();
  await loadTraces();
  await loadDocuments().catch(() => {
    state.documents = [];
  });
  state.keys = [];
  state.revealedKey = null;
  render();
  renderPlaygroundKnowledge();
}

async function savePlaygroundConfig() {
  const id = state.meta && state.meta.corpus_id;
  if (!id || !state.meta.writable) return;
  const payload = await api(`/api/projects/${encodeURIComponent(id)}/config`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(state.draftConfig),
  });
  if (payload.project && payload.project.config) {
    state.draftConfig = {
      instructions: payload.project.config.instructions || "",
      chat_model: payload.project.config.chat_model || "gpt-4o-mini",
      top_k: Number(payload.project.config.top_k) || 4,
    };
  }
  await loadMeta();
  renderPlaygroundKnowledge();
}

function syncDraftConfig() {
  const config = (state.meta && state.meta.agent_config) || {};
  state.draftConfig = {
    instructions: config.instructions || "",
    chat_model: config.chat_model || "gpt-4o-mini",
    top_k: Number(config.top_k) || 4,
  };
  if ($("pg-top-k") && state.meta && state.meta.writable) {
    $("pg-top-k").value = String(state.draftConfig.top_k);
  }
}

function captureDraftConfig() {
  const instructions = $("pg-instructions");
  const model = $("pg-chat-model");
  const topK = $("pg-config-top-k");
  if (instructions) state.draftConfig.instructions = instructions.value;
  if (model) state.draftConfig.chat_model = model.value;
  if (topK) {
    const parsed = Number(topK.value);
    if (Number.isInteger(parsed) && parsed >= 1 && parsed <= 20) {
      state.draftConfig.top_k = parsed;
    }
  }
}

function retrieveFallback(payload) {
  const chunks = (payload.trace && payload.trace.retrieved_chunks) || [];
  if (chunks.length) {
    return `Retrieved ${chunks.length} chunks. Open Sources to inspect them.`;
  }
  return "No chunks retrieved.";
}

function renderPlaygroundKnowledge() {
  renderKnowledge();
  renderAgent();
  renderApiPanel();
  if (typeof renderCanvas === "function") {
    renderCanvas();
    renderNodeInspector();
  }
}

function renderKnowledge() {
  const knowledge = $("pg-knowledge");
  if (!knowledge) return;
  const writable = Boolean(state.meta && state.meta.writable);
  const docs = state.documents || [];
  const docItems = docs
    .map(
      (item) => `<li>
        <span>${escapeHtml(item.name)} · ${item.size} B</span>
        ${
          writable
            ? `<button type="button" class="ghost danger" data-doc-del="${escapeHtml(item.name)}">Remove</button>`
            : ""
        }
      </li>`
    )
    .join("");
  const uploads = (state.uploads || [])
    .map((item) => {
      const kind = item.status === "failed" ? "error" : item.status === "ready" ? "ok" : "warn";
      const detail = item.error || item.status;
      return `<li class="${kind}">${escapeHtml(item.name)} — ${escapeHtml(detail)}</li>`;
    })
    .join("");
  knowledge.innerHTML = `${
      writable
        ? ""
        : `<p class="recover-note">Built-in corpora are read-only. Create a project to upload your own files.</p>`
    }
    <form class="project-form" id="pg-project-form">
      <input id="pg-project-name" maxlength="80" placeholder="New project name" />
      <button type="submit" class="ghost">Create</button>
    </form>
    ${
      writable
        ? `<div class="dropzone" id="pg-drop" role="button" tabindex="0">
            Drop .txt or .pdf here, or click to choose
            <input id="pg-file" type="file" accept=".txt,.pdf,text/plain,application/pdf" multiple />
          </div>`
        : ""
    }
    ${uploads ? `<ul class="upload-status">${uploads}</ul>` : ""}
    ${
      docs.length
        ? `<ul class="doc-list">${docItems}</ul>`
        : `<div class="empty"><strong>No documents yet</strong>${
            writable ? "Upload a notice or guide to give the agent something to retrieve." : "Switch to a project, or create one."
          }</div>`
    }
    ${
      writable
        ? `<div class="pg-knowledge-head"><button type="button" class="ghost danger" id="pg-delete-project">Delete project</button></div>`
        : ""
    }`;
}

function renderAgent() {
  const root = $("pg-agent");
  if (!root) return;
  const writable = Boolean(state.meta && state.meta.writable);
  if (!writable) {
    root.innerHTML = `<div class="empty"><strong>Projects only</strong>Create a project in Knowledge to set instructions and a model.</div>`;
    return;
  }
  const modelOptions = CHAT_MODELS.map((model) => {
    const selected = model === state.draftConfig.chat_model ? " selected" : "";
    return `<option value="${escapeHtml(model)}"${selected}>${escapeHtml(model)}</option>`;
  }).join("");
  root.innerHTML = `<form class="pg-config" id="pg-config-form">
      <label class="sr-only" for="pg-instructions">Instructions</label>
      <textarea id="pg-instructions" maxlength="8000" placeholder="How this agent should answer, on top of grounding.">${escapeHtml(
        state.draftConfig.instructions || ""
      )}</textarea>
      <button type="submit" class="primary">Save</button>
      <details>
        <summary>Advanced</summary>
        <label class="mode">
          Model
          <select id="pg-chat-model">${modelOptions}</select>
        </label>
        <label class="mode">
          Default top_k
          <input id="pg-config-top-k" type="number" min="1" max="20" step="1" value="${escapeHtml(
            String(state.draftConfig.top_k || 4)
          )}" />
        </label>
      </details>
    </form>`;
}

function renderApiPanel() {
  const root = $("pg-api");
  if (!root) return;
  const writable = Boolean(state.meta && state.meta.writable);
  if (!writable) {
    root.innerHTML = `<div class="empty"><strong>Projects only</strong>Create a project in Knowledge to issue an API key.</div>`;
    return;
  }
  root.innerHTML = renderProjectKeys();
}

function renderProjectKeys() {
  const rows = (state.keys || [])
    .map((item) => {
      const revoked = item.revoked_at ? " · revoked" : "";
      const action = item.revoked_at
        ? ""
        : `<button type="button" class="ghost danger" data-key-revoke="${escapeHtml(item.id)}">Revoke</button>`;
      return `<li>
        <span>${escapeHtml(item.prefix || item.id)}${revoked}</span>
        ${action}
      </li>`;
    })
    .join("");
  const revealed = state.revealedKey
    ? `<div class="revealed-key">
        <div>Copy this key now. It is not stored in plaintext and will not be shown again.</div>
        <code>${escapeHtml(state.revealedKey)}</code>
        <button type="button" class="ghost" id="pg-copy-key">Copy</button>
      </div>
      <pre class="key-sample">curl -s http://127.0.0.1:8000/api/v1/evaluations \\
  -H "Authorization: Bearer ${escapeHtml(state.revealedKey)}" \\
  -H "Content-Type: application/json" \\
  -d '{"query":"When is the library open?","answer":"Saturday 10:00-16:00.","contexts":[{"text":"Saturday 10:00-16:00."}]}'</pre>`
    : "";
  return `<div class="pg-keys">
      <p class="recover-note">Keys authenticate POST /api/v1/evaluations for this project. Rewrite and expand are proposed, not applied, on external runs.</p>
      <button type="button" class="primary" id="pg-create-key">Create key</button>
      ${revealed}
      ${rows ? `<ul class="doc-list">${rows}</ul>` : `<div class="empty">No keys yet.</div>`}
    </div>`;
}

function renderPlaygroundChat() {
  const transcript = $("pg-transcript");
  if (!transcript) return;
  if (!state.messages.length && !state.loading) {
    transcript.innerHTML = `<div class="empty"><strong>Ask the agent</strong>Answers and sources show up after you send a question.</div>`;
    return;
  }
  const rows = state.messages.map((item) => {
    if (item.role === "user") {
      return `<div class="pg-msg user"><div class="who">You</div>${escapeHtml(item.text)}</div>`;
    }
    const parsed = formatAnswerHtml(item.text || "(empty)");
    return `<div class="pg-msg"><div class="who">${item.error ? "Error" : "Agent"}</div><div class="block">${parsed.html}</div></div>`;
  });
  if (state.loading) {
    rows.push(`<div class="pg-msg"><div class="who">Agent</div>Retrieving and evaluating…</div>`);
  }
  transcript.innerHTML = rows.join("");
  transcript.scrollTop = transcript.scrollHeight;
}

function renderPlaygroundInspect() {
  const inspect = $("pg-inspect");
  if (!inspect) return;
  const recover = recoverMarkup();
  const chunks = ((state.trace && state.trace.retrieved_chunks) || []).slice(0, 8);
  const config = (state.trace && state.trace.agent_config) || {};
  if (!chunks.length && !recover) {
    inspect.innerHTML = `<div class="empty"><strong>Sources</strong>Retrieved chunks and recovery details appear after a run.</div>`;
    return;
  }
  inspect.innerHTML =
    (recover ? `<div class="recover-bar" style="margin:0 0 12px">${recover}</div>` : "") +
    kv([
      ["run", state.selectedId],
      ["recovery", state.trace && state.trace.recovery && state.trace.recovery.action],
      ["trigger", state.trace && state.trace.recovery && state.trace.recovery.trigger],
      [
        "attempts",
        ((state.trace && state.trace.recovery_attempts) || [])
          .map((item) => item && item.action)
          .filter(Boolean)
          .join(" → "),
      ],
      ["model", config.chat_model],
      ["instructions", config.instructions],
    ]) +
    (chunks.length ? renderChunks(chunks) : "");
}

function resetPlaygroundChat() {
  state.messages = [];
  clearSelection();
  render();
}

function rerunLastPlayground() {
  const last = [...state.messages].reverse().find((item) => item.role === "user");
  if (!last) {
    showError("Nothing to rerun.");
    return;
  }
  $("pg-question").value = last.text;
  runQuestion(true).catch((error) => showError(error.message));
}

function retrieveHasChunk(step, chunkId) {
  if (!step || step.kind !== "retrieve") return false;
  const chunks = (step.payload && step.payload.chunks) || [];
  return chunks.some((chunk) => chunk.chunk_id === chunkId);
}

function selectCitation(chunkId, preferredPass) {
  if (!chunkId || !knownChunkIds().has(chunkId)) return;
  state.selectedChunkId = chunkId;
  const matches = (state.steps || []).filter((step) => retrieveHasChunk(step, chunkId));
  if (matches.length) {
    const preferred = preferredPass
      ? matches.find((step) => step.payload && step.payload.pass === preferredPass)
      : null;
    state.selectedStep = preferred || matches[matches.length - 1];
  }
  render();
  const selected = document.querySelector(".chunk.selected");
  if (selected) selected.scrollIntoView({ block: "nearest" });
}

const NODE_W = 196;
const NODE_H = 84;
const STAGE_ORDER = ["input", "corpus", "retriever", "instructions", "model", "judge", "recover", "output"];
const FLOW_TITLES = {
  input: "Input",
  corpus: "Corpus",
  retriever: "Retriever",
  instructions: "Instructions",
  model: "Model",
  judge: "Judge",
  recover: "Recover",
  output: "Output",
};

const canvasState = {
  selectedId: "input",
  selectedEdge: null,
  positions: {},
  pan: { x: 28, y: 36 },
  zoom: 1,
  note: "",
  fitted: false,
  fitScheduled: false,
  pointer: null,
};

function currentPlaygroundMode() {
  return ($("pg-mode") && $("pg-mode").value) || "loop";
}

function modeLabel(mode) {
  if (mode === "loop") return "Loop · auto recover";
  if (mode === "loop_confirm") return "Loop · confirm recovery";
  if (mode === "baseline") return "Baseline RAG";
  return "Retrieve only";
}

function stagesForMode(mode) {
  const generate = mode !== "retrieve_only";
  const evaluation = mode === "loop" || mode === "loop_confirm";
  return STAGE_ORDER.filter((id) => {
    if (id === "instructions" || id === "model") return generate;
    if (id === "judge" || id === "recover") return evaluation;
    return true;
  });
}

function isRemovableStage(id) {
  return id === "instructions" || id === "model" || id === "judge" || id === "recover";
}

function clipText(value, max) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

function flagWord(value) {
  if (value === true) return "true";
  if (value === false) return "false";
  return "n/a";
}

function latestStep(kind) {
  const matches = (state.steps || []).filter((step) => step.kind === kind);
  return matches.length ? matches[matches.length - 1] : null;
}

function mapStepStatus(status) {
  if (status === "ok") return "ok";
  if (status === "error") return "error";
  if (status === "warn" || status === "empty") return "warn";
  return "idle";
}

function lastPlaygroundMessage() {
  return state.messages.length ? state.messages[state.messages.length - 1] : null;
}

function activeChatModel() {
  if (state.meta && state.meta.writable) return state.draftConfig.chat_model || "gpt-4o-mini";
  return (state.meta && state.meta.configured_chat_model) || "gpt-4o-mini";
}

function nodeCopy(id) {
  const mode = currentPlaygroundMode();
  if (id === "input") {
    const typed = $("pg-question") && $("pg-question").value.trim();
    const last = [...state.messages].reverse().find((item) => item.role === "user");
    return {
      summary: clipText(typed || (last && last.text) || "Question for this run", 42),
      meta: "Sent with Run",
    };
  }
  if (id === "corpus") {
    const label = (state.meta && state.meta.corpus_label) || "Workspace";
    const count = (state.documents || []).length;
    const files = count === 1 ? "1 file" : `${count} files`;
    return {
      summary: clipText(count ? `${label} · ${files}` : label, 42),
      meta: (state.meta && state.meta.corpus_industry) || (state.meta && state.meta.writable ? "Project" : "Read-only workspace"),
    };
  }
  if (id === "retriever") {
    const topK = $("pg-top-k") ? $("pg-top-k").value : String(state.draftConfig.top_k || 4);
    return {
      summary: `top_k ${topK}`,
      meta: (state.meta && state.meta.configured_embedding_model) || "In-memory index",
    };
  }
  if (id === "instructions") {
    const text = (state.draftConfig.instructions || "").trim();
    return {
      summary: text ? clipText(text, 42) : "Grounding prompt",
      meta: state.meta && state.meta.writable ? "Saved on the project" : "Server grounding prompt",
    };
  }
  if (id === "model") {
    return { summary: activeChatModel(), meta: "temperature 0" };
  }
  if (id === "judge") {
    const evaluation = state.trace && state.trace.runtime_evaluation;
    return {
      summary: evaluation
        ? `sufficient ${flagWord(evaluation.evidence_sufficient)} · supported ${flagWord(evaluation.answer_supported)}`
        : "Grounding flags",
      meta: "temperature 0",
    };
  }
  if (id === "recover") {
    const action = state.trace && state.trace.recovery && state.trace.recovery.action;
    const verify = latestStep("verify");
    return {
      summary: action ? ACTION_LABELS[action] || action : mode === "loop_confirm" ? "Confirm recovery" : "Auto recover",
      meta: verify && verify.summary
        ? clipText(`${mode === "loop_confirm" ? "confirm" : "auto · up to 2"} · ${verify.summary}`, 42)
        : mode === "loop_confirm"
          ? "confirm before apply"
          : "auto · up to 2",
    };
  }
  const last = lastPlaygroundMessage();
  if (last && last.error) return { summary: "Run failed", meta: "See the inspector" };
  const verify = latestStep("verify");
  if (verify && verify.summary) return { summary: clipText(verify.summary, 42), meta: "Latest run" };
  const answer = state.trace && state.trace.answer;
  if (answer) return { summary: clipText(answer, 42), meta: "Latest run" };
  const chunks = (state.trace && state.trace.retrieved_chunks) || [];
  if (chunks.length) return { summary: chunks.length === 1 ? "1 chunk" : `${chunks.length} chunks`, meta: "Latest run" };
  return { summary: "Result of the run", meta: "After Run" };
}

function nodeStatus(id) {
  if (state.loading) return "idle";
  if (id === "recover" && state.recovering) return "running";
  const last = lastPlaygroundMessage();
  if (id === "output" && last && last.error) return "error";
  if (!state.trace) return "idle";
  if (id === "input" || id === "corpus" || id === "instructions") return "ok";
  if (id === "retriever") {
    const step = latestStep("retrieve");
    return step ? mapStepStatus(step.status) : "idle";
  }
  if (id === "model") {
    const step = latestStep("generate");
    if (!step || step.status === "skipped") return "idle";
    return mapStepStatus(step.status);
  }
  if (id === "judge") {
    const step = latestStep("evaluate");
    return step ? mapStepStatus(step.status) : "idle";
  }
  if (id === "recover") {
    if (state.trace.recovery_status === "proposed") return "warn";
    const step = latestStep("recover");
    if (step) return mapStepStatus(step.status);
    const verify = latestStep("verify");
    return verify ? mapStepStatus(verify.status) : "idle";
  }
  const verify = latestStep("verify");
  if (verify) return mapStepStatus(verify.status);
  if (state.trace.answer || ((state.trace.retrieved_chunks || []).length)) return "ok";
  return "idle";
}

function ensurePositions(ids) {
  const missing = ids.filter((id) => !canvasState.positions[id]);
  if (!missing.length) return;
  if (missing.length === ids.length) {
    ids.forEach((id, index) => {
      canvasState.positions[id] = { x: 16 + index * 232, y: 40 };
    });
    return;
  }
  let x = 16;
  ids.forEach((id) => {
    const pos = canvasState.positions[id];
    if (pos) x = Math.max(x, pos.x + 232);
  });
  missing.forEach((id) => {
    canvasState.positions[id] = { x, y: 40 };
    x += 232;
  });
}

function setPlaygroundMode(mode, note) {
  const select = $("pg-mode");
  if (select && select.value !== mode) select.value = mode;
  canvasState.note = note || "";
  const stages = stagesForMode(currentPlaygroundMode());
  if (!stages.includes(canvasState.selectedId)) canvasState.selectedId = stages[0] || "input";
  renderCanvas();
  renderNodeInspector();
}

function addStage(kind) {
  const mode = currentPlaygroundMode();
  if (kind === "generate") {
    if (mode !== "retrieve_only") {
      canvasState.selectedId = "model";
      canvasState.selectedEdge = null;
      canvasState.note = "Generate is already in this run.";
      renderCanvas();
      renderNodeInspector();
      return;
    }
    canvasState.selectedId = "model";
    canvasState.selectedEdge = null;
    setPlaygroundMode("baseline", "Mode is baseline RAG.");
    return;
  }
  if (kind !== "evaluation") return;
  if (mode === "loop" || mode === "loop_confirm") {
    canvasState.selectedId = "judge";
    canvasState.selectedEdge = null;
    canvasState.note = "Evaluation is already in this run.";
    renderCanvas();
    renderNodeInspector();
    return;
  }
  canvasState.selectedId = "recover";
  canvasState.selectedEdge = null;
  const note = mode === "retrieve_only"
    ? "Mode is loop with auto recover. Generate is on this run too."
    : "Mode is loop with auto recover.";
  setPlaygroundMode("loop", note);
}

function removeStage(id) {
  const mode = currentPlaygroundMode();
  if (id === "instructions" || id === "model") {
    if (mode === "retrieve_only") return;
    const hadEval = mode === "loop" || mode === "loop_confirm";
    canvasState.selectedId = "retriever";
    canvasState.selectedEdge = null;
    setPlaygroundMode(
      "retrieve_only",
      hadEval ? "Mode is retrieve only. Generate and evaluation left this run." : "Mode is retrieve only."
    );
    return;
  }
  if (id === "judge" || id === "recover") {
    if (mode !== "loop" && mode !== "loop_confirm") return;
    canvasState.selectedId = "model";
    canvasState.selectedEdge = null;
    setPlaygroundMode("baseline", "Mode is baseline RAG.");
  }
}

function removeEdgeTarget(target) {
  if (target === "instructions" || target === "model" || target === "judge" || target === "recover") {
    removeStage(target);
    return;
  }
  canvasState.note = "Input, corpus, retriever, and output stay connected on every run.";
  renderCanvas();
}

function connectionPlan(from, to) {
  if (!from || !to || from === to) return { ok: false, note: "Choose two different blocks." };
  const stages = stagesForMode(currentPlaygroundMode());
  const fromIndex = stages.indexOf(from);
  if (fromIndex >= 0 && stages[fromIndex + 1] === to) return { ok: true, note: "Already connected." };
  const mode = currentPlaygroundMode();
  const towardGenerate = to === "instructions" || to === "model";
  const fromEarly = from === "input" || from === "corpus" || from === "retriever";
  if (towardGenerate && fromEarly) {
    if (mode !== "retrieve_only") return { ok: true, note: "Generate is already in this run." };
    return { ok: true, mode: "baseline", select: "model", note: "Mode is baseline RAG." };
  }
  const towardEval = to === "judge" || to === "recover";
  if (towardEval && (from === "model" || from === "instructions")) {
    if (mode === "loop" || mode === "loop_confirm") return { ok: true, note: "Evaluation is already in this run." };
    if (mode === "retrieve_only") return { ok: false, note: "Add Generate before Evaluation." };
    return { ok: true, mode: "loop", select: "recover", note: "Mode is loop with auto recover." };
  }
  if (towardEval && mode === "retrieve_only") return { ok: false, note: "Add Generate before Evaluation." };
  return { ok: false, note: "Those blocks do not connect in this run." };
}

function applyConnection(from, to) {
  const result = connectionPlan(from, to);
  if (!result.ok) {
    canvasState.note = result.note;
    renderCanvas();
    return;
  }
  if (result.mode) {
    canvasState.selectedId = result.select || canvasState.selectedId;
    canvasState.selectedEdge = null;
    setPlaygroundMode(result.mode, result.note);
    return;
  }
  canvasState.note = result.note || "Already connected.";
  renderCanvas();
}

function insertFromPort(from) {
  const mode = currentPlaygroundMode();
  if (mode === "retrieve_only" && (from === "input" || from === "corpus" || from === "retriever")) {
    canvasState.selectedId = "model";
    canvasState.selectedEdge = null;
    setPlaygroundMode("baseline", "Mode is baseline RAG.");
    return;
  }
  if (mode === "baseline" && (from === "model" || from === "instructions")) {
    canvasState.selectedId = "recover";
    canvasState.selectedEdge = null;
    setPlaygroundMode("loop", "Mode is loop with auto recover.");
    return;
  }
  canvasState.note = "Nothing further connects from that block.";
  renderCanvas();
}

function renderPalette() {
  const root = $("pg-palette");
  if (!root) return;
  const mode = currentPlaygroundMode();
  const generateOn = mode !== "retrieve_only";
  const evalOn = mode === "loop" || mode === "loop_confirm";
  root.innerHTML = `<div class="pane-label">Blocks</div>
    <p class="palette-note">Drag a block onto the canvas. The run mode updates to match.</p>
    ${paletteItem("generate", "Generate", "Instructions and model", generateOn)}
    ${paletteItem("evaluation", "Evaluation", "Judge and recover", evalOn)}
    <p class="palette-fixed">On every run: Input, Corpus, Retriever, Output.</p>`;
}

function paletteItem(id, title, detail, on) {
  return `<button type="button" class="palette-item${on ? " is-on" : ""}" draggable="${on ? "false" : "true"}" data-add="${id}">
      <span>${escapeHtml(title)}</span>
      <small>${escapeHtml(detail)}${on ? " · on canvas" : ""}</small>
    </button>`;
}

function canvasStatusText() {
  if (state.loading) return "Running";
  if (state.recovering) return "Applying recovery";
  if (canvasState.note) return canvasState.note;
  return modeLabel(currentPlaygroundMode());
}

function renderCanvas() {
  const host = $("pg-nodes");
  const canvas = $("pg-canvas");
  if (!host || !canvas) return;
  renderPalette();
  const stages = stagesForMode(currentPlaygroundMode());
  ensurePositions(stages);
  if (!stages.includes(canvasState.selectedId)) canvasState.selectedId = stages[0] || "input";
  host.innerHTML = stages.map((id) => flowNodeHtml(id)).join("");
  drawEdges();
  applyWorldTransform();
  const status = $("pg-canvas-status");
  if (status) status.textContent = canvasStatusText();
  if (!canvasState.fitted && !canvasState.fitScheduled) {
    canvasState.fitScheduled = true;
    requestAnimationFrame(() => {
      canvasState.fitScheduled = false;
      const view = $("pg-canvas");
      if (!view || view.clientWidth < 40) return;
      frameCanvas();
      canvasState.fitted = true;
    });
  }
}

function flowNodeHtml(id) {
  const copy = nodeCopy(id);
  const status = nodeStatus(id);
  const pos = canvasState.positions[id] || { x: 16, y: 40 };
  const selected = id === canvasState.selectedId ? " is-selected" : "";
  const removable = isRemovableStage(id)
    ? `<button type="button" class="flow-remove" data-remove="${id}" aria-label="Remove ${escapeHtml(FLOW_TITLES[id])} from this run">×</button>`
    : "";
  const inlet = id === "input"
    ? ""
    : `<button type="button" class="flow-port in" data-port="in" data-node="${id}" aria-label="${escapeHtml(FLOW_TITLES[id])} input"></button>`;
  const outlet = id === "output"
    ? ""
    : `<button type="button" class="flow-port out" data-port="out" data-node="${id}" aria-label="${escapeHtml(FLOW_TITLES[id])} output"></button>`;
  return `<article class="flow-node is-${status}${selected}" data-node="${id}" style="transform: translate(${pos.x}px, ${pos.y}px)">
      <span class="flow-port-slot">${inlet}</span>
      <div class="flow-body">
        <div class="flow-top">
          <span class="flow-kicker">${escapeHtml(FLOW_TITLES[id])}</span>
          <span class="flow-dot" title="${escapeHtml(status)}"></span>
          ${removable}
        </div>
        <div class="flow-sub">${escapeHtml(copy.summary)}</div>
        <div class="flow-meta">${escapeHtml(copy.meta)}</div>
      </div>
      <span class="flow-port-slot">${outlet}</span>
    </article>`;
}

function updateNodeSubtitle(id) {
  const node = document.querySelector(`.flow-node[data-node="${id}"]`);
  if (!node) return;
  const copy = nodeCopy(id);
  const sub = node.querySelector(".flow-sub");
  const meta = node.querySelector(".flow-meta");
  if (sub) sub.textContent = copy.summary;
  if (meta) meta.textContent = copy.meta;
}

function portOut(id) {
  const pos = canvasState.positions[id] || { x: 0, y: 0 };
  return { x: pos.x + NODE_W, y: pos.y + NODE_H / 2 };
}

function portIn(id) {
  const pos = canvasState.positions[id] || { x: 0, y: 0 };
  return { x: pos.x, y: pos.y + NODE_H / 2 };
}

function edgePath(x1, y1, x2, y2) {
  const dx = Math.max(48, Math.abs(x2 - x1) * 0.45);
  const fmt = (n) => Number(n).toFixed(1);
  return `M ${fmt(x1)} ${fmt(y1)} C ${fmt(x1 + dx)} ${fmt(y1)}, ${fmt(x2 - dx)} ${fmt(y2)}, ${fmt(x2)} ${fmt(y2)}`;
}

function sizeWorld() {
  const stages = stagesForMode(currentPlaygroundMode());
  let maxX = 800;
  let maxY = 420;
  stages.forEach((id) => {
    const pos = canvasState.positions[id];
    if (!pos) return;
    maxX = Math.max(maxX, pos.x + NODE_W + 120);
    maxY = Math.max(maxY, pos.y + NODE_H + 120);
  });
  const world = $("pg-world");
  const svg = $("pg-edges");
  if (world) {
    world.style.width = `${maxX}px`;
    world.style.height = `${maxY}px`;
  }
  if (svg) {
    svg.setAttribute("width", String(maxX));
    svg.setAttribute("height", String(maxY));
  }
}

function drawEdges(preview) {
  const svg = $("pg-edges");
  if (!svg) return;
  sizeWorld();
  const stages = stagesForMode(currentPlaygroundMode());
  const parts = [];
  for (let index = 0; index < stages.length - 1; index += 1) {
    const from = stages[index];
    const to = stages[index + 1];
    const start = portOut(from);
    const end = portIn(to);
    const key = `${from}->${to}`;
    const selected = canvasState.selectedEdge === key ? " is-selected" : "";
    const d = edgePath(start.x, start.y, end.x, end.y);
    parts.push(`<path class="pg-edge-hit${selected}" data-from="${from}" data-to="${to}" d="${d}"></path>`);
    parts.push(`<path class="pg-edge${selected}" d="${d}"></path>`);
  }
  if (preview && canvasState.pointer && canvasState.pointer.type === "link") {
    const start = portOut(canvasState.pointer.id);
    parts.push(`<path class="pg-edge is-preview" d="${edgePath(start.x, start.y, preview.x, preview.y)}"></path>`);
  }
  svg.innerHTML = parts.join("");
}

function applyWorldTransform() {
  const world = $("pg-world");
  if (!world) return;
  world.style.transform = `translate(${canvasState.pan.x}px, ${canvasState.pan.y}px) scale(${canvasState.zoom})`;
}

function placeNode(id) {
  const node = document.querySelector(`.flow-node[data-node="${id}"]`);
  const pos = canvasState.positions[id];
  if (!node || !pos) return;
  node.style.transform = `translate(${pos.x}px, ${pos.y}px)`;
}

function markSelectedNode() {
  document.querySelectorAll(".flow-node").forEach((node) => {
    node.classList.toggle("is-selected", node.dataset.node === canvasState.selectedId);
  });
}

function clientToWorld(clientX, clientY) {
  const canvas = $("pg-canvas");
  const rect = canvas.getBoundingClientRect();
  return {
    x: (clientX - rect.left - canvasState.pan.x) / canvasState.zoom,
    y: (clientY - rect.top - canvasState.pan.y) / canvasState.zoom,
  };
}

function frameCanvas() {
  const canvas = $("pg-canvas");
  if (!canvas) return;
  const stages = stagesForMode(currentPlaygroundMode());
  ensurePositions(stages);
  const first = canvasState.positions[stages[0]];
  if (!first) return;
  canvasState.zoom = 1;
  canvasState.pan.x = 28 - first.x;
  canvasState.pan.y = Math.max(24, (canvas.clientHeight - NODE_H) / 2 - first.y);
  applyWorldTransform();
}

function fitCanvas() {
  const canvas = $("pg-canvas");
  if (!canvas) return;
  const stages = stagesForMode(currentPlaygroundMode());
  ensurePositions(stages);
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  stages.forEach((id) => {
    const pos = canvasState.positions[id];
    minX = Math.min(minX, pos.x);
    minY = Math.min(minY, pos.y);
    maxX = Math.max(maxX, pos.x + NODE_W);
    maxY = Math.max(maxY, pos.y + NODE_H);
  });
  const pad = 36;
  const boundsW = Math.max(1, maxX - minX);
  const boundsH = Math.max(1, maxY - minY);
  const zoom = Math.max(0.32, Math.min(1.15, (canvas.clientWidth - pad * 2) / boundsW, (canvas.clientHeight - pad * 2) / boundsH));
  canvasState.zoom = zoom;
  canvasState.pan.x = (canvas.clientWidth - boundsW * zoom) / 2 - minX * zoom;
  canvasState.pan.y = (canvas.clientHeight - boundsH * zoom) / 2 - minY * zoom;
  applyWorldTransform();
}

function zoomCanvas(factor) {
  const canvas = $("pg-canvas");
  if (!canvas) return;
  const mx = canvas.clientWidth / 2;
  const my = canvas.clientHeight / 2;
  const next = Math.min(1.6, Math.max(0.32, canvasState.zoom * factor));
  const ratio = next / canvasState.zoom;
  canvasState.pan.x = mx - (mx - canvasState.pan.x) * ratio;
  canvasState.pan.y = my - (my - canvasState.pan.y) * ratio;
  canvasState.zoom = next;
  applyWorldTransform();
}

function writableProject() {
  return Boolean(state.meta && state.meta.writable);
}

function renderNodeInspector() {
  const root = $("pg-node-config");
  const title = $("pg-inspector-title");
  if (!root || !title) return;
  const stages = stagesForMode(currentPlaygroundMode());
  if (!stages.includes(canvasState.selectedId)) canvasState.selectedId = stages[0] || "input";
  const id = canvasState.selectedId;
  title.textContent = FLOW_TITLES[id] || "Inspector";
  root.innerHTML = inspectorHtml(id);
}

function inspectorHtml(id) {
  if (id === "input") return inputInspector();
  if (id === "corpus") return corpusInspector();
  if (id === "retriever") return retrieverInspector();
  if (id === "instructions") return instructionsInspector();
  if (id === "model") return modelInspector();
  if (id === "judge") return judgeInspector();
  if (id === "recover") return recoverInspector();
  return outputInspector();
}

function inputInspector() {
  const examples = ((state.meta && state.meta.examples) || [])
    .map(
      (question) =>
        `<button type="button" class="chip" data-fill-question="${escapeHtml(question)}">${escapeHtml(clipText(question, 80))}</button>`
    )
    .join("");
  return `<p class="recover-note">The question in the dock is what this run sends. The retriever and the judge both see that text.</p>
    ${examples ? `<div class="chips">${examples}</div>` : ""}`;
}

function corpusInspector() {
  const docs = state.documents || [];
  const names = docs
    .slice(0, 8)
    .map((item) => `<li><span>${escapeHtml(item.name)}</span></li>`)
    .join("");
  const note = writableProject()
    ? "Drop .txt or .pdf files in the left column. This project indexes them for retrieval."
    : "Built-in workspaces stay read-only. Create a project to upload files.";
  return `<p class="recover-note">${note}</p>
    ${names ? `<ul class="doc-list">${names}</ul>` : `<div class="empty">No documents indexed.</div>`}`;
}

function retrieverInspector() {
  const value = $("pg-top-k") ? $("pg-top-k").value : String(state.draftConfig.top_k || 4);
  const embed = (state.meta && state.meta.configured_embedding_model) || "";
  const save = writableProject()
    ? `<button type="button" class="ghost" id="pg-node-save">Save as project default</button>`
    : "";
  return `<label class="mode">top_k
      <input id="pg-node-topk" type="number" min="1" max="20" step="1" value="${escapeHtml(String(value))}" />
    </label>
    <p class="recover-note">The next run sends this top_k.${embed ? ` Embedding model: ${escapeHtml(embed)}.` : ""}</p>
    ${save}`;
}

function instructionsInspector() {
  if (!writableProject()) {
    return `<p class="recover-note">This workspace uses the grounding prompt. Create a project to add instructions. Saved instructions are prepended and still cannot invent facts.</p>`;
  }
  return `<label class="sr-only" for="pg-node-instructions">Instructions</label>
    <textarea id="pg-node-instructions" maxlength="8000" placeholder="How this agent should answer, on top of grounding.">${escapeHtml(state.draftConfig.instructions || "")}</textarea>
    <p class="recover-note">Save to prepend this text to the grounding prompt on the next run.</p>
    <button type="button" class="ghost" id="pg-node-save">Save configuration</button>`;
}

function modelInspector() {
  const model = activeChatModel();
  if (!writableProject()) {
    return `<p class="recover-note">This workspace uses ${escapeHtml(model)}. Temperature is 0 for generation, the judge, and recovery. Create a project to choose another allowed model.</p>`;
  }
  const options = CHAT_MODELS.map((item) => {
    const selected = item === state.draftConfig.chat_model ? " selected" : "";
    return `<option value="${escapeHtml(item)}"${selected}>${escapeHtml(item)}</option>`;
  }).join("");
  return `<label class="mode">Model
      <select id="pg-node-model">${options}</select>
    </label>
    <p class="recover-note">Temperature is 0. Save to use this model on the next run.</p>
    <button type="button" class="ghost" id="pg-node-save">Save configuration</button>`;
}

function judgeInspector() {
  const fields = [
    ["evidence_sufficient", "boolean", "required"],
    ["answer_supported", "boolean | null", "with an answer"],
    ["sufficiency_rationale", "string", "optional"],
    ["support_rationale", "string", "optional"],
  ];
  const rows = fields
    .map(
      ([name, type, flag]) =>
        `<li><span>${escapeHtml(name)}</span><span>${escapeHtml(type)}</span><span class="schema-flag">${escapeHtml(flag)}</span></li>`
    )
    .join("");
  const evaluation = state.trace && state.trace.runtime_evaluation;
  const live = evaluation
    ? flagPills(evaluation) +
      kv([
        ["sufficiency", evaluation.sufficiency_rationale],
        ["support", evaluation.support_rationale],
        ["judge", evaluation.judge],
        ["model", evaluation.model],
      ])
    : "";
  return `<p class="pane-label">Response shape</p>
    <ul class="schema-fields">${rows}</ul>
    <p class="recover-note">The judge always returns this shape. Temperature is 0. Gold answers are never included.</p>
    ${live}`;
}

function recoverInspector() {
  const mode = currentPlaygroundMode();
  const proposal = recoverMarkup();
  return `<label class="mode">When a failure is diagnosed
      <select id="pg-node-policy">
        <option value="loop"${mode === "loop" ? " selected" : ""}>Auto recover</option>
        <option value="loop_confirm"${mode === "loop_confirm" ? " selected" : ""}>Confirm first</option>
      </select>
    </label>
    <p class="recover-note">${
      mode === "loop_confirm"
        ? "Confirm writes a proposal and waits for a choice."
        : "Auto applies up to 2 recovery actions, then verifies."
    }</p>
    ${proposal ? `<div class="recover-bar">${proposal}</div>` : ""}`;
}

function outputInspector() {
  const last = lastPlaygroundMessage();
  if (last && last.error) return `<div class="banner">${escapeHtml(last.text)}</div>`;
  const trace = state.trace;
  if (!trace) return `<div class="empty"><strong>Output</strong>Run a question to fill this block.</div>`;
  const answer = trace.answer || "";
  const verify = latestStep("verify");
  if (!answer.trim()) {
    const count = (trace.retrieved_chunks || []).length;
    return kv([
      ["chunks", count],
      ["model", trace.model],
    ]) + `<div class="empty">This run stopped before an answer. Sources lists the chunks.</div>`;
  }
  const parsed = formatAnswerHtml(answer);
  return kv([
    ["run", state.selectedId],
    ["verification", verify && verify.summary],
    ["model", trace.model],
  ]) + `<div class="block">${parsed.html}</div>${missingCitationNote(parsed.missing)}`;
}

function applyInspectorDraft() {
  const instructions = $("pg-node-instructions");
  const model = $("pg-node-model");
  const topK = $("pg-node-topk");
  if (instructions) {
    state.draftConfig.instructions = instructions.value;
    const existing = $("pg-instructions");
    if (existing) existing.value = instructions.value;
  }
  if (model) {
    state.draftConfig.chat_model = model.value;
    const existing = $("pg-chat-model");
    if (existing) existing.value = model.value;
  }
  if (topK) {
    const parsed = Number(topK.value);
    if (Number.isInteger(parsed) && parsed >= 1 && parsed <= 20) {
      state.draftConfig.top_k = parsed;
      if ($("pg-top-k")) $("pg-top-k").value = String(parsed);
      const saved = $("pg-config-top-k");
      if (saved) saved.value = String(parsed);
    }
  }
}

function onCanvasPointerDown(event) {
  if (event.button !== 0) return;
  const canvas = $("pg-canvas");
  const remove = event.target.closest("[data-remove]");
  if (remove) {
    event.preventDefault();
    event.stopPropagation();
    removeStage(remove.dataset.remove);
    return;
  }
  const port = event.target.closest(".flow-port.out");
  if (port) {
    event.preventDefault();
    canvasState.pointer = { type: "link", id: port.dataset.node, pointerId: event.pointerId };
    canvas.setPointerCapture(event.pointerId);
    drawEdges(clientToWorld(event.clientX, event.clientY));
    return;
  }
  const node = event.target.closest(".flow-node");
  if (node) {
    event.preventDefault();
    const id = node.dataset.node;
    const world = clientToWorld(event.clientX, event.clientY);
    const pos = canvasState.positions[id] || { x: 0, y: 0 };
    canvasState.selectedId = id;
    canvasState.selectedEdge = null;
    canvasState.pointer = {
      type: "move",
      id,
      dx: world.x - pos.x,
      dy: world.y - pos.y,
      pointerId: event.pointerId,
    };
    canvas.setPointerCapture(event.pointerId);
    canvas.focus({ preventScroll: true });
    markSelectedNode();
    renderNodeInspector();
    return;
  }
  const edge = event.target.closest(".pg-edge-hit");
  if (edge) {
    canvasState.selectedEdge = `${edge.dataset.from}->${edge.dataset.to}`;
    canvasState.selectedId = edge.dataset.to;
    canvas.focus({ preventScroll: true });
    markSelectedNode();
    drawEdges();
    renderNodeInspector();
    return;
  }
  canvasState.pointer = {
    type: "pan",
    x: event.clientX,
    y: event.clientY,
    panX: canvasState.pan.x,
    panY: canvasState.pan.y,
    pointerId: event.pointerId,
  };
  canvas.setPointerCapture(event.pointerId);
  canvas.focus({ preventScroll: true });
}

function onCanvasPointerMove(event) {
  const pointer = canvasState.pointer;
  if (!pointer || pointer.pointerId !== event.pointerId) return;
  if (pointer.type === "pan") {
    canvasState.pan.x = pointer.panX + (event.clientX - pointer.x);
    canvasState.pan.y = pointer.panY + (event.clientY - pointer.y);
    applyWorldTransform();
    return;
  }
  if (pointer.type === "move") {
    const world = clientToWorld(event.clientX, event.clientY);
    canvasState.positions[pointer.id] = { x: world.x - pointer.dx, y: world.y - pointer.dy };
    placeNode(pointer.id);
    drawEdges();
    return;
  }
  if (pointer.type === "link") drawEdges(clientToWorld(event.clientX, event.clientY));
}

function onCanvasPointerUp(event) {
  const pointer = canvasState.pointer;
  if (!pointer || pointer.pointerId !== event.pointerId) return;
  canvasState.pointer = null;
  if (pointer.type !== "link") return;
  const hit = document.elementFromPoint(event.clientX, event.clientY);
  const port = hit && hit.closest(".flow-port");
  const node = hit && hit.closest(".flow-node");
  const to = (port && port.dataset.node) || (node && node.dataset.node);
  drawEdges();
  if (to && to !== pointer.id) applyConnection(pointer.id, to);
  else if (!to) insertFromPort(pointer.id);
  else drawEdges();
}

function isStageDrag(event) {
  const types = event.dataTransfer ? [...event.dataTransfer.types] : [];
  return types.includes("text/plain");
}

function bindCanvas() {
  const canvas = $("pg-canvas");
  const palette = $("pg-palette");
  const pane = $("pg-inspect-pane");
  if (!canvas || !palette || !pane) return;
  canvas.addEventListener("pointerdown", onCanvasPointerDown);
  canvas.addEventListener("pointermove", onCanvasPointerMove);
  canvas.addEventListener("pointerup", onCanvasPointerUp);
  canvas.addEventListener("pointercancel", onCanvasPointerUp);
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const mx = event.clientX - rect.left;
    const my = event.clientY - rect.top;
    const next = Math.min(1.6, Math.max(0.32, canvasState.zoom * (event.deltaY > 0 ? 0.92 : 1.08)));
    const ratio = next / canvasState.zoom;
    canvasState.pan.x = mx - (mx - canvasState.pan.x) * ratio;
    canvasState.pan.y = my - (my - canvasState.pan.y) * ratio;
    canvasState.zoom = next;
    applyWorldTransform();
  }, { passive: false });
  canvas.addEventListener("dragenter", (event) => {
    if (!isStageDrag(event)) return;
    event.preventDefault();
    canvas.classList.add("is-dropping");
  });
  canvas.addEventListener("dragover", (event) => {
    if (!isStageDrag(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  });
  canvas.addEventListener("dragleave", (event) => {
    if (canvas.contains(event.relatedTarget)) return;
    canvas.classList.remove("is-dropping");
  });
  canvas.addEventListener("drop", (event) => {
    const kind = event.dataTransfer.getData("text/plain");
    canvas.classList.remove("is-dropping");
    if (kind !== "generate" && kind !== "evaluation") return;
    event.preventDefault();
    addStage(kind);
  });
  palette.addEventListener("click", (event) => {
    const item = event.target.closest("[data-add]");
    if (!item) return;
    addStage(item.dataset.add);
  });
  palette.addEventListener("dragstart", (event) => {
    const item = event.target.closest("[data-add]");
    if (!item || item.classList.contains("is-on")) {
      event.preventDefault();
      return;
    }
    event.dataTransfer.setData("text/plain", item.dataset.add);
    event.dataTransfer.effectAllowed = "copy";
  });
  $("pg-fit").addEventListener("click", () => fitCanvas());
  $("pg-zoom-in").addEventListener("click", () => zoomCanvas(1.1));
  $("pg-zoom-out").addEventListener("click", () => zoomCanvas(0.9));
  $("pg-run").addEventListener("click", () => {
    runQuestion(true).catch((error) => showError(error.message));
  });
  $("pg-mode").addEventListener("change", () => {
    const stages = stagesForMode(currentPlaygroundMode());
    if (!stages.includes(canvasState.selectedId)) canvasState.selectedId = stages[0] || "input";
    canvasState.selectedEdge = null;
    canvasState.note = "";
    renderCanvas();
    renderNodeInspector();
  });
  $("pg-top-k").addEventListener("input", () => {
    const field = $("pg-node-topk");
    if (field && document.activeElement !== field) field.value = $("pg-top-k").value;
    updateNodeSubtitle("retriever");
  });
  $("pg-question").addEventListener("input", () => updateNodeSubtitle("input"));
  pane.addEventListener("click", (event) => {
    if (event.target.closest("#pg-inspect")) return;
    const save = event.target.closest("#pg-node-save");
    if (save) {
      event.preventDefault();
      applyInspectorDraft();
      savePlaygroundConfig().catch((error) => showError(error.message));
      return;
    }
    const fill = event.target.closest("[data-fill-question]");
    if (fill) {
      $("pg-question").value = fill.dataset.fillQuestion;
      updateNodeSubtitle("input");
      $("pg-question").focus();
      return;
    }
    const openChild = event.target.closest("[data-open-child]");
    if (openChild) {
      selectRun(openChild.dataset.openChild).catch((error) => showError(error.message));
      return;
    }
    const recover = event.target.closest("[data-recover]");
    if (recover) {
      applyRecovery(recover.dataset.recover).catch((error) => showError(error.message));
      return;
    }
    const cite = event.target.closest("button.cite");
    if (!cite) return;
    selectCitation(cite.dataset.chunkId, cite.dataset.citePass || null);
  });
  pane.addEventListener("change", (event) => {
    if (event.target.id === "pg-node-policy") {
      canvasState.selectedId = "recover";
      setPlaygroundMode(event.target.value, "");
      return;
    }
    if (event.target.id === "pg-node-model") {
      state.draftConfig.chat_model = event.target.value;
      const existing = $("pg-chat-model");
      if (existing) existing.value = event.target.value;
      updateNodeSubtitle("model");
    }
  });
  pane.addEventListener("input", (event) => {
    if (event.target.id === "pg-node-topk") {
      const parsed = Number(event.target.value);
      if (Number.isInteger(parsed) && parsed >= 1 && parsed <= 20) {
        $("pg-top-k").value = String(parsed);
        const saved = $("pg-config-top-k");
        if (saved) saved.value = String(parsed);
        state.draftConfig.top_k = parsed;
        updateNodeSubtitle("retriever");
      }
      return;
    }
    if (event.target.id === "pg-node-instructions") {
      state.draftConfig.instructions = event.target.value;
      const existing = $("pg-instructions");
      if (existing) existing.value = event.target.value;
      updateNodeSubtitle("instructions");
    }
  });
  window.addEventListener("keydown", (event) => {
    if (state.view !== "playground") return;
    if (event.key !== "Delete" && event.key !== "Backspace") return;
    if (document.activeElement !== canvas) return;
    if (canvasState.selectedEdge) {
      const target = canvasState.selectedEdge.split("->")[1];
      event.preventDefault();
      removeEdgeTarget(target);
      return;
    }
    if (isRemovableStage(canvasState.selectedId)) {
      event.preventDefault();
      removeStage(canvasState.selectedId);
    }
  });
}



function bind() {
  $("run-btn").addEventListener("click", runQuestion);
  $("refresh-runs").addEventListener("click", () => loadTraces().catch((error) => showError(error.message)));
  $("delete-all-runs").addEventListener("click", () => deleteAllRuns().catch((error) => showError(error.message)));
  $("corpus").addEventListener("change", (event) => {
    switchCorpus(event.target.value).catch((error) => showError(error.message));
  });
  $("question").addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      runQuestion();
    }
  });
  $("example-chips").addEventListener("click", (event) => {
    const button = event.target.closest(".chip");
    if (!button) return;
    $("question").value = button.dataset.q;
    $("question").focus();
  });
  $("run-list").addEventListener("click", (event) => {
    const del = event.target.closest(".run-delete");
    if (del) {
      event.preventDefault();
      event.stopPropagation();
      deleteRun(del.dataset.id).catch((error) => showError(error.message));
      return;
    }
    const item = event.target.closest(".run-item");
    if (!item) return;
    selectRun(item.dataset.id).catch((error) => showError(error.message));
  });
  $("waterfall").addEventListener("click", (event) => {
    const button = event.target.closest(".step-btn");
    if (!button) return;
    state.selectedStep = state.steps.find((step) => step.id === button.dataset.step) || null;
    render();
  });
  $("recover-bar").addEventListener("click", (event) => {
    const openChild = event.target.closest("[data-open-child]");
    if (openChild) {
      selectRun(openChild.dataset.openChild).catch((error) => showError(error.message));
      return;
    }
    const recover = event.target.closest("[data-recover]");
    if (!recover) return;
    applyRecovery(recover.dataset.recover).catch((error) => showError(error.message));
  });
  $("answer-text").addEventListener("click", (event) => {
    const cite = event.target.closest("button.cite");
    if (!cite) return;
    selectCitation(cite.dataset.chunkId, cite.dataset.citePass || null);
  });
  $("inspector").addEventListener("click", (event) => {
    const cite = event.target.closest("button.cite");
    if (!cite) return;
    selectCitation(cite.dataset.chunkId, cite.dataset.citePass || null);
  });
  window.addEventListener("hashchange", () => {
    applyView();
    renderPlaygroundChat();
    renderPlaygroundInspect();
    renderPlaygroundKnowledge();
  });
  $("pg-reset").addEventListener("click", () => resetPlaygroundChat());
  $("pg-rerun").addEventListener("click", () => rerunLastPlayground());
  $("pg-composer").addEventListener("submit", (event) => {
    event.preventDefault();
    runQuestion(true).catch((error) => showError(error.message));
  });
  $("pg-question").addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      runQuestion(true).catch((error) => showError(error.message));
    }
  });
  $("pg-collapse").addEventListener("click", () => {
    state.inspectCollapsed = !state.inspectCollapsed;
    applyView();
  });
  $("nav-collapse").addEventListener("click", () => {
    state.navCollapsed = !state.navCollapsed;
    applyView();
  });
  document.getElementById("app").addEventListener("submit", (event) => {
    const configForm = event.target.closest("#pg-config-form");
    if (configForm) {
      event.preventDefault();
      captureDraftConfig();
      savePlaygroundConfig().catch((error) => showError(error.message));
      return;
    }
    const form = event.target.closest("#pg-project-form");
    if (!form) return;
    event.preventDefault();
    const name = $("pg-project-name").value.trim();
    if (!name) {
      showError("Name the project first.");
      return;
    }
    createPlaygroundProject(name).catch((error) => showError(error.message));
  });
  document.getElementById("app").addEventListener("input", (event) => {
    if (!["pg-instructions", "pg-chat-model", "pg-config-top-k"].includes(event.target.id)) return;
    captureDraftConfig();
  });
  document.getElementById("app").addEventListener("click", (event) => {
    const delProject = event.target.closest("#pg-delete-project");
    if (delProject) {
      event.preventDefault();
      deletePlaygroundProject().catch((error) => showError(error.message));
      return;
    }
    const createKey = event.target.closest("#pg-create-key");
    if (createKey) {
      event.preventDefault();
      createProjectKey().catch((error) => showError(error.message));
      return;
    }
    const copyKey = event.target.closest("#pg-copy-key");
    if (copyKey) {
      event.preventDefault();
      copyRevealedKey().catch((error) => showError(error.message));
      return;
    }
    const revokeKey = event.target.closest("[data-key-revoke]");
    if (revokeKey) {
      event.preventDefault();
      revokeProjectKey(revokeKey.dataset.keyRevoke).catch((error) => showError(error.message));
      return;
    }
    const remove = event.target.closest("[data-doc-del]");
    if (remove) {
      event.preventDefault();
      deleteDocument(remove.dataset.docDel).catch((error) => showError(error.message));
      return;
    }
    const zone = event.target.closest("#pg-drop");
    if (zone && event.target.id !== "pg-file") {
      const input = $("pg-file");
      if (input) input.click();
    }
  });
  document.getElementById("app").addEventListener("keydown", (event) => {
    if (event.target.id !== "pg-drop") return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    const input = $("pg-file");
    if (input) input.click();
  });
  document.getElementById("app").addEventListener("change", (event) => {
    if (event.target.id !== "pg-file") return;
    uploadFiles(event.target.files).catch((error) => showError(error.message));
    event.target.value = "";
  });
  document.getElementById("app").addEventListener("dragover", (event) => {
    const zone = event.target.closest("#pg-drop");
    if (!zone) return;
    event.preventDefault();
    zone.classList.add("dragover");
  });
  document.getElementById("app").addEventListener("dragleave", (event) => {
    const zone = event.target.closest("#pg-drop");
    if (!zone) return;
    zone.classList.remove("dragover");
  });
  document.getElementById("app").addEventListener("drop", (event) => {
    const zone = event.target.closest("#pg-drop");
    if (!zone) return;
    event.preventDefault();
    zone.classList.remove("dragover");
    uploadFiles(event.dataTransfer.files).catch((error) => showError(error.message));
  });
  $("pg-transcript").addEventListener("click", (event) => {
    const cite = event.target.closest("button.cite");
    if (!cite) return;
    selectCitation(cite.dataset.chunkId, cite.dataset.citePass || null);
  });
  $("pg-inspect").addEventListener("click", (event) => {
    const openChild = event.target.closest("[data-open-child]");
    if (openChild) {
      selectRun(openChild.dataset.openChild).catch((error) => showError(error.message));
      return;
    }
    const recover = event.target.closest("[data-recover]");
    if (recover) {
      applyRecovery(recover.dataset.recover).catch((error) => showError(error.message));
      return;
    }
    const cite = event.target.closest("button.cite");
    if (!cite) return;
    selectCitation(cite.dataset.chunkId, cite.dataset.citePass || null);
  });
  bindCanvas();
}

async function boot() {
  applyView();
  renderExamples();
  bind();
  render();
  try {
    await loadMeta();
    await loadCorpora();
    await loadTraces();
    await loadDocuments().catch(() => {
      state.documents = [];
    });
    await loadKeys();
    if (state.traces.length) {
      await selectRun(state.traces[0].run_id);
    } else {
      render();
    }
    renderPlaygroundKnowledge();
  } catch (error) {
    showError(error.message || String(error));
    renderPlaygroundKnowledge();
  }
}

boot();
