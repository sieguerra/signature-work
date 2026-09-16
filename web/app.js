const state = {
  meta: null,
  corpora: [],
  traces: [],
  selectedId: null,
  trace: null,
  steps: [],
  selectedStep: null,
  loading: false,
};

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
            ${pill(item.verification, item.verification)}
            <span>${escapeHtml(when)}</span>
          </div>
        </button>
        <button type="button" class="run-delete" data-id="${escapeHtml(item.run_id)}" aria-label="Delete run" title="Delete run">×</button>
      </div>`;
    })
    .join("");
}

function renderAnswer() {
  const bar = $("answer-bar");
  if (!state.trace) {
    bar.classList.add("hidden");
    return;
  }
  bar.classList.remove("hidden");
  $("answer-run-id").textContent = state.trace.run_id || "";
  const answer = (state.trace.answer || "").trim();
  $("answer-text").textContent = answer || "(no generated answer)";
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
      return `<article class="chunk">
        <div class="chunk-head">
          <span>${escapeHtml(chunk.chunk_id || "")}</span>
          <span>${Number(chunk.score || 0).toFixed(3)}</span>
        </div>
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
  if (step.kind === "retrieve") {
    root.innerHTML =
      kv([
        ["top_k", data.top_k],
        ["embedding model", data.embedding_model],
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
      ]);
    return;
  }
  if (step.kind === "generate") {
    root.innerHTML =
      kv([["model", data.model]]) +
      `<div class="block">${escapeHtml(data.answer || "(empty)")}</div>` +
      (data.previous_answer
        ? `<p class="pane-label">Previous answer</p><div class="block">${escapeHtml(data.previous_answer)}</div>`
        : "");
    return;
  }
  if (step.kind === "recover") {
    root.innerHTML =
      kv([
        ["action", data.action],
        ["attributed class", data.attributed_class],
        ["reason", data.reason],
        ["rewritten query", data.rewritten_query],
      ]) +
      (data.previous_answer
        ? `<p class="pane-label">Previous answer</p><div class="block">${escapeHtml(data.previous_answer)}</div>`
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
  renderWaterfall();
  renderInspector();
}

async function loadTraces() {
  const payload = await api("/api/traces");
  state.traces = payload.traces || [];
  renderRunList();
}

async function selectRun(runId) {
  showError("");
  const payload = await api(`/api/traces/${encodeURIComponent(runId)}`);
  state.selectedId = runId;
  state.trace = payload.trace;
  state.steps = payload.steps || [];
  state.selectedStep = state.steps[0] || null;
  render();
}

function clearSelection() {
  state.selectedId = null;
  state.trace = null;
  state.steps = [];
  state.selectedStep = null;
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
