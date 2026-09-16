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
};

const ACTION_LABELS = {
  regenerate: "Regenerate from evidence",
  rewrite: "Rewrite query and retrieve",
  abstain: "Abstain",
  accept: "Keep first-pass answer",
};

const V1_ACTIONS = ["regenerate", "rewrite", "abstain", "accept"];

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
  const banner = $("error-banner");
  if (!message) {
    banner.classList.add("hidden");
    banner.textContent = "";
    return;
  }
  banner.textContent = message;
  banner.classList.remove("hidden");
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
  if (!state.meta.api_key_present) {
    $("mode").value = "retrieve_only";
  }
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
    await loadMeta();
    await loadCorpora();
    await loadTraces();
    if (state.traces.length) {
      await selectRun(state.traces[0].run_id);
    } else {
      render();
    }
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
      const when = (item.timestamp || "").replace("T", " ").slice(0, 19);
      return `<div class="run-item${active}" data-id="${escapeHtml(item.run_id)}">
        <button type="button" class="run-select">
          <div class="q">${escapeHtml(item.query || "(no query)")}</div>
          <div class="meta">
            ${pill(item.action, item.action)}
            ${item.recovery_status === "proposed" ? pill("warn", "proposed") : ""}
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
  const recovered = Boolean(before || rewritten || firstChunks);
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

function renderRecoverBar() {
  const root = $("recover-bar");
  if (!root) return;
  const status = state.trace && state.trace.recovery_status;
  const action = proposedAction();
  const canPropose = Boolean(state.trace && status === "proposed" && action && action !== "accept");
  if (!canPropose) {
    root.classList.add("hidden");
    root.innerHTML = "";
    return;
  }
  root.classList.remove("hidden");
  const diagnosis = (state.trace && state.trace.diagnosis) || {};
  const klass = diagnosis.failure_class || "no class claimed";
  const rationale = diagnosis.rationale || "";
  if (state.childRunId) {
    root.innerHTML = `<div class="recover-kicker">Recovery</div>
      <p class="recover-note">Already applied on ${escapeHtml(state.childRunId)}.</p>
      <div class="recover-actions">
        <button type="button" class="primary" data-open-child="${escapeHtml(state.childRunId)}">Open recovered run</button>
      </div>`;
    return;
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
  root.innerHTML = `<div class="recover-kicker">Proposed recovery</div>
    <p class="recover-note">${escapeHtml(klass)}${rationale ? ` — ${escapeHtml(rationale)}` : ""}</p>
    <div class="recover-actions">
      <button type="button" class="primary" data-recover="${escapeHtml(action)}" ${
        state.recovering ? "disabled" : ""
      }>${escapeHtml(ACTION_LABELS[action] || action)}</button>
      ${secondary}
    </div>`;
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
      const title = chunk.title
        ? `<div class="chunk-title">${escapeHtml(chunk.title)}</div>`
        : "";
      return `<article class="chunk${active}" data-chunk-id="${escapeHtml(chunk.chunk_id || "")}">
        <div class="chunk-head">
          <span>${escapeHtml(chunk.chunk_id || "")}</span>
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
    root.innerHTML =
      kv([
        ["top_k", data.top_k],
        ["embedding model", data.embedding_model],
        ["pass", data.pass],
        ["note", data.note],
        ["cited", citedNote],
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
        ["source", data.source],
        ["recovery status", data.recovery_status],
        ["attributed class", data.attributed_class],
        ["reason", data.reason],
        ["rewritten query", data.rewritten_query],
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
  const latency =
    payload.mean_latency_ms == null ? "" : ` · mean latency ${Math.round(payload.mean_latency_ms)}ms`;
  strip.textContent = `n=${payload.n} · abstain=${payload.abstain}${actions ? ` · ${actions}` : ""}${verifies ? ` · ${verifies}` : ""}${latency}`;
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
  const ok = window.confirm(`Delete this run from disk?\n${runId}`);
  if (!ok) return;
  showError("");
  await api(`/api/traces/${encodeURIComponent(runId)}`, { method: "DELETE" });
  const wasSelected = state.selectedId === runId;
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

function readTopK() {
  const raw = Number($("top-k").value);
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
    await loadTraces();
    render();
  } catch (error) {
    state.recovering = false;
    renderRecoverBar();
    showError(error.message || String(error));
  }
}

async function runQuestion() {
  const question = $("question").value.trim();
  if (!question) {
    showError("Enter a question.");
    return;
  }
  const topK = readTopK();
  if (topK === null) {
    showError("top_k must be an integer from 1 to 20.");
    return;
  }
  showError("");
  state.loading = true;
  $("run-btn").disabled = true;
  renderWaterfall();
  try {
    const payload = await api("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        mode: $("mode").value,
        top_k: topK,
      }),
    });
    state.loading = false;
    state.selectedId = payload.run_id;
    state.trace = payload.trace;
    state.steps = payload.steps || [];
    state.selectedStep = state.steps.find((step) => step.id === "recover") || state.steps[0] || null;
    state.childRunId = payload.child_run_id || null;
    await loadTraces();
    render();
  } catch (error) {
    state.loading = false;
    renderWaterfall();
    showError(error.message || String(error));
  } finally {
    $("run-btn").disabled = false;
  }
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
}

async function boot() {
  renderExamples();
  bind();
  render();
  try {
    await loadMeta();
    await loadCorpora();
    await loadTraces();
    if (state.traces.length) {
      await selectRun(state.traces[0].run_id);
    } else {
      render();
    }
  } catch (error) {
    showError(error.message || String(error));
  }
}

boot();
