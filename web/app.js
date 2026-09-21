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

function currentView() {
  return location.hash.replace("#", "") === "evaluation" ? "evaluation" : "playground";
}

function applyView() {
  state.view = currentView();
  document.getElementById("app").dataset.view = state.view;
  $("nav-playground").classList.toggle("active", state.view === "playground");
  $("nav-evaluation").classList.toggle("active", state.view === "evaluation");
  $("brand-sub").textContent =
    state.view === "evaluation" ? "Trace explorer" : "Agentic RAG playground";
  document.getElementById("app").classList.toggle("inspect-collapsed", state.inspectCollapsed);
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
  const sendBtn = fromPlayground ? $("pg-send") : $("run-btn");
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
  }
  state.loading = true;
  sendBtn.disabled = true;
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
    showError(error.message || String(error));
  } finally {
    sendBtn.disabled = false;
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
  const knowledge = $("pg-knowledge");
  if (!knowledge) return;
  const writable = Boolean(state.meta && state.meta.writable);
  const label = (state.meta && state.meta.corpus_label) || "Workspace";
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
  const modelOptions = CHAT_MODELS.map((model) => {
    const selected = model === state.draftConfig.chat_model ? " selected" : "";
    return `<option value="${escapeHtml(model)}"${selected}>${escapeHtml(model)}</option>`;
  }).join("");
  knowledge.innerHTML = `<div class="pg-knowledge-head">
      <div class="pane-label">${escapeHtml(label)}</div>
      ${
        writable
          ? `<button type="button" class="ghost danger" id="pg-delete-project">Delete</button>`
          : ""
      }
    </div>
    <p class="recover-note">${
      writable
        ? "This project owns its documents, instructions, and runs. Drop files to index them."
        : "Built-in corpora are read-only. Create a project to upload your own files."
    }</p>
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
        ? `<form class="pg-config" id="pg-config-form">
            <div class="pane-label">Instructions</div>
            <textarea id="pg-instructions" maxlength="8000" placeholder="How this agent should answer, on top of grounding.">${escapeHtml(
              state.draftConfig.instructions || ""
            )}</textarea>
            <button type="submit" class="ghost">Save configuration</button>
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
          </form>
          ${renderProjectKeys()}`
        : ""
    }`;
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
      <div class="pane-label">API keys</div>
      <p class="recover-note">Keys authenticate POST /api/v1/evaluations for this project. Rewrite and expand are proposed, not applied, on external runs.</p>
      <button type="button" class="ghost" id="pg-create-key">Create key</button>
      ${revealed}
      ${rows ? `<ul class="doc-list">${rows}</ul>` : `<div class="empty">No keys yet.</div>`}
    </div>`;
}

function renderPlaygroundChat() {
  const transcript = $("pg-transcript");
  if (!transcript) return;
  if (!state.messages.length && !state.loading) {
    transcript.innerHTML = `<div class="empty"><strong>Ask the agent</strong>Questions run through the same evaluate → diagnose → recover loop as Evaluation.</div>`;
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
    $("pg-collapse").textContent = state.inspectCollapsed ? "Show sources" : "Collapse";
    applyView();
  });
  $("pg-knowledge").addEventListener("submit", (event) => {
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
  $("pg-knowledge").addEventListener("input", (event) => {
    if (!["pg-instructions", "pg-chat-model", "pg-config-top-k"].includes(event.target.id)) return;
    captureDraftConfig();
  });
  $("pg-knowledge").addEventListener("click", (event) => {
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
  $("pg-knowledge").addEventListener("keydown", (event) => {
    if (event.target.id !== "pg-drop") return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    const input = $("pg-file");
    if (input) input.click();
  });
  $("pg-knowledge").addEventListener("change", (event) => {
    if (event.target.id !== "pg-file") return;
    uploadFiles(event.target.files).catch((error) => showError(error.message));
    event.target.value = "";
  });
  $("pg-knowledge").addEventListener("dragover", (event) => {
    const zone = event.target.closest("#pg-drop");
    if (!zone) return;
    event.preventDefault();
    zone.classList.add("dragover");
  });
  $("pg-knowledge").addEventListener("dragleave", (event) => {
    const zone = event.target.closest("#pg-drop");
    if (!zone) return;
    zone.classList.remove("dragover");
  });
  $("pg-knowledge").addEventListener("drop", (event) => {
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
