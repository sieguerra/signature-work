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
  view: "overview",
  documents: [],
  openDocument: null,
  messages: [],
  inspectCollapsed: false,
  libraryCollapsed: false,
  navCollapsed: false,
  uploads: [],
  draftConfig: { instructions: "", chat_model: "gpt-4o-mini", top_k: 4 },
  savedAgent: { instructions: "", chat_model: "gpt-4o-mini", top_k: 4, behavior: null },
  agentBehavior: null,
  agentUi: { advancedOpen: false, ruleMenu: false, editingRule: null },
  agentSaving: false,
  agentSaveError: false,
  keys: [],
  revealedKey: null,
  apiLang: "curl",
  evalTab: "overview",
  evalPayload: null,
  runView: "diagram",
  quality: {},
  scoringProgress: null,
  overview: null,
  overviewError: "",
  logicalRuns: [],
  flightTraces: null,
  relFocus: null,
  relFilters: { verification: "all", recovery: "all", action: "all", diagnosis: "all", policy: "all", query: "" },
  keepReadOnly: false,
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

const VIEWS = ["overview", "test", "reliability", "data", "configuration", "integrations"];

const VIEW_ALIASES = {
  playground: "test",
  evaluation: "reliability",
  knowledge: "data",
  agent: "configuration",
  api: "integrations",
};

const VIEW_PANELS = {
  overview: "overview",
  test: "playground",
  reliability: "evaluation",
  data: "knowledge",
  configuration: "agent",
  integrations: "api",
};

function parseRoute(raw) {
  return window.ReliabilityView.parseRoute(raw, VIEWS, VIEW_ALIASES);
}

function canonicalView(raw) {
  return parseRoute(raw).view;
}

function currentView() {
  return canonicalView(location.hash);
}

function applyView() {
  const route = parseRoute(location.hash);
  const view = route.view;
  const canonical = window.ReliabilityView.routeHash(view, route.tab);
  if (location.hash !== canonical) history.replaceState(null, "", canonical);
  const changed = state.view !== view;
  state.view = view;
  if (view === "reliability" && state.evalTab !== route.tab) {
    state.evalTab = route.tab;
    state.relAutoFocus = false;
    applyEvalTab();
  }
  const app = document.getElementById("app");
  app.dataset.view = VIEW_PANELS[view];
  // Each view scrolls inside its own panel, which kept its old offset while
  // hidden. Opening a different page starts at the top. This runs after the
  // panel is shown, because a hidden panel ignores scrollTop.
  if (changed) {
    const panel = document.getElementById(`view-${VIEW_PANELS[view]}`);
    if (panel) panel.scrollTop = 0;
    playEnter(panel);
    if (view === "overview") state.overviewCountUp = true;
    if (view === "reliability") {
      state.relAutoFocus = false;
      placeTabIndicator(document.querySelector("#view-evaluation .eval-tabs"));
      renderReliability();
    }
  }
  app.classList.toggle("inspect-collapsed", state.inspectCollapsed);
  app.classList.toggle("library-collapsed", state.libraryCollapsed);
  app.classList.toggle("nav-collapsed", state.navCollapsed);
  document.querySelectorAll(".view-link").forEach((link) => {
    const view = (link.getAttribute("href") || "").replace("#", "");
    link.classList.toggle("active", view === state.view);
  });
  const collapse = $("pg-collapse");
  if (collapse) {
    const open = !state.inspectCollapsed;
    const label = open ? "Hide inspector" : "Show inspector";
    collapse.classList.toggle("is-on", open);
    collapse.setAttribute("aria-pressed", open ? "true" : "false");
    collapse.setAttribute("aria-label", label);
    collapse.title = label;
  }
  const blocks = $("pg-blocks-toggle");
  if (blocks) {
    const open = !state.libraryCollapsed;
    const label = open ? "Hide blocks" : "Show blocks";
    blocks.classList.toggle("is-on", open);
    blocks.setAttribute("aria-pressed", open ? "true" : "false");
    blocks.setAttribute("aria-label", label);
    blocks.title = label;
  }
  const navCollapse = $("nav-collapse");
  if (navCollapse) {
    const open = !state.navCollapsed;
    const label = open ? "Hide sidebar" : "Show sidebar";
    navCollapse.classList.toggle("is-on", open);
    navCollapse.setAttribute("aria-pressed", open ? "true" : "false");
    navCollapse.setAttribute("aria-label", label);
    navCollapse.dataset.tip = `${open ? "Collapse" : "Expand"} sidebar  ⌘B`;
  }
  renderShell();
}

// ---------- App shell: breadcrumb, environment status, run state, command palette ----------

const VIEW_TITLES = {
  overview: "Overview",
  test: "Test Console",
  reliability: "Reliability",
  data: "Data",
  configuration: "Configuration",
  integrations: "Integrations",
};

const VIEW_ICONS = {
  overview: "activity",
  test: "play",
  reliability: "shield-check",
  data: "database",
  configuration: "sliders",
  integrations: "code",
};

function renderShell() {
  const meta = state.meta || {};
  const label = meta.corpus_label || "Workspace";
  const sub = $("brand-sub");
  if (sub) sub.textContent = label;
  const crumbWs = $("crumb-ws");
  if (crumbWs) crumbWs.textContent = label;
  const avatar = $("ws-avatar");
  if (avatar) avatar.textContent = (label.trim()[0] || "W").toUpperCase();
  const page = $("crumb-page");
  if (page) page.textContent = VIEW_TITLES[state.view] || "";
  const mode = $("crumb-mode");
  if (mode) {
    const pgMode = $("pg-mode");
    mode.textContent = state.view === "test" && pgMode ? modeLabel(pgMode.value) : "";
  }
  const docs = $("nav-doc-count");
  if (docs) docs.textContent = meta.doc_count ? String(meta.doc_count) : "";
  const runs = $("nav-run-count");
  if (runs) {
    const count = state.logicalRuns.length ? state.logicalRuns.length : state.traces.length;
    runs.textContent = count ? String(count) : "";
  }
  document.title = `${VIEW_TITLES[state.view] || "GroundLoop"} · ${label} · GroundLoop`;
}

function renderRunState() {
  const root = $("run-state");
  if (!root) return;
  if (state.loading) {
    root.innerHTML = `<span class="pulse" aria-hidden="true"></span>Running · waiting on the core`;
  } else if (state.recovering) {
    root.innerHTML = `<span class="pulse" aria-hidden="true"></span>Applying recovery`;
  } else {
    root.textContent = "";
  }
}

function renderEnvStatus() {
  const meta = state.meta;
  const dot = $("env-dot");
  const summary = $("top-meta");
  const pop = $("env-pop");
  const btn = $("env-btn");
  // The button's accessible name carries the same sentence as #top-meta.
  const announce = (text) => {
    if (summary) summary.textContent = text;
    if (btn) btn.setAttribute("aria-label", `Environment: ${text}`);
  };
  if (!meta) {
    if (dot) dot.className = "env-dot is-error";
    announce("Backend unreachable");
    return;
  }
  const keyOn = Boolean(meta.api_key_present);
  const provider = meta.official_openai ? "OpenAI" : "custom backend";
  if (dot) dot.className = `env-dot ${keyOn ? "is-ok" : "is-warn"}`;
  const snapshot = Boolean(meta.demo && meta.demo.snapshot);
  if (snapshot && dot) dot.className = "env-dot is-ok";
  announce(snapshot ? "Read-only snapshot" : keyOn ? meta.configured_chat_model || "Connected" : "No API key");
  if (btn) btn.dataset.tip = keyOn ? `${meta.configured_chat_model} · ${provider}` : "No API key: retrieve only";
  if (!pop) return;
  const row = (iconName, key, value, tone = "") =>
    value == null || value === ""
      ? ""
      : `<li>${icon(iconName, 14)}<span class="k">${escapeHtml(key)}</span><span class="v ${tone}" title="${escapeHtml(String(value))}">${escapeHtml(String(value))}</span></li>`;
  pop.innerHTML = `<div class="env-pop-head">Environment</div>
    <ul class="env-rows">
      ${row("server", "Backend", "Connected", "ok")}
      ${row("key", "API key", keyOn ? "Present" : "Missing", keyOn ? "ok" : "warn")}
      ${row("zap", "Provider", provider)}
      ${row("sparkles", "Chat model", meta.configured_chat_model)}
      ${row("database", "Embedding", meta.configured_embedding_model)}
      ${row("file-text", "Documents", meta.doc_count)}
      ${row("folder", "Domain", !meta.writable ? meta.corpus_industry : "")}
      ${row("layers", "Access", meta.writable ? "Editable system" : "Read-only")}
    </ul>
    ${keyOn ? "" : `<p class="env-note">Without a key Test Console can only retrieve. Add OPENAI_API_KEY to .env and restart.</p>`}`;
}

function toggleEnvPop(force) {
  const pop = $("env-pop");
  const btn = $("env-btn");
  if (!pop || !btn) return;
  const open = force === undefined ? pop.hidden : force;
  pop.hidden = !open;
  btn.setAttribute("aria-expanded", open ? "true" : "false");
}

function toast(message) {
  const root = $("toasts");
  if (!root) return;
  const item = document.createElement("div");
  item.className = "toast";
  item.innerHTML = `${icon("check-circle", 15)}<span>${escapeHtml(message)}</span>`;
  root.appendChild(item);
  window.setTimeout(() => item.classList.add("is-out"), 2200);
  window.setTimeout(() => item.remove(), 2500);
}

function setNavCollapsed(collapsed) {
  state.navCollapsed = collapsed;
  try {
    localStorage.setItem("swrag.navCollapsed", collapsed ? "1" : "0");
  } catch {
    /* storage unavailable: keep the in-memory value */
  }
  applyView();
  if (typeof frameCanvas === "function") window.setTimeout(() => frameCanvas(), 260);
}

function initialNavCollapsed() {
  try {
    const saved = localStorage.getItem("swrag.navCollapsed");
    if (saved === "1" || saved === "0") return saved === "1";
  } catch {
    /* fall through to the viewport default */
  }
  return window.innerWidth < 1200;
}

const cmdk = { items: [], index: 0 };

function commandList() {
  const items = Object.keys(VIEW_TITLES).map((view) => ({
    group: "Go to",
    label: VIEW_TITLES[view],
    icon: VIEW_ICONS[view],
    hint: state.view === view ? "Current" : "",
    run: () => {
      location.hash = `#${view}`;
    },
  }));
  items.push(
    {
      group: "Actions",
      label: "Run test query",
      icon: "play",
      hint: "⌘↵",
      run: () => {
        location.hash = "#test";
        const field = $("pg-question");
        if (field && field.value.trim()) {
          runQuestion(true).catch((error) => showError(error.message));
        } else if (field) {
          window.setTimeout(() => field.focus(), 0);
        }
      },
    },
    {
      group: "Actions",
      label: "Create system",
      icon: "plus",
      run: () => {
        if (state.navCollapsed) setNavCollapsed(false);
        const form = $("new-workspace-form");
        form.hidden = false;
        window.setTimeout(() => $("new-workspace-name").focus(), 0);
      },
    },
    {
      group: "Actions",
      label: state.navCollapsed ? "Expand sidebar" : "Collapse sidebar",
      icon: "panel-left",
      hint: "⌘B",
      run: () => setNavCollapsed(!state.navCollapsed),
    },
    {
      group: "Actions",
      label: "Refresh runs",
      icon: "refresh-cw",
      run: () => loadTraces().catch((error) => showError(error.message)),
    },
    ...window.Theme.PREFS.map((pref) => ({
      group: "Theme",
      label: { system: "Use system theme", light: "Light theme", dark: "Dark theme" }[pref],
      icon: { system: "monitor", light: "sun", dark: "moon" }[pref],
      hint: window.Theme.readPref() === pref ? "Current" : "",
      run: () => window.Theme.apply(pref),
    }))
  );
  const activeId = state.meta && state.meta.corpus_id;
  state.corpora
    .filter((item) => item.writable && item.id !== activeId)
    .forEach((item) => {
      items.push({
        group: "Switch system",
        label: item.label,
        icon: "folder",
        run: () => {
          $("corpus").value = item.id;
          switchCorpus(item.id).catch((error) => showError(error.message));
        },
      });
    });
  return items;
}

function renderCmdk() {
  const list = $("cmdk-list");
  const query = $("cmdk-input").value.trim().toLowerCase();
  cmdk.items = commandList().filter(
    (item) => !query || item.label.toLowerCase().includes(query) || item.group.toLowerCase().includes(query)
  );
  cmdk.index = Math.min(cmdk.index, Math.max(0, cmdk.items.length - 1));
  if (!cmdk.items.length) {
    list.innerHTML = `<li class="cmdk-empty">No matching commands</li>`;
    $("cmdk-input").removeAttribute("aria-activedescendant");
    return;
  }
  let lastGroup = "";
  list.innerHTML = cmdk.items
    .map((item, index) => {
      const header = item.group !== lastGroup ? `<li class="cmdk-group" role="presentation">${escapeHtml(item.group)}</li>` : "";
      lastGroup = item.group;
      const selected = index === cmdk.index;
      return `${header}<li class="cmdk-item" role="option" id="cmdk-opt-${index}" data-cmdk="${index}" aria-selected="${selected}">${icon(item.icon, 15)}<span>${escapeHtml(item.label)}</span>${item.hint ? `<span class="hint">${escapeHtml(item.hint)}</span>` : ""}</li>`;
    })
    .join("");
  $("cmdk-input").setAttribute("aria-activedescendant", `cmdk-opt-${cmdk.index}`);
  const active = $(`cmdk-opt-${cmdk.index}`);
  if (active) active.scrollIntoView({ block: "nearest" });
}

function openCmdk() {
  const root = $("cmdk");
  cmdk.returnFocus = document.activeElement;
  root.hidden = false;
  $("cmdk-input").value = "";
  cmdk.index = 0;
  renderCmdk();
  $("cmdk-input").focus();
}

function closeCmdk() {
  const root = $("cmdk");
  if (root.hidden) return;
  root.hidden = true;
  if (cmdk.returnFocus && cmdk.returnFocus.focus) cmdk.returnFocus.focus();
}

function runCmdk(index) {
  const item = cmdk.items[index];
  if (!item) return;
  closeCmdk();
  item.run();
}

function renderThemeToggle() {
  const button = $("theme-toggle");
  const ico = $("theme-ico");
  if (!button || !ico) return;
  const next = window.Theme.toggled(window.Theme.current());
  const label = next === "light" ? "Switch to light theme" : "Switch to dark theme";
  ico.innerHTML = icon(next === "light" ? "sun" : "moon", 15);
  button.setAttribute("aria-label", label);
  button.dataset.tip = next === "light" ? "Light theme" : "Dark theme";
}

function bindShell() {
  const themeButton = $("theme-toggle");
  if (themeButton) {
    themeButton.addEventListener("click", () => {
      const next = window.Theme.toggled(window.Theme.current());
      // Circular reveal from the button, where the browser supports view transitions.
      if (!document.startViewTransition || prefersReducedMotion()) {
        window.Theme.apply(next);
        return;
      }
      const box = themeButton.getBoundingClientRect();
      const root = document.documentElement;
      root.style.setProperty("--reveal-x", `${box.left + box.width / 2}px`);
      root.style.setProperty("--reveal-y", `${box.top + box.height / 2}px`);
      root.classList.add("theme-reveal");
      const transition = document.startViewTransition(() => window.Theme.apply(next));
      transition.finished.finally(() => root.classList.remove("theme-reveal"));
    });
  }
  document.addEventListener("themechange", () => {
    renderThemeToggle();
    // Charts read CSS variables, so they repaint on their own. Anything that
    // cached a computed color would re-render here.
  });
  window.Theme.watchSystem();
  renderThemeToggle();
  const replaceIndicator = () => placeTabIndicator(document.querySelector("#view-evaluation .eval-tabs"));
  window.addEventListener("resize", replaceIndicator);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(replaceIndicator);
  ["open-cmdk", "topbar-cmdk"].forEach((id) => {
    const button = $(id);
    if (button) button.addEventListener("click", openCmdk);
  });
  $("cmdk").addEventListener("mousedown", (event) => {
    if (event.target.id === "cmdk") closeCmdk();
  });
  $("cmdk-input").addEventListener("input", () => {
    cmdk.index = 0;
    renderCmdk();
  });
  $("cmdk-input").addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const n = cmdk.items.length || 1;
      cmdk.index = (cmdk.index + (event.key === "ArrowDown" ? 1 : n - 1)) % n;
      renderCmdk();
    } else if (event.key === "Enter") {
      event.preventDefault();
      runCmdk(cmdk.index);
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeCmdk();
    } else if (event.key === "Tab") {
      event.preventDefault();
    }
  });
  $("cmdk-list").addEventListener("mousemove", (event) => {
    const item = event.target.closest("[data-cmdk]");
    if (!item || Number(item.dataset.cmdk) === cmdk.index) return;
    cmdk.index = Number(item.dataset.cmdk);
    renderCmdk();
  });
  $("cmdk-list").addEventListener("click", (event) => {
    const item = event.target.closest("[data-cmdk]");
    if (item) runCmdk(Number(item.dataset.cmdk));
  });
  $("env-btn").addEventListener("click", (event) => {
    event.stopPropagation();
    toggleEnvPop();
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest("#env")) toggleEnvPop(false);
  });
  $("pg-mode").addEventListener("change", () => {
    renderShell();
    renderModeNote();
  });
  window.addEventListener("keydown", (event) => {
    const mod = event.metaKey || event.ctrlKey;
    if (mod && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if ($("cmdk").hidden) openCmdk();
      else closeCmdk();
      return;
    }
    if (mod && event.key.toLowerCase() === "b") {
      event.preventDefault();
      setNavCollapsed(!state.navCollapsed);
      return;
    }
    if (event.key === "Escape") toggleEnvPop(false);
  });
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

// POST /api/runs/stream: Server-Sent Events, one per stage start and end, then
// "done" with the same payload POST /api/runs returns. Falls back to the plain
// endpoint when the browser cannot read a streamed body.
async function streamRun(body, onEvent) {
  const init = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  if (!window.ReadableStream || !window.TextDecoder) return api("/api/runs", init);
  const response = await fetch("/api/runs/stream", init);
  if (!response.ok || !response.body) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      if (payload && payload.detail) detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
    } catch {
      /* keep the status text */
    }
    throw new Error(detail);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const data = block
        .split("\n")
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6))
        .join("\n");
      if (!data) continue;
      const event = JSON.parse(data);
      if (event.type === "done") return event.run;
      if (event.type === "error") throw new Error(typeof event.detail === "string" ? event.detail : JSON.stringify(event.detail));
      onEvent(event);
    }
  }
  throw new Error("The run stream ended before the run finished.");
}

// Public deployments: a live demo (GROUNDLOOP_DEMO) or a static snapshot.
// Either way controls that would change data are hidden, and a badge says
// what kind of copy this is.
function demoInfo() {
  const demo = (state.meta && state.meta.demo) || {};
  return { live: Boolean(demo.enabled), snapshot: Boolean(demo.snapshot), runsLeft: demo.runs_left, dailyRuns: demo.daily_runs };
}

function renderDemoBadge() {
  const info = demoInfo();
  const publicCopy = info.live || info.snapshot;
  document.documentElement.classList.toggle("is-demo", publicCopy);
  document.documentElement.classList.toggle("is-snapshot", info.snapshot);
  let badge = $("demo-badge");
  if (!publicCopy) {
    if (badge) badge.remove();
    return;
  }
  if (!badge) {
    const actions = $("topbar-actions");
    if (!actions) return;
    actions.insertAdjacentHTML("afterbegin", `<span class="demo-badge" id="demo-badge"></span>`);
    badge = $("demo-badge");
  }
  const text = info.snapshot
    ? "Read-only snapshot"
    : `Public demo · ${info.runsLeft ?? 0} live run${info.runsLeft === 1 ? "" : "s"} left today`;
  const tip = info.snapshot
    ? "A saved copy of recorded runs. Asking new questions needs the live version or a local install."
    : "A shared public copy. Data cannot be changed, and live runs are capped per day.";
  badge.innerHTML = `${icon(info.snapshot ? "eye" : "zap", 12)}<span>${escapeHtml(text)}</span>`;
  badge.dataset.tip = tip;
  badge.dataset.tipWrap = "";
  badge.dataset.tipAlign = "end";
}

async function loadMeta() {
  state.meta = await api("/api/meta");
  renderEnvStatus();
  renderShell();
  renderDemoBadge();
  if (!state.meta.api_key_present) {
    const mode = $("mode");
    if (mode) mode.value = "retrieve_only";
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
  const workspaces = state.corpora.filter((item) => item.writable);
  if (!state.corpora.length) {
    select.innerHTML = `<option value="">No system yet</option>`;
    const form = $("new-workspace-form");
    if (form && !demoInfo().live && !demoInfo().snapshot) form.hidden = false;
    return;
  }
  const activeIsWorkspace = workspaces.some((item) => item.id === active);
  const readOnly = state.corpora.filter((item) => !item.writable);
  select.innerHTML = [...workspaces, ...readOnly]
    .map((item) => {
      const selected = item.id === active ? " selected" : "";
      return `<option value="${escapeHtml(item.id)}"${selected}>${escapeHtml(item.label)}</option>`;
    })
    .join("");
  // Open on the server's active system, read-only or not. Switching here
  // changed the active system for every open tab and any run in flight, and
  // hid the built-in corpora's runs on every page load.
  void activeIsWorkspace;
}

function renderExamples() {
  const host = $("example-chips");
  if (!host) return;
  const examples = (state.meta && state.meta.examples) || [];
  host.innerHTML = examples
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
    state.flightTraces = null;
    state.relFocus = null;
    state.messages = [];
    state.uploads = [];
    state.openDocument = null;
    await loadMeta();
    await loadCorpora();
    await loadTraces();
    await loadDocuments().catch(() => {
      state.documents = [];
    });
    state.revealedKey = null;
    await loadKeys();
    render();
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
  if (!root) return;
  if (!state.traces.length) {
    root.innerHTML =
      `<div class="empty"><strong>No runs yet</strong>Ask a question to write a trace. Existing files under experiments/output also appear here.</div>`;
    return;
  }
  root.innerHTML = state.traces
    .map((item) => {
      const active = item.run_id === state.selectedId ? " active" : "";
      const child = item.parent_run_id ? " child-run" : "";
      const when = item.timestamp ? window.ReliabilityView.formatWhen(item.timestamp) : "";
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
  if (!bar) return;
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
  if (!root) return;
  if (state.loading) {
    root.innerHTML = `<li class="empty"><strong>Running</strong>Waiting on the core. This can take several seconds.</li>`;
    return;
  }
  if (!state.steps.length) {
    root.innerHTML = `<li class="empty"><strong>No trace steps</strong>Inspect a run to load its steps.</li>`;
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
  if (!root || !label) return;
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
  renderRunState();
  renderRunList();
  renderAnswer();
  renderRecoverBar();
  renderRunView();
  renderWaterfall();
  renderInspector();
  renderPlaygroundChat();
  renderPlaygroundInspect();
  if (typeof renderCanvas === "function") {
    renderCanvas();
    renderNodeInspector();
  }
  renderFlight();
  renderReliability();
}

async function loadTraces() {
  const payload = await api("/api/traces");
  state.traces = payload.traces || [];
  renderRunList();
  renderShell();
  await loadOverview();
  await loadLogicalRuns();
  await loadEval();
}

function setEvalTab(tab) {
  if (tab !== state.evalTab) state.relAutoFocus = false;
  state.evalTab = tab;
  applyEvalTab();
  // The URL records the tab so reload, sharing, and Back restore it.
  const hash = window.ReliabilityView.routeHash("reliability", tab);
  if (location.hash !== hash) location.hash = hash;
}

function applyEvalTab() {
  const view = $("view-evaluation");
  if (!view) return;
  view.dataset.tab = state.evalTab;
  view.querySelectorAll("[data-eval-tab]").forEach((button) => {
    const on = button.dataset.evalTab === state.evalTab;
    button.classList.toggle("active", on);
    button.setAttribute("aria-selected", on ? "true" : "false");
    button.tabIndex = on ? 0 : -1;
  });
  placeTabIndicator(view.querySelector(".eval-tabs"));
}

// The active tab's highlight is one element that slides between tabs.
function placeTabIndicator(tabs) {
  if (!tabs) return;
  const active = tabs.querySelector("button.active");
  if (!active || !active.offsetWidth) return;
  tabs.style.setProperty("--ind-x", `${active.offsetLeft}px`);
  tabs.style.setProperty("--ind-w", `${active.offsetWidth}px`);
  tabs.classList.add("has-indicator");
}

function renderRunView() {
  const view = $("view-evaluation");
  const root = $("run-diagram");
  const tabs = $("run-view-tabs");
  if (!view || !root || !tabs) return;
  const hasRun = Boolean(state.trace);
  view.dataset.runMode = hasRun ? state.runView : "trace";
  tabs.classList.toggle("hidden", !hasRun);
  tabs.querySelectorAll("[data-run-view]").forEach((button) => {
    const on = button.dataset.runView === state.runView;
    button.classList.toggle("active", on);
    button.setAttribute("aria-selected", on ? "true" : "false");
  });
  const runId = hasRun ? String(state.trace.run_id || "") : "";
  if (typeof renderRunDiagram === "function") renderRunDiagram(root, hasRun ? state.trace : null, state.quality[runId]);
  if (hasRun && state.runView === "diagram" && String(state.trace.answer || "").trim() && !state.quality[runId]) {
    ensureQuality(runId);
  }
}

async function ensureQuality(runId) {
  state.quality[runId] = { status: "loading" };
  try {
    const saved = (await api(`/api/traces/${encodeURIComponent(runId)}/quality`)).quality;
    if (saved) {
      state.quality[runId] = { status: "done", data: saved };
    } else {
      await scoreRun(runId, { refresh: false });
      return;
    }
  } catch (error) {
    state.quality[runId] = { status: "error", error: error.message };
  }
  if (state.trace && state.trace.run_id === runId) renderRunView();
}

async function showStoredQuality(runId) {
  const saved = (await api(`/api/traces/${encodeURIComponent(runId)}/quality`)).quality;
  if (!saved) {
    state.quality[runId] = { status: "error", error: "No stored quality score." };
  } else {
    state.quality[runId] = { status: "done", data: saved };
  }
  renderReliability();
}

async function scoreRun(runId, { refresh = true } = {}) {
  state.quality[runId] = { status: "loading" };
  if (refresh && state.trace && state.trace.run_id === runId) renderRunView();
  try {
    const scored = (await api(`/api/traces/${encodeURIComponent(runId)}/quality`, { method: "POST" })).quality;
    state.quality[runId] = { status: "done", data: scored };
  } catch (error) {
    state.quality[runId] = { status: "error", error: error.message };
  }
  if (state.trace && state.trace.run_id === runId) renderRunView();
  renderReliability();
  loadEval().catch(() => {});
}

async function scoreAllRuns() {
  const runs = ((state.evalPayload && state.evalPayload.runs) || []).filter((run) => run.has_answer && !run.quality);
  if (!runs.length || state.scoringProgress) return;
  state.scoringProgress = { done: 0, total: runs.length };
  renderEvalCharts();
  let failed = 0;
  for (const run of runs) {
    try {
      const scored = (await api(`/api/traces/${encodeURIComponent(run.run_id)}/quality`, { method: "POST" })).quality;
      state.quality[run.run_id] = { status: "done", data: scored };
    } catch (error) {
      failed += 1;
      if (failed === 1) showError(`Scoring stopped: ${error.message}`);
      break;
    }
    state.scoringProgress.done += 1;
    renderEvalCharts();
  }
  state.scoringProgress = null;
  await loadEval();
}

function qualityBoardRuns() {
  const evalRuns = (state.evalPayload && state.evalPayload.runs) || [];
  const byId = new Map(evalRuns.map((run) => [run.run_id, run]));
  const logical = state.logicalRuns || [];
  if (!logical.length) return evalRuns;
  return logical.map((run) => {
    const match = byId.get(run.inspect_run_id) || null;
    const abstained = Boolean(match && match.abstained);
    return {
      query: run.query,
      run_id: (match && match.run_id) || run.inspect_run_id,
      has_answer: Boolean(match && match.has_answer && !abstained),
      abstained,
      quality: match && !abstained ? match.quality : null,
    };
  });
}

function renderEvalCharts() {
  const root = $("eval-overview");
  if (!root) return;
  if (typeof renderQualityBoard === "function") {
    renderQualityBoard(root, { runs: qualityBoardRuns() }, state.scoringProgress);
    return;
  }
  if (typeof renderEvalOverview === "function") renderEvalOverview(root, state.evalPayload, state.scoringProgress);
}

async function loadEval() {
  const payload = await api("/api/eval");
  state.evalPayload = payload;
  renderEvalCharts();
  const strip = $("eval-strip");
  if (!strip) return;
  strip.innerHTML = `<span class="eval-strip-title">Runtime tallies</span>${window.ReliabilityView.qualityTally(payload)
    .map((item) => `<span class="eval-stat"><b>${escapeHtml(item.value)}</b> ${escapeHtml(item.label)}</span>`)
    .join("")}`;
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
    state.flightTraces = null;
    state.relFocus = null;
  }
  await loadTraces();
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
  if (!field) return null;
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
  renderRunState();
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
    if (state.view === "test") {
      const parentId = payload.trace && payload.trace.parent_run_id;
      if (parentId) {
        const parent = await api(`/api/traces/${encodeURIComponent(parentId)}`);
        state.flightTraces = [parent.trace, payload.trace];
      } else {
        state.flightTraces = [payload.trace];
      }
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
    renderRunState();
    showError(error.message || String(error));
  }
}

async function runQuestion(fromPlayground) {
  const questionEl = fromPlayground ? $("pg-question") : $("question");
  const modeEl = fromPlayground ? $("pg-mode") : $("mode");
  if (!questionEl || !modeEl) return;
  const runButtons = fromPlayground
    ? [$("pg-send"), $("pg-run")].filter(Boolean)
    : [$("run-btn")].filter(Boolean);
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
  state.liveEvents = [];
  state.liveStarted = performance.now();
  runButtons.forEach((button) => {
    button.disabled = true;
  });
  render();
  const liveTimer = window.setInterval(renderLiveElapsed, 100);
  try {
    const payload = await streamRun(
      {
        question,
        mode: modeEl.value,
        top_k: topK,
        recovery_policy: selectedRecoveryPolicy(),
      },
      (event) => {
        state.liveEvents.push(event);
        renderFlight();
      }
    );
    window.clearInterval(liveTimer);
    state.liveEvents = [];
    state.loading = false;
    state.selectedId = payload.run_id;
    state.trace = payload.trace;
    state.steps = payload.steps || [];
    state.selectedStep = state.steps.find((step) => step.id === "recover") || state.steps[0] || null;
    state.childRunId = payload.child_run_id || null;
    if (fromPlayground) {
      state.flightTraces = [payload.trace];
      state.messages.push({
        role: "assistant",
        text: (payload.trace && payload.trace.answer) || payload.answer || retrieveFallback(payload),
        runId: payload.run_id,
      });
    }
    await loadTraces();
    if (demoInfo().live) loadMeta().catch(() => {});
    render();
  } catch (error) {
    window.clearInterval(liveTimer);
    state.liveEvents = [];
    state.loading = false;
    if (fromPlayground) {
      state.messages.push({ role: "assistant", text: error.message || String(error), error: true });
    }
    renderRunState();
    renderWaterfall();
    renderPlaygroundChat();
    renderPlaygroundInspect();
    renderCanvas();
    renderNodeInspector();
    renderFlight();
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
    toast("API key copied");
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
  state.openDocument = null;
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

async function openDocument(name) {
  const payload = await api(`/api/documents/${encodeURIComponent(name)}`);
  state.openDocument = { name: payload.name, text: payload.text || "" };
  renderKnowledge();
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
    if (file.size > 32 * 1024 * 1024) {
      state.uploads = [{ name, status: "failed", error: "File is larger than 32 MB." }];
      renderPlaygroundKnowledge();
      showError("File is larger than 32 MB.");
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
  if (state.openDocument && state.openDocument.name === name) state.openDocument = null;
  await loadMeta();
  await loadDocuments();
  renderPlaygroundKnowledge();
}

async function deletePlaygroundProject() {
  const id = state.meta && state.meta.corpus_id;
  if (!id || !state.meta.writable) return;
  const ok = window.confirm(`Delete system ${state.meta.corpus_label} and its documents?`);
  if (!ok) return;
  await api(`/api/projects/${encodeURIComponent(id)}`, { method: "DELETE" });
  clearSelection();
  state.messages = [];
  state.uploads = [];
  state.openDocument = null;
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
    const saved = payload.project.config;
    state.draftConfig = {
      instructions: saved.instructions || "",
      chat_model: saved.chat_model || "gpt-4o-mini",
    top_k: Number(saved.top_k) || 4,
    behavior: saved.behavior || null,
    recovery_policy: saved.recovery_policy === "gap_aware" ? "gap_aware" : "v1",
  };
  }
  await loadMeta();
  renderPlaygroundKnowledge();
}

function syncDraftConfig() {
  const config = (state.meta && state.meta.agent_config) || {};
  const instructions = config.instructions || "";
  const behavior = AgentConfig.hydrate(config.behavior, instructions);
  state.agentBehavior = behavior;
  state.draftConfig = {
    instructions,
    chat_model: config.chat_model || "gpt-4o-mini",
    top_k: Number(config.top_k) || 4,
    behavior: AgentConfig.serialize(behavior),
    recovery_policy: config.recovery_policy === "gap_aware" ? "gap_aware" : "v1",
  };
  state.savedAgent = {
    instructions,
    chat_model: state.draftConfig.chat_model,
    top_k: state.draftConfig.top_k,
    behavior: AgentConfig.serialize(behavior),
    recovery_policy: state.draftConfig.recovery_policy,
  };
  if ($("pg-top-k") && state.meta && state.meta.writable) {
    $("pg-top-k").value = String(state.draftConfig.top_k);
  }
  const policy = $("pg-recovery-policy");
  if (policy) policy.value = state.draftConfig.recovery_policy || "v1";
  syncPolicyNote();
}

function captureDraftConfig() {
  const model = $("pg-chat-model");
  const topK = $("pg-config-top-k");
  if (state.agentBehavior && state.agentBehavior.mode === "raw") {
    const instructions = $("pg-instructions");
    if (instructions) state.draftConfig.instructions = instructions.value;
  }
  if (model) state.draftConfig.chat_model = model.value;
  if (topK) {
    const parsed = Number(topK.value);
    if (Number.isInteger(parsed) && parsed >= 1 && parsed <= 20) {
      state.draftConfig.top_k = parsed;
    }
  }
  if (state.agentBehavior) state.draftConfig.behavior = AgentConfig.serialize(state.agentBehavior);
  const policy = $("pg-config-policy") || $("pg-recovery-policy");
  if (policy) state.draftConfig.recovery_policy = policy.value === "gap_aware" ? "gap_aware" : "v1";
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

function formatBytes(size) {
  const bytes = Number(size) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) {
    const kb = bytes / 1024;
    return `${kb >= 10 ? Math.round(kb) : kb.toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function uploadStatusLabel(item) {
  if (!item) return "";
  if (item.status === "indexing") return "Uploading…";
  if (item.status === "ready") return "Uploaded";
  return item.error || "Upload failed";
}

function renderKnowledge() {
  renderKnowledgePage();
  // Show the first source's text instead of an empty reader column. Once per
  // system, and never over a source the user opened or closed.
  const docs = state.documents || [];
  const corpus = state.meta && state.meta.corpus_id;
  if (docs.length && !state.openDocument && corpus && state.knowledgeAutoOpened !== corpus) {
    state.knowledgeAutoOpened = corpus;
    openDocument(docs[0].name).catch(() => {});
  }
}

function renderKnowledgePage() {
  const knowledge = $("pg-knowledge");
  if (!knowledge) return;
  const writable = Boolean(state.meta && state.meta.writable);
  const docs = state.documents || [];
  const open = state.openDocument;
  const showing = open && docs.some((item) => item.name === open.name) ? open : null;
  const total = docs.reduce((sum, item) => sum + (Number(item.size) || 0), 0);
  const label = (state.meta && state.meta.corpus_label) || "Workspace";
  const workspaceId = (state.meta && state.meta.corpus_id) || "";
  const rows = docs
    .map((item) => {
      const selected = showing && showing.name === item.name;
      const type = String(item.suffix || "").replace(/^\./, "").toUpperCase() || "FILE";
      return `<tr class="${selected ? "is-open" : ""}">
        <td>
          <button type="button" class="kn-open" data-doc-open="${escapeHtml(item.name)}">
            ${icon("file-text", 16)}
            <span>${escapeHtml(item.name)}</span>
          </button>
        </td>
        <td><span class="kn-type">${escapeHtml(type)}</span></td>
        <td class="kn-size">${escapeHtml(formatBytes(item.size))}</td>
        <td class="kn-actions">${
          writable
            ? `<button type="button" class="ghost danger" data-doc-del="${escapeHtml(item.name)}">Remove</button>`
            : ""
        }</td>
      </tr>`;
    })
    .join("");
  const upload = (state.uploads || [])[0];
  const uploadClass = upload
    ? upload.status === "failed"
      ? "is-bad"
      : upload.status === "ready"
        ? "is-ok"
        : "is-busy"
    : "";
  const dropzone = writable
    ? `<div class="dropzone${upload && upload.status === "indexing" ? " is-busy" : ""}" id="pg-drop" role="button" tabindex="0">
        ${icon("upload", 16)}
        <span><b>Drop files here or browse</b><small>TXT · PDF · up to 32 MB</small></span>
        <input id="pg-file" type="file" accept=".txt,.pdf,text/plain,application/pdf" multiple />
      </div>
      ${
        upload
          ? `<p class="kn-upload ${uploadClass}">${escapeHtml(upload.name)} — ${escapeHtml(uploadStatusLabel(upload))}</p>`
          : ""
      }`
    : "";
  const reader = showing
    ? `<article class="kn-reader">
        <div class="kn-reader-bar">
          <h3>${escapeHtml(showing.name)}</h3>
          <button type="button" class="ghost" data-doc-close>Close</button>
        </div>
        <p class="kn-reader-meta">${escapeHtml(formatBytes(docs.find((item) => item.name === showing.name).size))} · file text</p>
        <pre class="doc-text">${showing.text ? escapeHtml(showing.text) : "This file has no extracted text."}</pre>
      </article>`
    : `<p class="kn-aside-note">Select a source to read the text stored for that file. Chunks are built at retrieve time and are not listed here.</p>`;
  const sources = docs.length
    ? `<table class="kn-table">
        <thead><tr><th>Name</th><th>Type</th><th>Size</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`
    : `<div class="kn-empty">
        <h2>No sources yet</h2>
        <p>${writable ? "Add documents this system is allowed to retrieve from." : "This demo is read-only. Create a system to upload files."}</p>
        ${writable ? dropzone : ""}
      </div>`;
  knowledge.innerHTML = `<div class="kn-page">
    <header class="kn-head">
      <div>
        <h1>Data</h1>
        <p>What this RAG system can retrieve from.</p>
      </div>
      ${
        writable
          ? `<button type="button" class="primary" id="kn-add-source">${icon("plus", 14)} Add source</button>`
          : ""
      }
    </header>
    ${
      writable
        ? ""
        : `<p class="kn-readonly">This demo is read-only. Create a system to upload and remove files.</p>`
    }
    <dl class="kn-summary">
      <div><dt>Sources</dt><dd>${docs.length}</dd></div>
      <div><dt>Total size</dt><dd>${escapeHtml(formatBytes(total))}</dd></div>
      <div><dt>Accepted formats</dt><dd>TXT · PDF</dd></div>
    </dl>
    <div class="kn-grid${docs.length ? "" : " is-empty"}">
      <section class="kn-sources" aria-label="Sources">
        <h2>Sources</h2>
        ${sources}
        ${docs.length && dropzone ? dropzone : ""}
      </section>
      ${
        docs.length
          ? `<aside class="kn-side" aria-label="Source text">
              <h2>Source text</h2>
              ${reader}
            </aside>`
          : ""
      }
    </div>
    <section class="kn-settings">
      <h2>System</h2>
      <p>The name is chosen when the system is created. This page cannot rename it.</p>
      <dl class="kn-summary kn-id">
        <div><dt>Name</dt><dd>${escapeHtml(label)}</dd></div>
        <div><dt>Id</dt><dd class="kn-mono">${escapeHtml(workspaceId)}</dd></div>
      </dl>
      <form class="project-form" id="pg-project-form">
        <label for="pg-project-name">New system</label>
        <input id="pg-project-name" maxlength="80" placeholder="Name" aria-label="New system name" />
        <button type="submit" class="ghost">Create</button>
      </form>
    </section>
    ${
      writable
        ? `<section class="kn-danger">
            <h2>Danger zone</h2>
            <div>
              <b>Delete system</b>
              <p>Permanently delete ${escapeHtml(label)} and its documents. You will be asked to confirm.</p>
            </div>
            <button type="button" class="ghost danger" id="pg-delete-project">Delete system</button>
          </section>`
        : ""
    }
  </div>`;
}

function agentSourceCount() {
  if (Array.isArray(state.documents)) return state.documents.length;
  const count = state.meta && state.meta.doc_count;
  return typeof count === "number" ? count : 0;
}

function agentStageFlags() {
  const mode = currentPlaygroundMode();
  const loop = mode === "loop" || mode === "loop_confirm";
  return {
    retrieve: true,
    generate: mode !== "retrieve_only",
    judge: loop,
    recover: loop,
    verify: loop,
  };
}

function agentDirty() {
  const saved = state.savedAgent || {};
  const model = ($("pg-chat-model") && $("pg-chat-model").value) || state.draftConfig.chat_model;
  const topField = $("pg-config-top-k");
  const parsed = topField ? Number(topField.value) : Number(state.draftConfig.top_k);
  const top = Number.isInteger(parsed) && parsed >= 1 && parsed <= 20 ? parsed : Number(saved.top_k) || 4;
  const instructions = state.agentBehavior && state.agentBehavior.mode === "raw" && $("pg-instructions")
    ? $("pg-instructions").value
    : state.draftConfig.instructions || "";
  return instructions !== (saved.instructions || "")
    || model !== (saved.chat_model || "gpt-4o-mini")
    || top !== (Number(saved.top_k) || 4)
    || (state.draftConfig.recovery_policy || "v1") !== (saved.recovery_policy || "v1")
    || !AgentConfig.sameBehavior(state.agentBehavior, saved.behavior);
}

function syncInstructionMirrors(text) {
  const node = $("pg-node-instructions");
  if (node && document.activeElement !== node) node.value = text;
  if (typeof updateNodeSubtitle === "function") updateNodeSubtitle("instructions");
}

function commitBehavior(next) {
  state.agentUi.editingRule = null;
  state.agentUi.ruleMenu = false;
  state.agentBehavior = AgentConfig.normalize(next);
  const text = AgentConfig.effectiveInstructions(state.agentBehavior, state.draftConfig.instructions);
  state.draftConfig.instructions = text;
  state.draftConfig.behavior = AgentConfig.serialize(state.agentBehavior);
  syncInstructionMirrors(text);
  renderAgent();
}

function adoptRawInstructions(text, force) {
  const current = state.agentBehavior
    ? AgentConfig.effectiveInstructions(state.agentBehavior, state.draftConfig.instructions)
    : state.draftConfig.instructions || "";
  if (!force && state.agentBehavior && state.agentBehavior.mode !== "raw" && text === current) {
    state.draftConfig.instructions = text;
    return;
  }
  state.agentBehavior = AgentConfig.rawBehavior();
  state.draftConfig.instructions = text;
  state.draftConfig.behavior = AgentConfig.serialize(state.agentBehavior);
  state.agentUi.advancedOpen = true;
  state.agentUi.ruleMenu = false;
  const field = $("pg-instructions");
  if (field && document.activeElement !== field) field.value = text;
  syncInstructionMirrors(text);
}

const AGENT_SUGGESTIONS = [
  { group: "Grounding", items: [
    { label: "Only answer from retrieved knowledge", apply: ["grounding", "evidence"] },
    { label: "Cite sources", apply: ["grounding", "cite"] },
    { label: "Acknowledge missing evidence", apply: ["grounding", "admit"] },
    { label: "Avoid unsupported assumptions", rule: "Do not state assumptions the retrieved evidence does not support." },
  ]},
  { group: "Response style", items: [
    { label: "Keep answers concise", apply: ["detail", "concise"] },
    { label: "Explain things step-by-step", apply: ["explanation", "step"] },
    { label: "Use bullet points when useful", apply: ["formatting", "bullets"] },
    { label: "Define technical terms", rule: "Define technical terms the first time they appear." },
    { label: "Give the direct answer first", apply: ["formatting", "summaryFirst"] },
  ]},
  { group: "Tone", items: [
    { label: "Professional", apply: ["tone", "professional"] },
    { label: "Friendly", apply: ["tone", "friendly"] },
    { label: "Casual", apply: ["tone", "casual"] },
    { label: "Academic", apply: ["tone", "academic"] },
  ]},
];

function addOwnAgentRule() {
  const field = $("agent-own-rule");
  const text = field ? field.value.trim() : "";
  if (!text) return;
  applyAgentSuggestion({ rule: text });
}

function applyAgentSuggestion(item) {
  const next = AgentConfig.clone(state.agentBehavior);
  next.mode = "guided";
  next.legacyText = null;
  if (item.rule) {
    if (!next.customRules.includes(item.rule)) next.customRules.push(item.rule);
  } else {
    const [group, value] = item.apply;
    if (group === "formatting" || group === "grounding") next[group][value] = true;
    else next[group] = value;
  }
  next.preset = AgentConfig.detectPreset(next);
  state.agentUi.ruleMenu = false;
  commitBehavior(next);
}

function setAgentChoice(group, value) {
  const next = AgentConfig.clone(state.agentBehavior);
  next.mode = "guided";
  next.legacyText = null;
  if (group === "formatting" || group === "grounding") next[group][value] = !next[group][value];
  else next[group] = next[group] === value ? "" : value;
  next.preset = AgentConfig.detectPreset(next);
  commitBehavior(next);
}

function switchAgentToRaw() {
  const text = AgentConfig.effectiveInstructions(state.agentBehavior, state.draftConfig.instructions);
  adoptRawInstructions(text, true);
  renderAgent();
  const field = $("pg-instructions");
  if (field) {
    field.value = text;
    field.focus();
  }
}

function switchAgentToGuided() {
  const text = ($("pg-instructions") && $("pg-instructions").value) || state.draftConfig.instructions || "";
  const parsed = AgentConfig.parseAgentInstructions(text);
  if (!parsed.ok) {
    const ok = window.confirm("These raw instructions can't be represented as guided settings. Keep the whole text as one custom rule? It stays exact until you change a setting.");
    if (!ok) return;
    state.agentUi.advancedOpen = true;
    commitBehavior(AgentConfig.legacyBehavior(text));
    return;
  }
  state.agentUi.advancedOpen = false;
  commitBehavior(parsed.behavior);
}

function refreshAgentChrome() {
  const status = $("agent-save-state");
  if (status) {
    const dirty = agentDirty();
    const saving = state.agentSaving;
    const failed = Boolean(state.agentSaveError) && !saving;
    status.className = `agent-state${saving ? " is-saving" : failed ? " is-failed" : dirty ? " is-dirty" : " is-clean"}`;
    status.innerHTML = saving
      ? `${icon("loader", 14)} Saving…`
      : failed
        ? `${icon("alert-circle", 14)} Save failed`
        : dirty
          ? `<span class="agent-dot" aria-hidden="true"></span> Unsaved changes`
          : `${icon("check", 14)} Saved`;
  }
  const save = $("pg-agent-save");
  if (save) {
    save.disabled = state.agentSaving;
    save.textContent = state.agentSaving ? "Saving…" : "Save";
  }
  const behavior = state.agentBehavior || AgentConfig.emptyBehavior();
  const text = behavior.mode === "raw" && $("pg-instructions")
    ? $("pg-instructions").value
    : AgentConfig.effectiveInstructions(behavior, state.draftConfig.instructions);
  const count = $("agent-count");
  if (count) count.textContent = `${text.length.toLocaleString()} / 8,000`;
  const generated = $("agent-generated");
  if (generated) generated.textContent = text.trim() ? text : "No extra instructions yet. Runs use the grounding prompt only.";
  const summary = $("agent-summary");
  if (summary) {
    summary.innerHTML = AgentConfig.summaryChips(behavior).map((chip) => `<li>${escapeHtml(chip)}</li>`).join("");
  }
  const rulesNote = $("agent-rules-note");
  if (rulesNote) {
    const countRules = (behavior.customRules || []).length;
    rulesNote.textContent = countRules ? `${countRules} saved with the instructions` : "None yet";
  }
  const modelName = ($("pg-chat-model") && $("pg-chat-model").value) || state.draftConfig.chat_model || "gpt-4o-mini";
  const topField = $("pg-config-top-k");
  const topValue = topField && topField.value ? topField.value : String(state.draftConfig.top_k || 4);
  const modelOut = $("agent-ov-model");
  if (modelOut) modelOut.textContent = modelName;
  const topOut = $("agent-ov-topk");
  if (topOut) topOut.textContent = topValue;
  const genDetail = $("agent-stage-generate");
  if (genDetail) genDetail.textContent = `${modelName} · temperature 0`;
  const mode = currentPlaygroundMode();
  const modeOut = $("agent-run-mode");
  if (modeOut && document.activeElement !== modeOut) modeOut.value = mode;
  const recoverDetail = $("agent-stage-recover");
  if (recoverDetail) {
    recoverDetail.textContent = mode === "loop_confirm" ? "Waits for you to confirm" : mode === "loop" ? "Automatic, up to 2 fixes" : "Off in this mode";
  }
  const verifyDetail = $("agent-stage-verify");
  if (verifyDetail) {
    verifyDetail.textContent = mode === "loop" || mode === "loop_confirm" ? "Judge checks the result again" : "Off in this mode";
  }
  const flags = agentStageFlags();
  document.querySelectorAll("[data-agent-stage]").forEach((node) => {
    node.classList.toggle("is-off", !flags[node.dataset.agentStage]);
  });
  const checks = $("agent-grounding");
  if (checks) {
    const rows = [
      ["evidence", "Retrieved evidence"],
      ["cite", "Cite sources"],
      ["admit", "Admit gaps"],
      ["uncertainty", "Explain uncertainty"],
    ];
    if (behavior.mode === "raw" || behavior.legacyText != null) {
      checks.innerHTML = `<p>${behavior.mode === "raw" ? "Raw instructions are saved as written." : "Existing instructions are unchanged until you edit a setting."}</p>`;
    } else {
      checks.innerHTML = rows.map(([key, label]) => {
        const on = Boolean(behavior.grounding[key]);
        return `<li class="${on ? "is-on" : ""}">${icon(on ? "check" : "minus", 14)} ${escapeHtml(label)}</li>`;
      }).join("");
    }
  }
}

function agentSeg(group, value, label, current) {
  const on = current === value ? " is-on" : "";
  const pressed = current === value ? "true" : "false";
  return `<button type="button" class="seg-btn${on}" data-choice="${group}" data-value="${value}" aria-pressed="${pressed}">${escapeHtml(label)}</button>`;
}

function agentCheck(group, key, title, detail, on) {
  return `<label class="check-row">
    <input type="checkbox" data-choice="${group}" data-value="${key}" ${on ? "checked" : ""} />
    <span><b>${escapeHtml(title)}</b><small>${escapeHtml(detail)}</small></span>
  </label>`;
}

// A built-in system cannot be edited, but its settings are still worth
// showing: the pipeline it runs, the models, and how to make an editable copy.
function agentReadOnlyHtml() {
  const meta = state.meta || {};
  const label = meta.corpus_label || "This system";
  const chat = meta.configured_chat_model || "—";
  const embed = meta.configured_embedding_model || "—";
  const docs = meta.doc_count != null ? String(meta.doc_count) : "—";
  const stage = (key, swatch, title, detail) =>
    `<li><span class="agent-swatch is-${swatch}"></span><span class="agent-pipe-copy"><b>${escapeHtml(title)}</b><small>${escapeHtml(detail)}</small></span></li>`;
  return `<div class="kn-page agent-readonly">
    <header class="kn-head">
      <div>
        <h1>Configuration</h1>
        <p>How ${escapeHtml(label)} responds. Built-in systems are read-only, so these settings are shown, not edited.</p>
      </div>
      <button type="button" class="primary" id="agent-new-workspace">${icon("plus", 14)} New system</button>
    </header>
    <div class="agent-ro-grid">
      <section class="kn-sources agent-ro-card">
        <h2>Pipeline</h2>
        <ol class="agent-pipe">
          ${stage("retrieve", "retrieval", "Retrieve", `${embed} · top 4 passages by default`)}
          ${stage("generate", "generation", "Generate", `${chat} · temperature 0`)}
          ${stage("judge", "judge", "Judge", "Evidence sufficiency and answer support, same model")}
          ${stage("recover", "recovery", "Recover", "Current v1 policy: rewrite, expand, regenerate, or abstain")}
          ${stage("verify", "success", "Verify", "Compares the judge flags before and after recovery")}
        </ol>
      </section>
      <section class="kn-sources agent-ro-card">
        <h2>Settings</h2>
        <dl class="tc-facts-grid">
          <div><dt>Chat model</dt><dd>${escapeHtml(chat)}</dd></div>
          <div><dt>Embedding</dt><dd>${escapeHtml(embed)}</dd></div>
          <div><dt>Sources</dt><dd><a href="#data">${escapeHtml(docs)} documents</a></dd></div>
          <div><dt>Domain</dt><dd>${escapeHtml(meta.corpus_industry || "—")}</dd></div>
          <div><dt>Instructions</dt><dd>Grounding rules only</dd></div>
          <div><dt>Recovery policy</dt><dd>Current v1</dd></div>
        </dl>
      </section>
      <section class="kn-sources agent-ro-card agent-ro-next">
        <h2>Make an editable system</h2>
        <ol class="agent-ro-steps">
          <li><b>Create a system</b><span>Give it a name. It starts empty and fully editable.</span></li>
          <li><b>Add sources</b><span>Upload TXT or PDF notes under Data.</span></li>
          <li><b>Set how it responds</b><span>Tone, detail, grounding rules, model, and retrieval depth.</span></li>
          <li><b>Test the loop</b><span>Run questions in Test Console and watch recovery work.</span></li>
        </ol>
      </section>
    </div>
  </div>`;
}

function renderAgent() {
  const root = $("pg-agent");
  if (!root) return;
  const writable = Boolean(state.meta && state.meta.writable);
  if (!writable) {
    root.innerHTML = agentReadOnlyHtml();
    return;
  }
  if (!state.agentBehavior) state.agentBehavior = AgentConfig.hydrate(null, state.draftConfig.instructions || "");
  const behavior = state.agentBehavior;
  const guided = behavior.mode !== "raw";
  const presetOptions = Object.entries(AgentConfig.PRESETS).map(([id, preset]) => {
    const selected = id === (behavior.preset || "custom") ? " selected" : "";
    return `<option value="${id}"${selected}>${escapeHtml(preset.label)}</option>`;
  }).join("");
  const preset = AgentConfig.PRESETS[behavior.preset] || AgentConfig.PRESETS.custom;
  const model = state.draftConfig.chat_model || "gpt-4o-mini";
  const modelOptions = CHAT_MODELS.map((item) => `<option value="${escapeHtml(item)}"${item === model ? " selected" : ""}>${escapeHtml(item)}</option>`).join("");
  const topK = String(state.draftConfig.top_k || 4);
  const embed = (state.meta && state.meta.configured_embedding_model) || "In-memory index";
  const label = (state.meta && state.meta.corpus_label) || "Workspace";
  const sources = agentSourceCount();
  const sourceNames = (state.documents || []).slice(0, 3).map((item) => item.name).filter(Boolean);
  const sourceDetail = sourceNames.length
    ? escapeHtml(sourceNames.join(", ")) + ((state.documents || []).length > 3 ? ` +${state.documents.length - 3}` : "")
    : "No documents yet";
  const mode = currentPlaygroundMode();
  const modeOptions = [
    ["loop", "Loop · auto recover"],
    ["loop_confirm", "Loop · confirm recovery"],
    ["baseline", "Baseline RAG"],
    ["retrieve_only", "Retrieve only"],
  ].map(([value, text]) => `<option value="${value}"${value === mode ? " selected" : ""}>${text}</option>`).join("");
  const legacy = guided && behavior.legacyText != null
    ? `<p class="agent-legacy">These instructions were already saved as free text. They stay exactly as written until you change a setting. The text is kept below as a custom rule.</p>`
    : "";
  const toneRow = ["professional", "friendly", "casual", "academic", "custom"]
    .map((value) => agentSeg("tone", value, value === "custom" ? "Custom" : value[0].toUpperCase() + value.slice(1), behavior.tone))
    .join("");
  const detailRow = ["concise", "balanced", "detailed"]
    .map((value) => agentSeg("detail", value, value[0].toUpperCase() + value.slice(1), behavior.detail))
    .join("");
  const explainRow = [["direct", "Direct"], ["step", "Step-by-step"], ["explanatory", "Explanatory"]]
    .map(([value, name]) => agentSeg("explanation", value, name, behavior.explanation))
    .join("");
  const customTone = behavior.tone === "custom"
    ? `<label class="agent-field agent-custom-tone"><span>Custom tone</span><input id="agent-custom-tone" maxlength="240" value="${escapeHtml(behavior.customTone)}" placeholder="Short description, such as warm and direct" /></label>`
    : "";
  const rules = behavior.customRules.map((rule, index) => {
    if (state.agentUi.editingRule === index) {
      return `<li class="agent-rule is-editing">
        <textarea id="agent-rule-draft" rows="2" maxlength="2000">${escapeHtml(rule)}</textarea>
        <button type="button" class="primary" data-rule-done="${index}">Done</button>
      </li>`;
    }
    return `<li class="agent-rule">
      <p>${escapeHtml(rule)}</p>
      <span class="agent-rule-actions">
        <button type="button" data-rule-up="${index}" aria-label="Move rule up" ${index === 0 ? "disabled" : ""}>${icon("arrow-up", 14)}</button>
        <button type="button" data-rule-down="${index}" aria-label="Move rule down" ${index === behavior.customRules.length - 1 ? "disabled" : ""}>${icon("arrow-down", 14)}</button>
        <button type="button" data-rule-edit="${index}">Edit</button>
        <button type="button" data-rule-del="${index}" aria-label="Remove rule">${icon("x", 14)}</button>
      </span>
    </li>`;
  }).join("");
  const suggestionGroups = AGENT_SUGGESTIONS.map((group) => {
    const items = group.items.map((item, index) => `<button type="button" data-suggestion="${group.group}:${index}">${escapeHtml(item.label)}</button>`).join("");
    return `<div class="agent-suggest-group"><div>${escapeHtml(group.group)}</div>${items}</div>`;
  }).join("");
  const guidedBody = `<section class="agent-section">
      <h2>Start with a template</h2>
      <p class="agent-section-lead">A template fills in tone, detail, and grounding. It does not change the model, and you can edit every choice after.</p>
      <label class="agent-field">
        <span class="sr-only">Template</span>
        <select id="agent-preset">${presetOptions}</select>
        <small id="agent-preset-blurb">${escapeHtml(behavior.legacyText != null ? "Existing free text is kept as a custom rule." : preset.blurb)}</small>
      </label>
    </section>
    <section class="agent-section">
      <h2>Response behavior</h2>
      <div class="agent-setting">
        <div class="agent-setting-label">Tone</div>
        <div class="seg" role="group" aria-label="Tone">${toneRow}</div>
        ${customTone}
      </div>
      <div class="agent-setting">
        <div class="agent-setting-label">Detail</div>
        <div class="seg" role="group" aria-label="Response detail">${detailRow}</div>
      </div>
      <div class="agent-setting">
        <div class="agent-setting-label">Explanation</div>
        <div class="seg" role="group" aria-label="Explanation style">${explainRow}</div>
      </div>
      <div class="agent-setting">
        <div class="agent-setting-label">Formatting</div>
        <div class="check-list">
          ${agentCheck("formatting", "bullets", "Bullet points when useful", "Use bullets when a list is easier to scan.", behavior.formatting.bullets)}
          ${agentCheck("formatting", "numbered", "Numbered steps for procedures", "Ask for numbered steps when the question is a procedure.", behavior.formatting.numbered)}
          ${agentCheck("formatting", "tables", "Tables for comparisons", "Ask for a table when the answer is comparing items.", behavior.formatting.tables)}
          ${agentCheck("formatting", "summaryFirst", "Short answer first", "Lead with the answer, then the detail.", behavior.formatting.summaryFirst)}
        </div>
      </div>
    </section>
    <section class="agent-section">
      <h2>Grounding</h2>
      <p class="agent-section-lead">These are instructions to the model. The judge still checks whether an answer is backed by the passages. They are not a guarantee the model will comply.</p>
      <div class="check-list">
        ${agentCheck("grounding", "evidence", "Base claims on retrieved evidence", "Prefer retrieved sources over unsupported claims.", behavior.grounding.evidence)}
        ${agentCheck("grounding", "cite", "Cite supporting sources", "Cite a source when an answer uses a retrieved document.", behavior.grounding.cite)}
        ${agentCheck("grounding", "admit", "Admit when evidence is not enough", "Say so when the retrieved sources do not contain the answer.", behavior.grounding.admit)}
        ${agentCheck("grounding", "uncertainty", "Explain uncertainty", "Say briefly why the evidence may be incomplete or ambiguous.", behavior.grounding.uncertainty)}
      </div>
    </section>
    <section class="agent-section">
      <div class="agent-section-head">
        <h2>Custom rules</h2>
        <button type="button" class="ghost" id="agent-add-rule" aria-expanded="${state.agentUi.ruleMenu ? "true" : "false"}">${icon("plus", 14)} Add rule</button>
      </div>
      ${state.agentUi.ruleMenu ? `<div class="agent-suggest" id="agent-rule-menu">
        ${suggestionGroups}
        <div class="agent-suggest-own">
          <label class="sr-only" for="agent-own-rule">Your rule</label>
          <input id="agent-own-rule" maxlength="2000" placeholder="Write my own rule…" />
          <button type="button" class="primary" id="agent-own-add">Add</button>
        </div>
      </div>` : ""}
      ${rules ? `<ul class="agent-rules">${rules}</ul>` : `<p class="agent-empty-rules">No custom rules. The choices above are the whole instruction.</p>`}
    </section>`;
  const rawBody = `<section class="agent-section">
      <h2>Raw instructions</h2>
      <p class="agent-section-lead">This text is what gets saved. Guided settings will not change it until you switch back.</p>
      <div class="agent-editor">
        <div class="agent-editor-bar"><span>Saved on the project</span><span id="agent-count"></span></div>
        <label class="sr-only" for="pg-instructions">Raw instructions</label>
        <textarea id="pg-instructions" maxlength="8000">${escapeHtml(state.draftConfig.instructions || "")}</textarea>
      </div>
      <button type="button" class="ghost" id="agent-use-guided">Switch to guided settings</button>
    </section>`;
  const instructionsField = guided
    ? `<textarea id="pg-instructions" class="sr-only" tabindex="-1" readonly aria-hidden="true">${escapeHtml(AgentConfig.effectiveInstructions(behavior, state.draftConfig.instructions))}</textarea>`
    : "";
  root.innerHTML = `<div class="agent-studio">
    <form class="pg-config agent-main" id="pg-config-form">
      <header class="agent-head">
        <div class="agent-head-row">
          <div>
            <h1>Configuration</h1>
            <p>How this system responds: response behavior, grounding, retrieval defaults, and the model. Recovery policy is an explicit choice. The default is current v1.</p>
          </div>
          <div class="agent-save">
            <span class="agent-state is-clean" id="agent-save-state"></span>
            <button type="submit" class="primary" id="pg-agent-save">Save</button>
          </div>
        </div>
      </header>
      ${legacy}
      ${guided ? guidedBody : rawBody}
      ${instructionsField}
      <section class="agent-section">
        <h2>Retrieval and model</h2>
        <div class="agent-fields">
          <label class="agent-field">
            <span>Model</span>
            <select id="pg-chat-model">${modelOptions}</select>
            <small>Used for generation, the judge, and recovery.</small>
          </label>
          <label class="agent-field">
            <span>Recovery policy</span>
            <select id="pg-config-policy">
              <option value="v1"${(state.draftConfig.recovery_policy || "v1") === "v1" ? " selected" : ""}>Current v1</option>
              <option value="gap_aware"${state.draftConfig.recovery_policy === "gap_aware" ? " selected" : ""}>Gap-aware (Guarded)</option>
            </select>
            <small>Guarded gap-aware recovery is opt-in. It is not the default. Retrieve-only and baseline runs do not apply it.</small>
          </label>
          <label class="agent-field">
            <span>Default top_k</span>
            <input id="pg-config-top-k" type="number" min="1" max="20" step="1" value="${escapeHtml(topK)}" />
            <small>Passages retrieved, unless a Test Console run overrides it.</small>
          </label>
          <div class="agent-fixed">
            <span>Temperature</span>
            <b>0</b>
            <small>Fixed for generation, the judge, and recovery.</small>
          </div>
          <div class="agent-fixed">
            <span>Embedding</span>
            <b>${escapeHtml(embed)}</b>
            <small>Fixed for this server. Retrieval uses it to rank passages.</small>
          </div>
        </div>
      </section>
      <section class="agent-section">
        <button type="button" class="agent-advanced-toggle" id="agent-advanced-toggle" aria-expanded="${state.agentUi.advancedOpen ? "true" : "false"}">
          ${icon(state.agentUi.advancedOpen ? "chevron-down" : "chevron-right", 16)}
          Advanced · generated instructions
        </button>
        ${state.agentUi.advancedOpen ? `<div class="agent-raw">
          <p>This is the instruction text the next saved run will prepend to the grounding prompt. The grounding rules still come first and cannot be removed.</p>
          <pre id="agent-generated"></pre>
          <div class="agent-raw-actions">
            <button type="button" class="ghost" id="agent-copy">${icon("copy", 14)} Copy</button>
            ${guided ? `<button type="button" class="ghost" id="agent-edit-raw">Edit raw instructions</button>` : ""}
          </div>
        </div>` : `<pre id="agent-generated" class="sr-only"></pre>`}
      </section>
    </form>
    <aside class="agent-side" aria-label="Current settings">
      <div class="agent-kicker">Current settings</div>
      <h2>${escapeHtml(label)}</h2>
      <p class="agent-side-lead">A loop run retrieves, generates, then judges. Recovery runs only when the judge or the retrieval signal asks for it.</p>
      <ol class="agent-pipe">
        <li data-agent-stage="retrieve"><span class="agent-swatch is-retrieval"></span><span class="agent-pipe-copy"><b>Retrieve</b><small>${escapeHtml(embed)}</small></span></li>
        <li data-agent-stage="generate"><span class="agent-swatch is-generation"></span><span class="agent-pipe-copy"><b>Generate</b><small id="agent-stage-generate"></small></span></li>
        <li data-agent-stage="judge"><span class="agent-swatch is-judge"></span><span class="agent-pipe-copy"><b>Judge</b><small>Grounding flags, same model</small></span></li>
        <li data-agent-stage="recover"><span class="agent-swatch is-recovery"></span><span class="agent-pipe-copy"><b>Recover</b><small id="agent-stage-recover"></small></span></li>
        <li data-agent-stage="verify"><span class="agent-swatch is-success"></span><span class="agent-pipe-copy"><b>Verify</b><small id="agent-stage-verify"></small></span></li>
      </ol>
      <div class="agent-overview-block">
        <div class="agent-setting-label">Current behavior</div>
        <ul class="agent-chips" id="agent-summary"></ul>
      </div>
      <div class="agent-overview-block">
        <div class="agent-setting-label">Grounding</div>
        <ul class="agent-checks" id="agent-grounding"></ul>
      </div>
      <dl class="agent-spec">
        <div><dt>Model</dt><dd id="agent-ov-model"></dd></div>
        <div><dt>Sources</dt><dd><a href="#data" id="agent-ov-sources">${sources}</a><small>${sourceDetail}</small></dd></div>
        <div><dt>Top K</dt><dd id="agent-ov-topk" class="agent-num"></dd></div>
        <div><dt>Temperature</dt><dd>0 <small>Fixed</small></dd></div>
      </dl>
      <label class="agent-field agent-mode-field">
        <span>Test Console run mode</span>
        <select id="agent-run-mode" aria-label="Test Console run mode">${modeOptions}</select>
        <small>Not saved with these settings. Test Console uses the saved instructions, not unsaved edits on this page.</small>
      </label>
      <a class="agent-playground-link" href="#test">Run a test query</a>
    </aside>
  </div>`;
  refreshAgentChrome();
  const draft = $("agent-rule-draft");
  if (draft) draft.focus();
}

function apiOrigin() {
  if (typeof location !== "undefined" && location.origin && location.origin !== "null") return location.origin;
  return "http://127.0.0.1:8000";
}

function apiExample(lang) {
  const origin = apiOrigin();
  const url = `${origin}/api/v1/evaluations`;
  const body = `{
  "query": "When is the library open?",
  "answer": "Saturday 10:00-16:00.",
  "contexts": [{ "text": "Saturday 10:00-16:00." }]
}`;
  if (lang === "js") {
    return `const response = await fetch(${JSON.stringify(url)}, {
  method: "POST",
  headers: {
    "Authorization": "Bearer swr_your_key",
    "Content-Type": "application/json"
  },
  body: JSON.stringify(${body})
});
const evaluation = await response.json();`;
  }
  if (lang === "py") {
    return `import json
import urllib.request

body = json.dumps(${body}).encode()
request = urllib.request.Request(
    ${JSON.stringify(url)},
    data=body,
    headers={
        "Authorization": "Bearer swr_your_key",
        "Content-Type": "application/json",
    },
    method="POST",
)
print(urllib.request.urlopen(request).read().decode())`;
  }
  return `curl -s ${url} \\
  -H "Authorization: Bearer swr_your_key" \\
  -H "Content-Type: application/json" \\
  -d '${body}'`;
}

function renderApiPanel() {
  const root = $("pg-api");
  if (!root) return;
  const writable = Boolean(state.meta && state.meta.writable);
  root.innerHTML = renderProjectKeys();
  if (!writable) {
    // The API reference applies to every system; only keys need one you own.
    const create = $("pg-create-key");
    if (create) create.remove();
    const keys = root.querySelector(".api-keys");
    const locked = `<section class="api-keys api-keys-locked" aria-label="API keys">
        <h2>API keys</h2>
        <p>Keys belong to a system you own. Built-in systems are read-only and cannot issue keys.</p>
        <button type="button" class="ghost" id="agent-new-workspace">${icon("plus", 14)} New system</button>
      </section>`;
    if (keys) keys.outerHTML = locked;
    else root.querySelector(".api-page")?.insertAdjacentHTML("beforeend", locked);
  }
}

function renderProjectKeys() {
  const lang = ["curl", "js", "py"].includes(state.apiLang) ? state.apiLang : "curl";
  const sample = apiExample(lang);
  const keys = state.keys || [];
  const rows = keys
    .map((item) => {
      const revoked = Boolean(item.revoked_at);
      return `<tr class="${revoked ? "is-revoked" : ""}">
        <td><code>${escapeHtml(item.prefix || item.id)}</code></td>
        <td>${escapeHtml(item.scope || "evaluations")}</td>
        <td>${escapeHtml(formatStamp(item.created_at))}</td>
        <td>${revoked ? escapeHtml(formatStamp(item.revoked_at)) : "Active"}</td>
        <td>${
          revoked
            ? ""
            : `<button type="button" class="ghost danger" data-key-revoke="${escapeHtml(item.id)}">Revoke</button>`
        }</td>
      </tr>`;
    })
    .join("");
  const revealed = state.revealedKey
    ? `<div class="api-dialog" role="dialog" aria-modal="true" aria-labelledby="api-key-title">
        <div class="api-dialog-card">
          <h2 id="api-key-title">API key created</h2>
          <p>Copy this key now. It is not stored in plaintext and will not be shown again.</p>
          <code>${escapeHtml(state.revealedKey)}</code>
          <div class="api-dialog-actions">
            <button type="button" class="primary" id="pg-copy-key">${icon("copy", 14)} Copy key</button>
            <button type="button" class="ghost" data-key-done>Done</button>
          </div>
        </div>
      </div>`
    : "";
  const tabs = [
    ["curl", "cURL"],
    ["js", "JavaScript"],
    ["py", "Python"],
  ]
    .map(
      ([id, name]) =>
        `<button type="button" class="seg-btn${lang === id ? " is-on" : ""}" data-api-lang="${id}" aria-pressed="${lang === id ? "true" : "false"}">${name}</button>`
    )
    .join("");
  return `<div class="api-page pg-keys">
    ${revealed}
    <header class="kn-head">
      <div>
        <h1>Integrations</h1>
        <p>Evaluate responses from an external RAG application. This endpoint judges the answer and contexts you send. It does not retrieve from this system, and it does not apply rewrite or expand.</p>
      </div>
      <button type="button" class="primary" id="pg-create-key">${icon("plus", 14)} Create API key</button>
    </header>
    <div class="api-grid">
      <section class="api-quick" aria-label="Quick start">
        <h2>Quick start</h2>
        <p class="api-lead"><code>POST</code> <span>/api/v1/evaluations</span></p>
        <p class="api-note">Required body fields are <code>query</code>, <code>answer</code>, and <code>contexts</code>. Each context needs <code>text</code>. Optional context fields: <code>chunk_id</code>, <code>doc_id</code>, <code>title</code>, <code>score</code>, <code>page</code>. Optional body field: <code>metadata</code>.</p>
        <div class="seg" role="tablist" aria-label="Example language">${tabs}</div>
        <div class="api-code">
          <button type="button" class="ghost" id="api-copy-sample">${icon("copy", 14)} Copy</button>
          <pre id="api-sample">${escapeHtml(sample)}</pre>
        </div>
      </section>
      <aside class="api-side" aria-label="Endpoint">
        <h2>Endpoint</h2>
        <dl>
          <div><dt>Method</dt><dd><code>POST</code> /api/v1/evaluations</dd></div>
          <div><dt>Read one run</dt><dd><code>GET</code> /api/v1/evaluations/{run_id}</dd></div>
          <div><dt>Authentication</dt><dd><code>Authorization: Bearer</code> or <code>X-Api-Key</code>. Keys start with <code>swr_</code>.</dd></div>
          <div><dt>What it does</dt><dd>Judges the answer you send against the contexts you send. It does not retrieve from this system.</dd></div>
          <div><dt>Recovery</dt><dd>Proposed, not applied. <code>recovery_status</code> is <code>proposed</code>. <code>rewrite</code> and <code>expand</code> are unavailable because they need a corpus index this endpoint does not have.</dd></div>
        </dl>
        <h3>Response shape</h3>
        <p class="api-note">These are the fields the endpoint returns. The values are illustrative, not a live run.</p>
        <pre class="api-shape">{
  "run_id": "string",
  "project_id": "string",
  "answer": "string",
  "evaluation": {
    "evidence_sufficient": true,
    "answer_supported": true,
    "sufficiency_rationale": "string",
    "support_rationale": "string",
    "judge": "string",
    "model": "string"
  },
  "diagnosis": {
    "failure_class": null,
    "rationale": "string",
    "detector": "first-pass-runtime"
  },
  "retrieval_signal": {
    "top_score": null,
    "runner_up_score": null,
    "relative_margin": null,
    "weak_top": false,
    "ambiguous_top": false,
    "reason": "string",
    "detector": "retrieval-score"
  },
  "recovery": {
    "action": "accept",
    "reason": "string",
    "attributed_class": null,
    "source": "policy",
    "outcome_note": "",
    "trigger": "string"
  },
  "recovery_status": "proposed",
  "unavailable_actions": {
    "rewrite": "rewrite needs a corpus index; this evaluation was submitted without one",
    "expand": "expand needs a corpus index; this evaluation was submitted without one"
  },
  "note": "Recovery is proposed, not applied. rewrite and expand need a corpus index this endpoint does not have."
}</pre>
      </aside>
    </div>
    <section class="api-keys" aria-label="API keys">
      <h2>API keys</h2>
      ${
        rows
          ? `<table class="kn-table">
              <thead><tr><th>Prefix</th><th>Scope</th><th>Created</th><th>Status</th><th></th></tr></thead>
              <tbody>${rows}</tbody>
            </table>`
          : `<div class="kn-empty">
              <h2>No API keys yet</h2>
              <p>Create a key to authenticate external evaluation requests.</p>
              <button type="button" class="primary" data-create-key>${icon("plus", 14)} Create API key</button>
            </div>`
      }
    </section>
  </div>`;
}

function renderPlaygroundChat() {
  const transcript = $("pg-transcript");
  if (!transcript) return;
  if (!state.messages.length && !state.loading) {
    transcript.innerHTML = `<div class="empty"><strong>Run a test query</strong>The trace shows what the system retrieved, answered, and verified.</div>`;
    return;
  }
  const rows = state.messages.map((item) => {
    if (item.role === "user") {
      return `<div class="pg-msg user"><div class="who">You</div>${escapeHtml(item.text)}</div>`;
    }
    const parsed = formatAnswerHtml(item.text || "(empty)");
    return `<div class="pg-msg"><div class="who">${item.error ? "Error" : "Result"}</div><div class="block">${parsed.html}</div></div>`;
  });
  if (state.loading) {
    rows.push(`<div class="pg-msg"><div class="who">Result</div>Retrieving and evaluating…</div>`);
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
  state.flightTraces = null;
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
  if (mode === "loop") return "Auto recovery";
  if (mode === "loop_confirm") return "Confirm recovery";
  if (mode === "baseline") return "Baseline";
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
      meta: (state.meta && state.meta.corpus_industry) || (state.meta && state.meta.writable ? "Project" : "Read-only system"),
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

function gridSpec() {
  const canvas = $("pg-canvas");
  const avail = Math.max(NODE_W, (canvas ? canvas.clientWidth : 640) - 48);
  const gapX = 36;
  const cols = Math.max(1, Math.floor((avail + gapX) / (NODE_W + gapX)));
  return { cols, gapX, gapY: 36 };
}

function cellFor(index, grid) {
  const col = index % grid.cols;
  const row = Math.floor(index / grid.cols);
  return {
    x: 16 + col * (NODE_W + grid.gapX),
    y: 24 + row * (NODE_H + grid.gapY),
  };
}

function ensurePositions(ids) {
  const missing = ids.filter((id) => !canvasState.positions[id]);
  if (!missing.length) return;
  const canvas = $("pg-canvas");
  if (missing.length === ids.length && canvas && canvas.clientWidth < 40) return;
  const grid = gridSpec();
  if (missing.length === ids.length) {
    ids.forEach((id, index) => {
      canvasState.positions[id] = cellFor(index, grid);
    });
    return;
  }
  let next = ids.length - missing.length;
  missing.forEach((id) => {
    canvasState.positions[id] = cellFor(next, grid);
    next += 1;
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
    <p class="palette-note">These blocks match the test mode. Adding one switches the mode for the next query.</p>
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
  const fmt = (n) => Number(n).toFixed(1);
  const dx = x2 - x1;
  const dy = y2 - y1;
  if (Math.abs(dy) < 20 && dx > 24) {
    const bend = Math.max(32, dx * 0.42);
    return `M ${fmt(x1)} ${fmt(y1)} C ${fmt(x1 + bend)} ${fmt(y1)}, ${fmt(x2 - bend)} ${fmt(y2)}, ${fmt(x2)} ${fmt(y2)}`;
  }
  if (dy > 24 && dx < -24) {
    const wrapped = wrapEdge(x1, y1, x2, y2);
    if (wrapped) return wrapped;
  }
  const bend = Math.max(40, Math.hypot(dx, dy) * 0.35);
  return `M ${fmt(x1)} ${fmt(y1)} C ${fmt(x1 + bend)} ${fmt(y1)}, ${fmt(x2 - bend)} ${fmt(y2)}, ${fmt(x2)} ${fmt(y2)}`;
}

function wrapEdge(x1, y1, x2, y2) {
  const fmt = (n) => Number(n).toFixed(1);
  const outX = x1 + 22;
  const inX = x2 - 22;
  const midY = (y1 + y2) / 2;
  const radius = 12;
  if (midY - radius < y1 + radius + 4 || y2 - radius < midY + radius + 4) return "";
  if (outX - radius <= x1 || inX + radius >= x2) return "";
  return [
    `M ${fmt(x1)} ${fmt(y1)}`,
    `H ${fmt(outX - radius)}`,
    `Q ${fmt(outX)} ${fmt(y1)} ${fmt(outX)} ${fmt(y1 + radius)}`,
    `V ${fmt(midY - radius)}`,
    `Q ${fmt(outX)} ${fmt(midY)} ${fmt(outX - radius)} ${fmt(midY)}`,
    `H ${fmt(inX + radius)}`,
    `Q ${fmt(inX)} ${fmt(midY)} ${fmt(inX)} ${fmt(midY + radius)}`,
    `V ${fmt(y2 - radius)}`,
    `Q ${fmt(inX)} ${fmt(y2)} ${fmt(inX + radius)} ${fmt(y2)}`,
    `H ${fmt(x2)}`,
  ].join(" ");
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
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  stages.forEach((id) => {
    const pos = canvasState.positions[id];
    if (!pos) return;
    minX = Math.min(minX, pos.x);
    minY = Math.min(minY, pos.y);
    maxX = Math.max(maxX, pos.x + NODE_W);
    maxY = Math.max(maxY, pos.y + NODE_H);
  });
  if (!Number.isFinite(minX)) return;
  const boundsW = maxX - minX;
  const boundsH = maxY - minY;
  canvasState.zoom = 1;
  canvasState.pan.x = Math.max(16, (canvas.clientWidth - boundsW) / 2 - minX);
  const extraY = canvas.clientHeight - boundsH;
  canvasState.pan.y = extraY > 48 ? extraY / 2 - minY : 24 - minY;
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
  if (!root || !title || !$("pg-canvas")) return;
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
    ? "Add .txt or .pdf files on the Data page. The next query retrieves from them."
    : "Create a system to upload files.";
  return `<p class="recover-note">${note}</p>
    ${names ? `<ul class="doc-list">${names}</ul>` : `<div class="empty">No documents yet.</div>`}`;
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
    return `<p class="recover-note">This system uses the grounding prompt. Create a system to write instructions. Saved instructions are prepended and still cannot invent facts.</p>`;
  }
  return `<label class="sr-only" for="pg-node-instructions">Instructions</label>
    <textarea id="pg-node-instructions" maxlength="8000" placeholder="How this system should answer, on top of grounding.">${escapeHtml(state.draftConfig.instructions || "")}</textarea>
    <p class="recover-note">Save to prepend this text to the grounding prompt on the next run.</p>
    <button type="button" class="ghost" id="pg-node-save">Save configuration</button>`;
}

function modelInspector() {
  const model = activeChatModel();
  if (!writableProject()) {
    return `<p class="recover-note">This system uses ${escapeHtml(model)}. Temperature is 0 for generation, the judge, and recovery. Create a system to choose another allowed model.</p>`;
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
  if (instructions) adoptRawInstructions(instructions.value);
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
    if (event.target.id === "pg-node-instructions") adoptRawInstructions(event.target.value);
  });
  window.addEventListener("keydown", (event) => {
    if (state.view !== "test") return;
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
  const overview = $("overview-body");
  if (overview) {
    overview.addEventListener("click", (event) => {
      const button = event.target.closest("[data-inspect-run]");
      if (!button) return;
      inspectOverviewRun(button.dataset.inspectRun).catch((error) => showError(error.message));
    });
  }
  const runBtn = $("run-btn");
  if (runBtn) runBtn.addEventListener("click", runQuestion);
  const refreshRuns = $("refresh-runs");
  if (refreshRuns) refreshRuns.addEventListener("click", () => loadTraces().catch((error) => showError(error.message)));
  const deleteAll = $("delete-all-runs");
  if (deleteAll) deleteAll.addEventListener("click", () => deleteAllRuns().catch((error) => showError(error.message)));
  $("corpus").addEventListener("change", (event) => {
    const chosen = state.corpora.find((item) => item.id === event.target.value);
    state.keepReadOnly = Boolean(chosen && !chosen.writable);
    switchCorpus(event.target.value).catch((error) => showError(error.message));
  });
  const question = $("question");
  if (question) {
    question.addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        runQuestion();
      }
    });
  }
  const chips = $("example-chips");
  if (chips) {
    chips.addEventListener("click", (event) => {
      const button = event.target.closest(".chip");
      if (!button || !question) return;
      question.value = button.dataset.q;
      question.focus();
    });
  }
  const runList = $("run-list");
  if (runList) {
    runList.addEventListener("click", (event) => {
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
  }
  const relSearch = $("rel-search");
  if (relSearch) {
    relSearch.addEventListener("input", () => {
      state.relFilters.query = relSearch.value;
      renderReliability();
    });
  }
    ["rel-verification", "rel-recovery", "rel-action", "rel-diagnosis", "rel-policy"].forEach((id) => {
    const field = $(id);
    if (!field) return;
    field.addEventListener("change", () => {
      const key = id.replace("rel-", "");
      state.relFilters[key] = field.value;
      renderReliability();
    });
  });
  $("view-evaluation").querySelector(".eval-tabs").addEventListener("keydown", (event) => {
    const tabs = window.ReliabilityView.RELIABILITY_TABS;
    if (!event.target.closest("[data-eval-tab]")) return;
    const index = tabs.indexOf(state.evalTab);
    let next = null;
    if (event.key === "ArrowRight") next = tabs[(index + 1) % tabs.length];
    else if (event.key === "ArrowLeft") next = tabs[(index - 1 + tabs.length) % tabs.length];
    else if (event.key === "Home") next = tabs[0];
    else if (event.key === "End") next = tabs[tabs.length - 1];
    if (!next) return;
    event.preventDefault();
    setEvalTab(next);
    $("view-evaluation").querySelector(`[data-eval-tab="${next}"]`)?.focus();
  });
  $("view-evaluation").addEventListener("click", (event) => {
    const tab = event.target.closest("[data-eval-tab]");
    if (tab) {
      setEvalTab(tab.dataset.evalTab);
      return;
    }
    const preset = event.target.closest("[data-rel-preset]");
    if (preset) {
      applyRelPreset(preset.dataset.relPreset, preset.dataset.relValue);
      return;
    }
    const open = event.target.closest("[data-rel-open]");
    if (open) {
      inspectOverviewRun(open.dataset.relOpen).catch((error) => showError(error.message));
      return;
    }
    const review = event.target.closest("[data-rel-console]");
    if (review) {
      const row = (state.logicalRuns || []).find((item) => item.logical_run_id === review.dataset.relConsole);
      if (row) {
        openFlight(row.trace_ids || [row.logical_run_id], {
          stepsFor: row.inspect_run_id || row.logical_run_id,
        }).catch((error) => showError(error.message));
      }
      return;
    }
    const remove = event.target.closest("[data-rel-delete]");
    if (remove) {
      deleteRun(remove.dataset.relDelete).catch((error) => showError(error.message));
      return;
    }
    const runView = event.target.closest("[data-run-view]");
    if (runView) {
      state.runView = runView.dataset.runView;
      renderRunView();
      return;
    }
    const claims = event.target.closest("[data-rel-claims]");
    if (claims) {
      showStoredQuality(claims.dataset.relClaims).catch((error) => showError(error.message));
      return;
    }
    const scoreOne = event.target.closest("[data-score-run-id]");
    if (scoreOne) {
      scoreRun(scoreOne.dataset.scoreRunId);
      return;
    }
    if (event.target.closest("[data-score-run]")) {
      if (state.trace) scoreRun(String(state.trace.run_id));
      return;
    }
    if (event.target.closest("[data-score-all]")) {
      scoreAllRuns();
      return;
    }
    const bar = event.target.closest("[data-chart-run]");
    if (!bar) return;
    inspectOverviewRun(bar.dataset.chartRun).catch((error) => showError(error.message));
  });
  const waterfall = $("waterfall");
  if (waterfall) {
    waterfall.addEventListener("click", (event) => {
      const button = event.target.closest(".step-btn");
      if (!button) return;
      state.selectedStep = state.steps.find((step) => step.id === button.dataset.step) || null;
      render();
    });
  }
  const recoverBar = $("recover-bar");
  if (recoverBar) {
    recoverBar.addEventListener("click", (event) => {
      const openChild = event.target.closest("[data-open-child]");
      if (openChild) {
        selectRun(openChild.dataset.openChild).catch((error) => showError(error.message));
        return;
      }
      const recover = event.target.closest("[data-recover]");
      if (!recover) return;
      applyRecovery(recover.dataset.recover).catch((error) => showError(error.message));
    });
  }
  const answerText = $("answer-text");
  if (answerText) {
    answerText.addEventListener("click", (event) => {
      const cite = event.target.closest("button.cite");
      if (!cite) return;
      selectCitation(cite.dataset.chunkId, cite.dataset.citePass || null);
    });
  }
  const inspector = $("inspector");
  if (inspector) {
    inspector.addEventListener("click", (event) => {
      const cite = event.target.closest("button.cite");
      if (!cite) return;
      selectCitation(cite.dataset.chunkId, cite.dataset.citePass || null);
    });
  }
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
  const collapse = $("pg-collapse");
  if (collapse) {
    collapse.addEventListener("click", () => {
      state.inspectCollapsed = !state.inspectCollapsed;
      applyView();
    });
  }
  const blocks = $("pg-blocks-toggle");
  if (blocks) {
    blocks.addEventListener("click", () => {
      state.libraryCollapsed = !state.libraryCollapsed;
      applyView();
      window.setTimeout(() => frameCanvas(), 260);
    });
  }
  $("new-workspace").addEventListener("click", () => {
    const form = $("new-workspace-form");
    form.hidden = !form.hidden;
    if (!form.hidden) $("new-workspace-name").focus();
  });
  $("nav-collapse").addEventListener("click", () => setNavCollapsed(!state.navCollapsed));
  document.getElementById("app").addEventListener("submit", (event) => {
    const configForm = event.target.closest("#pg-config-form");
    if (configForm) {
      event.preventDefault();
      if (state.agentSaving) return;
      const ownRule = document.activeElement && document.activeElement.id === "agent-own-rule";
      if (ownRule) {
        addOwnAgentRule();
        return;
      }
      state.agentUi.editingRule = null;
      captureDraftConfig();
      state.agentSaving = true;
      state.agentSaveError = false;
      refreshAgentChrome();
      savePlaygroundConfig()
        .then(() => {
          state.agentSaveError = false;
        })
        .catch((error) => {
          state.agentSaveError = true;
          showError(error.message);
        })
        .finally(() => {
          state.agentSaving = false;
          refreshAgentChrome();
        });
      return;
    }
    const sidebarForm = event.target.closest("#new-workspace-form");
    const knowledgeForm = event.target.closest("#pg-project-form");
    const form = sidebarForm || knowledgeForm;
    if (!form) return;
    event.preventDefault();
    const input = sidebarForm ? $("new-workspace-name") : $("pg-project-name");
    const name = input.value.trim();
    if (!name) {
      showError("Name the system first.");
      return;
    }
    createPlaygroundProject(name)
      .then(() => {
        input.value = "";
        if (sidebarForm) sidebarForm.hidden = true;
      })
      .catch((error) => showError(error.message));
  });
  document.getElementById("app").addEventListener("focusout", (event) => {
    if (event.target.id !== "agent-rule-draft") return;
    const next = event.relatedTarget;
    if (next && next.closest && next.closest(".agent-rule.is-editing")) return;
    if (state.agentUi.editingRule == null) return;
    state.agentUi.editingRule = null;
    commitBehavior(state.agentBehavior);
  });
  document.getElementById("app").addEventListener("input", (event) => {
    if (event.target.id === "agent-custom-tone") {
      const next = AgentConfig.clone(state.agentBehavior);
      next.mode = "guided";
      next.legacyText = null;
      next.tone = "custom";
      next.customTone = event.target.value;
      next.preset = AgentConfig.detectPreset(next);
      state.agentBehavior = next;
      const text = AgentConfig.effectiveInstructions(next, "");
      state.draftConfig.instructions = text;
      state.draftConfig.behavior = AgentConfig.serialize(next);
      const hidden = $("pg-instructions");
      if (hidden) hidden.value = text;
      syncInstructionMirrors(text);
      refreshAgentChrome();
      return;
    }
    if (event.target.id === "agent-rule-draft") {
      const index = state.agentUi.editingRule;
      if (index == null || !state.agentBehavior) return;
      state.agentBehavior.customRules[index] = event.target.value;
      state.agentBehavior.legacyText = null;
      state.agentBehavior.mode = "guided";
      const text = AgentConfig.buildAgentInstructions(state.agentBehavior);
      state.draftConfig.instructions = text;
      const hidden = $("pg-instructions");
      if (hidden) hidden.value = text;
      refreshAgentChrome();
      return;
    }
    if (!["pg-instructions", "pg-chat-model", "pg-config-top-k", "pg-config-policy"].includes(event.target.id)) return;
    captureDraftConfig();
    refreshAgentChrome();
  });
  document.getElementById("app").addEventListener("change", (event) => {
    if (event.target.id === "agent-preset") {
      state.agentUi.ruleMenu = false;
      state.agentUi.editingRule = null;
      commitBehavior(AgentConfig.applyPreset(state.agentBehavior, event.target.value));
      return;
    }
    if (event.target.matches("input[data-choice]")) {
      setAgentChoice(event.target.dataset.choice, event.target.dataset.value);
      return;
    }
    if (event.target.id === "pg-chat-model" || event.target.id === "pg-config-top-k" || event.target.id === "pg-config-policy") {
      captureDraftConfig();
      refreshAgentChrome();
      return;
    }
    if (event.target.id === "pg-recovery-policy") {
      if (state.draftConfig) state.draftConfig.recovery_policy = selectedRecoveryPolicy();
      syncPolicyNote();
      return;
    }
    if (event.target.id === "agent-run-mode") {
      const mode = $("pg-mode");
      if (mode && mode.value !== event.target.value) {
        mode.value = event.target.value;
        mode.dispatchEvent(new Event("change"));
      }
      refreshAgentChrome();
      return;
    }
    if (event.target.id === "pg-mode" && $("agent-run-mode")) refreshAgentChrome();
  });
  window.addEventListener("keydown", (event) => {
    if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "s") return;
    if (state.view !== "configuration" || !$("pg-config-form")) return;
    event.preventDefault();
    $("pg-config-form").requestSubmit();
  });
  document.getElementById("app").addEventListener("click", (event) => {
    const suggestion = event.target.closest("[data-suggestion]");
    if (suggestion) {
      event.preventDefault();
      const [group, index] = suggestion.dataset.suggestion.split(":");
      const found = AGENT_SUGGESTIONS.find((item) => item.group === group);
      const choice = found && found.items[Number(index)];
      if (choice) applyAgentSuggestion(choice);
      return;
    }
    const ownAdd = event.target.closest("#agent-own-add");
    if (ownAdd) {
      event.preventDefault();
      addOwnAgentRule();
      return;
    }
    const choice = event.target.closest("button[data-choice]");
    if (choice) {
      event.preventDefault();
      setAgentChoice(choice.dataset.choice, choice.dataset.value);
      return;
    }
    const addRule = event.target.closest("#agent-add-rule");
    if (addRule) {
      event.preventDefault();
      state.agentUi.editingRule = null;
      state.agentUi.ruleMenu = !state.agentUi.ruleMenu;
      renderAgent();
      const field = $("agent-own-rule");
      if (field) field.focus();
      return;
    }
    const ruleEdit = event.target.closest("[data-rule-edit]");
    if (ruleEdit) {
      event.preventDefault();
      state.agentUi.ruleMenu = false;
      state.agentUi.editingRule = Number(ruleEdit.dataset.ruleEdit);
      renderAgent();
      return;
    }
    const ruleDone = event.target.closest("[data-rule-done]");
    if (ruleDone) {
      event.preventDefault();
      state.agentUi.editingRule = null;
      commitBehavior(state.agentBehavior);
      return;
    }
    const ruleDel = event.target.closest("[data-rule-del]");
    if (ruleDel) {
      event.preventDefault();
      const next = AgentConfig.clone(state.agentBehavior);
      next.customRules.splice(Number(ruleDel.dataset.ruleDel), 1);
      next.legacyText = null;
      next.mode = "guided";
      next.preset = AgentConfig.detectPreset(next);
      state.agentUi.editingRule = null;
      commitBehavior(next);
      return;
    }
    const ruleMove = event.target.closest("[data-rule-up], [data-rule-down]");
    if (ruleMove) {
      event.preventDefault();
      const index = Number(ruleMove.dataset.ruleUp != null ? ruleMove.dataset.ruleUp : ruleMove.dataset.ruleDown);
      const delta = ruleMove.dataset.ruleUp != null ? -1 : 1;
      const next = AgentConfig.clone(state.agentBehavior);
      const target = index + delta;
      if (target >= 0 && target < next.customRules.length) {
        const current = next.customRules[index];
        next.customRules[index] = next.customRules[target];
        next.customRules[target] = current;
      }
      next.legacyText = null;
      next.mode = "guided";
      next.preset = AgentConfig.detectPreset(next);
      commitBehavior(next);
      return;
    }
    if (event.target.closest("#agent-edit-raw")) {
      event.preventDefault();
      switchAgentToRaw();
      return;
    }
    if (event.target.closest("#agent-use-guided")) {
      event.preventDefault();
      switchAgentToGuided();
      return;
    }
    if (event.target.closest("#agent-advanced-toggle")) {
      event.preventDefault();
      state.agentUi.advancedOpen = !state.agentUi.advancedOpen;
      renderAgent();
      return;
    }
    if (event.target.closest("#agent-copy")) {
      event.preventDefault();
      const text = state.agentBehavior && state.agentBehavior.mode === "raw" && $("pg-instructions")
        ? $("pg-instructions").value
        : AgentConfig.effectiveInstructions(state.agentBehavior, state.draftConfig.instructions);
      const done = navigator.clipboard && navigator.clipboard.writeText(text);
      if (done && done.then) done.then(() => toast("Copied instructions")).catch(() => showError("Could not copy instructions."));
      else showError("Could not copy instructions.");
      return;
    }
    if (state.agentUi.ruleMenu && !event.target.closest("#agent-rule-menu") && !event.target.closest("#agent-add-rule")) {
      state.agentUi.ruleMenu = false;
      const menu = $("agent-rule-menu");
      if (menu) menu.remove();
      const add = $("agent-add-rule");
      if (add) add.setAttribute("aria-expanded", "false");
    }
    const newWorkspace = event.target.closest("#agent-new-workspace");
    if (newWorkspace) {
      event.preventDefault();
      if (state.navCollapsed) setNavCollapsed(false);
      const form = $("new-workspace-form");
      form.hidden = false;
      $("new-workspace-name").focus();
      return;
    }
    const delProject = event.target.closest("#pg-delete-project");
    if (delProject) {
      event.preventDefault();
      deletePlaygroundProject().catch((error) => showError(error.message));
      return;
    }
    const addSource = event.target.closest("#kn-add-source");
    if (addSource) {
      event.preventDefault();
      const input = $("pg-file");
      if (input) input.click();
      return;
    }
    const apiLang = event.target.closest("[data-api-lang]");
    if (apiLang) {
      event.preventDefault();
      state.apiLang = apiLang.dataset.apiLang;
      renderApiPanel();
      return;
    }
    const copySample = event.target.closest("#api-copy-sample");
    if (copySample) {
      event.preventDefault();
      const sample = $("api-sample");
      const text = sample ? sample.textContent : "";
      const done = text && navigator.clipboard && navigator.clipboard.writeText(text);
      if (done && done.then) {
        done.then(() => {
          toast("Copied example");
          const previous = copySample.innerHTML;
          copySample.classList.add("is-copied");
          copySample.innerHTML = `${icon("check", 14)} Copied`;
          window.setTimeout(() => {
            if (!copySample.isConnected) return;
            copySample.classList.remove("is-copied");
            copySample.innerHTML = previous;
          }, 1200);
        }).catch(() => showError("Could not copy the example."));
      } else showError("Could not copy the example.");
      return;
    }
    const dismissKey = event.target.closest("[data-key-done]");
    if (dismissKey) {
      event.preventDefault();
      state.revealedKey = null;
      renderApiPanel();
      return;
    }
    const createKey = event.target.closest("#pg-create-key, [data-create-key]");
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
    const closeDoc = event.target.closest("[data-doc-close]");
    if (closeDoc) {
      event.preventDefault();
      state.openDocument = null;
      renderKnowledge();
      return;
    }
    const openDoc = event.target.closest("[data-doc-open]");
    if (openDoc) {
      event.preventDefault();
      openDocument(openDoc.dataset.docOpen).catch((error) => showError(error.message));
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
  const transcript = $("pg-transcript");
  if (transcript) {
    transcript.addEventListener("click", (event) => {
      const cite = event.target.closest("button.cite");
      if (!cite) return;
      selectCitation(cite.dataset.chunkId, cite.dataset.citePass || null);
    });
  }
  const history = $("tc-history");
  if (history) {
    history.addEventListener("click", (event) => {
      const button = event.target.closest("[data-flight]");
      if (!button) return;
      const ids = (button.dataset.flight || "").split(",").filter(Boolean);
      openFlight(ids).catch((error) => showError(error.message));
    });
  }
  const flight = $("tc-flight");
  if (flight) {
    flight.addEventListener("click", (event) => {
      const recover = event.target.closest("[data-recover]");
      if (!recover) return;
      applyRecovery(recover.dataset.recover).catch((error) => showError(error.message));
    });
  }
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

const OV_ACTIONS = {
  rewrite: "Rewrite",
  expand: "Expand",
  regenerate: "Regenerate",
  abstain: "Abstain",
};

const OV_DIAGNOSES = {
  unsupported_generation: "Unsupported generation",
  retrieval_miss: "Retrieval miss",
  evidence_insufficiency: "Evidence insufficiency",
};

const OV_STATES = {
  not_judged: "Not judged",
  evidence_insufficient: "Evidence insufficient",
  answer_unsupported: "Answer unsupported",
  answer_supported: "Answer supported",
  evidence_sufficient: "Evidence sufficient",
};

const OV_OUTCOMES = {
  improved: "Improved",
  unchanged: "Unchanged",
  still_failing: "Still failing",
  degraded: "Degraded",
};

function applyRelPreset(key, value) {
  if (!key) return;
  state.relFilters[key] = value;
  const field = $(`rel-${key}`);
  if (field) field.value = value;
  setEvalTab("runs");
  renderReliability();
}

function relWhen(value) {
  return window.ReliabilityView.formatWhen(value);
}

function relFraction(part) {
  if (!part || !part.total || part.rate == null) return "—";
  return `${part.count} / ${part.total} (${Math.round(part.rate * 100)}%)`;
}

function relSignal(part) {
  if (!part || !part.total || part.rate == null) return "—";
  return `${part.true}/${part.total} (${Math.round(part.rate * 100)}%)`;
}

function renderReliability() {
  const view = window.ReliabilityView;
  renderRelSummary(view);
  renderRelRuns(view);
  renderRelRecoveries(view);
  renderRelDetail(view);
}

function renderRelSummary(view) {
  const root = $("rel-summary");
  if (!root) return;
  const data = state.overview;
  if (!data) {
    root.innerHTML = state.overviewError
      ? `<p class="rel-empty">${escapeHtml(state.overviewError)}</p>`
      : `<div class="rel-summary" aria-busy="true" aria-label="Loading reliability">${'<section class="sk-card"><span class="skeleton sk-line sk-short"></span><span class="skeleton sk-line"></span><span class="skeleton sk-line"></span></section>'.repeat(4)}</div>`;
    return;
  }
  if (!data.observed_runs) {
    root.innerHTML = `<p class="rel-note">All recorded runs for this system. There is no date filter.</p><p class="rel-empty">No runs recorded yet. Questions are run from Test Console.</p>`;
    return;
  }
  const pending = (state.logicalRuns || []).filter((run) => run.recovery_pending).length;
  const unattributed = data.unattributed || 0;
  const outcomes = data.outcomes || {};
  const labels = view || {
    labelDiagnosis: (name) => name,
    labelAction: (name) => name,
  };
  root.innerHTML = `
    <div class="rel-summary">
      <section>
        <h2>Reliability volume${infoTip("All recorded runs for this system. There is no date filter. This is the historical pattern, not the live attention snapshot on Overview.")}</h2>
        ${relStat("Judged logical runs", String(data.judged_runs || 0))}
        ${relStat("Runs requiring recovery", relFraction(data.recovery_required))}
        ${relStat("Applied recoveries", String((outcomes.applied) || 0))}
        ${relStat("Pending recoveries", String(pending))}
      </section>
      <section>
        <h2>Verification outcomes${infoTip("Unchanged means a recovery was applied and the runtime judge flags did not change. It is not treated as improved, and it is not automatically unresolved.")}</h2>
        ${relOutcomeRows(outcomes)}
        ${relStat("Pending, not in the verified denominator", String(pending))}
        <button type="button" class="ghost rel-preset-link" data-rel-preset="verification" data-rel-value="needs">Show runs that need investigation →</button>
      </section>
      <section>
        <h2>Failure diagnoses</h2>
        ${relCountRows(data.diagnoses, (row) => (labels.labelDiagnosis ? labels.labelDiagnosis(row.name) : row.name))}
        ${unattributed ? relStat("Not attributed", String(unattributed)) : ""}
        ${!(data.diagnoses || []).length && !unattributed ? `<p class="rel-empty">No stored failure class on these runs.</p>` : ""}
      </section>
      <section>
        <h2>Recovery actions</h2>
        ${relCountRows(data.applied_actions, (row) => (labels.labelAction ? labels.labelAction(row.name) : row.name))}
        ${!(data.applied_actions || []).length ? `<p class="rel-empty">No recovery actions applied yet.</p>` : ""}
      </section>
      <section>
        <h2>Runtime judge state${infoTip((data.signals && data.signals.note) || "")}</h2>
        ${relStat("Evidence sufficient, initial → final", `${relSignal(data.signals && data.signals.evidence_sufficient && data.signals.evidence_sufficient.initial)} → ${relSignal(data.signals && data.signals.evidence_sufficient && data.signals.evidence_sufficient.final)}`)}
        ${relStat("Answer supported, initial → final", `${relSignal(data.signals && data.signals.answer_supported && data.signals.answer_supported.initial)} → ${relSignal(data.signals && data.signals.answer_supported && data.signals.answer_supported.final)}`)}
      </section>
      <section>
        <h2>Latency${infoTip("A run's latency is the sum of its trace and any recovery child.")}</h2>
        ${relLatency(data.latency)}
      </section>
    </div>`;
}

function relStat(label, value) {
  return `<p class="rel-stat"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></p>`;
}

function relOutcomeRows(outcomes) {
  const total = outcomes.with_outcome || 0;
  if (!total) return `<p class="rel-empty">No verified recoveries yet.</p>`;
  const names = [
    ["improved", "Improved"],
    ["unchanged", "Unchanged"],
    ["still_failing", "Still failing"],
    ["degraded", "Degraded"],
  ];
  return names
    .map(([key, label]) => {
      const count = outcomes[key] || 0;
      const width = Math.round((count / total) * 100);
      return `<div class="rel-line"><span>${label}</span><span class="rel-bar"><span class="is-${key}" style="width:${width}%"></span></span><span>${count}</span></div>`;
    })
    .join("");
}

function relStatus(run, view) {
  const label = view && view.presentVerification ? view.presentVerification(run) : view.labelVerification(run);
  const tone = {
    "Safe stop": "safe_stop",
    Improved: "improved",
    Unchanged: "unchanged",
    "Still failing": "still_failing",
    Degraded: "degraded",
    Pending: "pending",
  }[label] || "neutral";
  return `<span class="status-pill is-${tone}">${escapeHtml(label)}</span>`;
}

function pathChips(text) {
  const parts = String(text || "")
    .split(" → ")
    .map((part) => part.trim())
    .filter(Boolean);
  if (!parts.length) return `<span class="ov-quiet">—</span>`;
  return `<span class="path-chips">${parts
    .map((part) => `<span class="path-chip">${escapeHtml(part)}</span>`)
    .join('<span class="path-arrow" aria-hidden="true">→</span>')}</span>`;
}

function relCountRows(rows, labelFor) {
  return (rows || [])
    .map((row) => relStat(labelFor(row), String(row.count)))
    .join("");
}

function relLatency(latency) {
  if (!latency || !latency.runs || latency.median_ms == null) {
    return `<p class="rel-empty">No timed runs yet.</p>`;
  }
  // One bar per timed run, newest first, scaled to the slowest.
  const timed = (state.logicalRuns || []).filter((run) => run.latency_ms != null).slice(0, 8);
  const max = Math.max(1, ...timed.map((run) => run.latency_ms));
  const bars = timed
    .map(
      (run) => `<div class="lat-row" title="${escapeHtml(run.query || "")}">
        <span class="lat-q">${escapeHtml(clipFlight(run.query || "(empty question)"))}</span>
        <span class="lat-track"><span class="lat-fill" style="width:${Math.max(4, (100 * run.latency_ms) / max)}%"></span></span>
        <span class="lat-v">${escapeHtml(formatFlightLatency(run.latency_ms))}</span>
      </div>`
    )
    .join("");
  return `<p class="lat-median"><b>${escapeHtml(formatFlightLatency(latency.median_ms))}</b> median across ${latency.runs} timed run${latency.runs === 1 ? "" : "s"}</p>
    <div class="lat-bars">${bars}</div>
`;
}

function renderRelRuns(view) {
  const root = $("rel-runs");
  if (!root || !view) return;
  const runs = state.logicalRuns || [];
  if (state.relFocus && !runs.some((run) => run.logical_run_id === state.relFocus.logical_run_id)) {
    state.relFocus = null;
  }
  if (!runs.length) {
    root.innerHTML = `<p class="rel-empty">No runs recorded yet.</p>`;
    return;
  }
  const filtered = view.filterLogicalRuns(runs, state.relFilters);
  if (!filtered.length) {
    root.innerHTML = `<p class="rel-empty">No runs match these filters.</p>`;
    return;
  }
  const body = filtered
    .map((run) => {
      const diagnosis = !run.judged
        ? "Not judged"
        : (run.diagnoses || []).map(view.labelDiagnosis).join(", ") || "Not attributed";
      const latency = run.latency_ms == null ? "—" : formatFlightLatency(run.latency_ms);
      const focused = state.relFocus && state.relFocus.logical_run_id === run.logical_run_id;
      return `<tr class="rel-row${focused ? " is-focus" : ""}" data-rel-open="${escapeHtml(run.logical_run_id)}" aria-selected="${focused ? "true" : "false"}">
        <td class="c-q">${escapeHtml(run.query || "(empty question)")}<small class="c-sub">${escapeHtml(relWhen(run.timestamp))}</small></td>
        <td class="c-init">${escapeHtml(view.labelInitialState(run.initial_state))}</td>
        <td class="c-rec">${pathChips(view.labelRecovery(run))}</td>
        <td class="c-diag">${escapeHtml(diagnosis)}</td>
        <td class="c-ver">${relStatus(run, view)}</td>
        <td class="c-lat">${escapeHtml(latency)}</td>
        <td class="c-act"><button type="button" class="ghost" data-rel-open="${escapeHtml(run.logical_run_id)}" aria-label="Inspect ${escapeHtml(run.query || "run")}">${icon("chevron-right", 14)}</button></td>
      </tr>`;
    })
    .join("");
  root.innerHTML = `<div class="rel-scroll"><table class="rel-table rel-runs-table">
    <thead><tr><th class="c-q">Question</th><th class="c-init">Initial state</th><th class="c-rec">Recovery</th><th class="c-diag">Diagnosis</th><th class="c-ver">Verification</th><th class="c-lat">Latency</th><th class="c-act"></th></tr></thead>
    <tbody>${body}</tbody>
  </table></div>`;
  // Master-detail: with nothing selected, open the newest matching run so the
  // detail pane is never blank. Once per visit to the tab.
  if (!state.relFocus && state.view === "reliability" && state.evalTab === "runs" && !state.relAutoFocus) {
    state.relAutoFocus = true;
    const first = filtered[0];
    inspectOverviewRun(first.inspect_run_id || first.logical_run_id).catch((error) => showError(error.message));
  }
}

function renderRelRecoveries(view) {
  const root = $("rel-recoveries");
  if (!root || !view) return;
  const cases = view.recoveryCases(state.logicalRuns || []);
  if (!cases.length) {
    root.innerHTML = `<p class="rel-empty">No recovery cases yet. An accepted run, or a run that was never judged, is not listed here.</p>`;
    return;
  }
  const body = cases
    .map((run) => {
      const pending = Boolean(run.recovery_pending) && !(run.recovery || []).length;
      const path = pending ? view.recoveryPath(run) : view.labelRecovery(run);
      const diagnosis = !run.judged
        ? "Not judged"
        : (run.diagnoses || []).map(view.labelDiagnosis).join(", ") || "Not attributed";
      return `<tr>
        <td>${escapeHtml(run.query || "(empty question)")}</td>
        <td>${escapeHtml(view.labelTrigger(run.trigger) || "—")}</td>
        <td>${escapeHtml(diagnosis)}</td>
        <td>${pathChips(path)}${pending ? ` <span class="status-pill is-pending">Proposed</span>` : ""}</td>
        <td>${escapeHtml(view.labelSource(run.source) || "—")}</td>
        <td>${relStatus(run, view)}</td>
        <td>${escapeHtml(relWhen(run.timestamp))}</td>
        <td><button type="button" class="ghost" data-rel-open="${escapeHtml(run.logical_run_id)}">Inspect</button></td>
      </tr>`;
    })
    .join("");
  // Compact tallies above the table: which paths ran, what triggered them, how they ended.
  const tally = (key) => {
    const counts = new Map();
    cases.forEach((run) => {
      const name = key(run);
      if (name) counts.set(name, (counts.get(name) || 0) + 1);
    });
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  };
  const statCard = (title, entries) => `<section class="rec-stat">
      <h3>${escapeHtml(title)}</h3>
      ${entries.length
        ? entries.map(([name, count]) => `<p><span>${escapeHtml(name)}</span><b>${count}</b></p>`).join("")
        : `<p class="rel-note">None yet.</p>`}
    </section>`;
  const stats = `<div class="rec-stats">
      ${statCard("Recovery path", tally((run) => (run.recovery_pending && !(run.recovery || []).length ? "Proposed" : view.labelRecovery(run))))}
      ${statCard("Trigger", tally((run) => view.labelTrigger(run.trigger) || "Not recorded"))}
      ${statCard("Result", tally((run) => view.presentVerification(run)))}
    </div>`;
  root.innerHTML = `<p class="rel-note">How runtime recovery behaved across runs. Pending proposals stay visible here.</p>
    ${stats}
    <div class="rel-scroll"><table class="rel-table">
      <thead><tr><th>Question</th><th>Trigger</th><th>Diagnosis</th><th>Recovery path</th><th>Source</th><th>Verification</th><th>When</th><th></th></tr></thead>
      <tbody>${body}</tbody>
    </table></div>`;
}

function renderRelDetail(view) {
  const root = $("rel-detail");
  const workspace = $("workspace");
  if (!root) return;
  const row = state.relFocus;
  if (!row || !view) {
    root.innerHTML = (state.logicalRuns || []).length
      ? `<div class="rel-detail-empty">
          ${icon("activity", 18)}
          <h2>Select a run</h2>
          <p>Its agent loop, answers, and evidence open here.</p>
        </div>`
      : "";
    if (workspace) workspace.classList.remove("is-open");
    return;
  }
  const loaded = new Set((state.flightTraces || []).map((trace) => trace.run_id));
  const aligned = (row.trace_ids || []).length > 0 && (row.trace_ids || []).every((id) => loaded.has(id));
  const flight = aligned && window.FlightRecorder ? FlightRecorder.buildFlight(state.flightTraces) : null;
  const pending = Boolean(row.recovery_pending) && !(row.recovery || []).length;
  const action = pending
    ? `<button type="button" class="primary" data-rel-console="${escapeHtml(row.logical_run_id)}">Review recovery</button>`
    : `<button type="button" class="ghost" data-rel-console="${escapeHtml(row.logical_run_id)}">Open in Test Console</button>`;
  const usage = formatUsage(row.usage);
  const latency = row.latency_ms == null ? "Latency not recorded" : formatFlightLatency(row.latency_ms);
  const config = state.trace && state.trace.agent_config
    ? `<pre class="rel-config">${escapeHtml(JSON.stringify(state.trace.agent_config, null, 2))}</pre>`
    : `<p class="rel-note">No agent config snapshot on this run.</p>`;
  const qualityId = row.inspect_run_id || row.logical_run_id;
  const saved = state.quality[qualityId];
  const board = qualityBoardRuns().find((item) => item.run_id === qualityId);
  const qualityNote = `<p class="rel-note">Post-hoc quality is separate from runtime verification and does not influence recovery.</p>`;
  let quality = qualityNote;
  if (saved && saved.status === "done" && typeof metricsCard === "function") {
    quality += metricsCard(saved, {
      recovered: (row.recovery || []).length > 0,
      abstained: Boolean(board && board.abstained),
      finalChunks: (state.trace && state.trace.retrieved_chunks) || [],
      hasAnswer: !(board && board.abstained),
    });
  } else if (board && view.qualityStatus(board) === "Scored") {
    quality += `<p class="rel-stat"><span>Quality</span><strong>Scored</strong></p><button type="button" class="ghost" data-rel-claims="${escapeHtml(qualityId)}">Show claim checks</button>`;
  } else if (board && view.qualityStatus(board) === "Not scored") {
    quality += `<p class="rel-stat"><span>Quality</span><strong>Not scored</strong></p><button type="button" class="ghost" data-score-run-id="${escapeHtml(qualityId)}">Score this run</button>`;
  } else {
    quality += `<p class="rel-stat"><span>Quality</span><strong>Not applicable</strong></p>`;
  }
  const safeNote = row.safe_stop
    ? `<p class="tc-safe-note">Safe stop. Bounded recovery stopped because sufficient support was not found. The stored verifier result stays in the trace below and is not a second status.</p>`
    : "";
  const detailKey = `${row.logical_run_id}:${flight ? "ready" : "loading"}`;
  const freshDetail = detailKey !== state.lastRelDetailKey;
  state.lastRelDetailKey = detailKey;
  root.innerHTML = `<article class="rel-detail">
    <div class="rel-detail-head">
      <div>
        <p class="rel-kicker">Logical run</p>
        <h2>${escapeHtml(row.query || "(empty question)")}</h2>
      </div>
      <div class="rel-detail-actions">${action}<button type="button" class="ghost danger" data-rel-delete="${escapeHtml(row.logical_run_id)}">Delete run</button></div>
    </div>
    <p class="rel-meta">${escapeHtml(latency)} · ${escapeHtml(usage)}</p>
    ${safeNote}
    ${flight ? flightHtml(flight, { propose: false }) : `<p class="rel-empty">Loading this run…</p>`}
    <h3>Post-hoc quality</h3>
    ${quality}
    <h3>Agent config</h3>
    ${config}
  </article>`;
  if (workspace) workspace.classList.toggle("is-open", aligned && state.steps.length > 0);
  if (freshDetail && flight) playEnter(root);
}

async function loadOverview() {
  const root = $("overview-body");
  if (!root) return;
  try {
    state.overview = await api("/api/overview");
    state.overviewError = "";
  } catch (error) {
    state.overview = null;
    state.overviewError = error.message || "Overview could not be loaded.";
  }
  renderOverview();
}

async function loadLogicalRuns() {
  try {
    const payload = await api("/api/logical-runs");
    state.logicalRuns = payload.runs || [];
  } catch (error) {
    state.logicalRuns = [];
  }
  renderFlight();
  renderReliability();
  renderShell();
}

async function openFlight(ids, options) {
  const stay = Boolean(options && options.stay);
  const traces = [];
  for (const id of ids) {
    const payload = await api(`/api/traces/${encodeURIComponent(id)}`);
    if (payload.trace) traces.push(payload.trace);
  }
  state.flightTraces = traces;
  const flight = window.FlightRecorder ? FlightRecorder.buildFlight(traces) : null;
  const focusId = (flight && flight.pending && flight.pending.runId) || (traces[traces.length - 1] && traces[traces.length - 1].run_id);
  const focus = traces.find((trace) => trace.run_id === focusId) || traces[traces.length - 1] || null;
  state.selectedId = focus ? focus.run_id : null;
  state.trace = focus;
  state.steps = [];
  state.selectedStep = null;
  if (options && options.stepsFor) {
    try {
      const detail = await api(`/api/traces/${encodeURIComponent(options.stepsFor)}`);
      state.steps = detail.steps || [];
      state.selectedStep = state.steps[0] || null;
    } catch (error) {
      state.steps = [];
    }
  }
  state.childRunId = flight && !flight.pending && traces.length > 1 ? traces[traces.length - 1].run_id : null;
  if (stay) {
    const match = (state.logicalRuns || []).find((run) =>
      (run.trace_ids || []).some((id) => ids.includes(id))
    );
    if (match) state.relFocus = match;
  } else if (state.view !== "test") {
    if (location.hash !== "#test") location.hash = "#test";
    applyView();
  }
  render();
}

function renderModeNote() {
  const note = $("pg-mode-note");
  const mode = $("pg-mode");
  if (!note || !mode || !window.FlightRecorder) return;
  note.textContent = FlightRecorder.modeNote(mode.value);
}

function renderFlight() {
  renderModeNote();
  renderFlightHistory();
  const root = $("tc-flight");
  if (!root || !window.FlightRecorder) return;
  if (state.loading && state.view === "test" && (state.liveEvents || []).length) {
    root.innerHTML = liveFlightHtml();
    state.lastFlightKey = null;
    return;
  }
  if (state.loading && state.view === "test") {
    if (!root.querySelector(".loop-map.is-running")) {
      root.innerHTML = `<div class="tc-running">
        ${loopMapHtml(null).replace('class="loop-map is-idle"', 'class="loop-map is-idle is-running"')}
        <p class="tc-running-note"><span class="pulse" aria-hidden="true"></span>Running the loop. The core returns the whole trace when it finishes, so the stages fill in together.</p>
      </div>`;
    }
    state.lastFlightKey = null;
    return;
  }
  const flight = FlightRecorder.buildFlight(state.flightTraces);
  if (!flight) {
    root.innerHTML = flightIdleHtml();
    const inspect = $("pg-inspect");
    const title = $("pg-inspector-title");
    if (title) title.textContent = "Run detail";
    if (inspect) {
      inspect.innerHTML = `<div class="tc-idle tc-idle-side"><p class="tc-empty">Retrieved passages and judge flags appear after a run.</p></div>`;
    }
    return;
  }
  root.innerHTML = flightHtml(flight);
  renderFlightInspector(flight);
  const key = (flight.traceIds || []).join(",");
  if (key !== state.lastFlightKey) {
    state.lastFlightKey = key;
    playEnter(root);
  }
}

function renderFlightHistory() {
  const root = $("tc-history");
  if (!root) return;
  const open = new Set((state.flightTraces || []).map((trace) => trace.run_id));
  if (!state.logicalRuns.length) {
    root.innerHTML = `<p class="tc-empty">No runs yet.</p>`;
    return;
  }
  root.innerHTML = state.logicalRuns
    .map((run) => {
      const ids = (run.trace_ids || []).join(",");
      const on = (run.trace_ids || []).some((id) => open.has(id));
      const outcome = run.safe_stop
        ? "Safe stop"
        : run.verification
          ? FlightRecorder.labelOutcome(run.verification)
          : run.recovery_pending
            ? "Proposed"
            : "";
      const path = (run.recovery || []).map((action) =>
        run.safe_stop && action === "abstain" ? "safe stop" : action
      );
      return `<button type="button" class="tc-run${on ? " is-on" : ""}" data-flight="${escapeHtml(ids)}">
        <strong>${escapeHtml(clipFlight(run.query || "(empty)"))}</strong>
        <small>${escapeHtml([outcome, path.length ? path.join(" → ") : ""].filter(Boolean).join(" · "))}</small>
      </button>`;
    })
    .join("");
}

// Caveats live behind an info icon next to the heading they qualify. The text
// is the same; it is the button's accessible name and its tooltip, so it is
// one hover or one Tab away instead of a paragraph on every card.
function infoTip(text) {
  if (!text) return "";
  return `<button type="button" class="info-tip" data-tip="${escapeHtml(text)}" data-tip-wrap aria-label="${escapeHtml(text)}">${icon("info", 13)}</button>`;
}

// ---------- Motion ----------
// Animations are triggered by events (a page opens, a new run is shown), not
// by every re-render, so nothing replays while the user works.
function prefersReducedMotion() {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

function playEnter(el) {
  if (!el || prefersReducedMotion()) return;
  el.classList.remove("is-entering");
  void el.offsetWidth;
  el.classList.add("is-entering");
  window.clearTimeout(el._enterTimer);
  el._enterTimer = window.setTimeout(() => el.classList.remove("is-entering"), 900);
}

// Tween every number in an element's text from 0 ("2/2" counts both parts).
function countUp(root) {
  if (!root || prefersReducedMotion()) return;
  root.querySelectorAll("[data-count]").forEach((el) => {
    const target = el.textContent;
    const parts = target.split(/(\d+)/);
    if (parts.length < 2) return;
    const start = performance.now();
    const duration = 520;
    const frame = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      el.textContent = parts.map((part) => (/^\d+$/.test(part) ? String(Math.round(Number(part) * eased)) : part)).join("");
      if (t < 1) window.requestAnimationFrame(frame);
      else el.textContent = target;
    };
    window.requestAnimationFrame(frame);
  });
}

// Icon per agent stage and per flight step kind. One icon language for the
// loop map and the step timeline.
const STAGE_ICONS = {
  retrieve: "search",
  generate: "sparkles",
  judge: "scale",
  diagnose: "activity",
  recover: "wrench",
  verify: "shield-check",
  query: "message-square",
  why: "info",
  source: "git-branch",
  trigger: "zap",
  abstain: "ban",
};

const STAGE_STATE_LABELS = {
  idle: "Not run yet",
  done: "Done",
  flagged: "Flagged",
  pending: "Waiting for confirmation",
  skipped: "Not part of this run",
  pass: "Passed",
  fail: "Failed",
  neutral: "No change",
  safe: "Safe stop",
};

function loopMapHtml(flight) {
  const stages = window.FlightRecorder.loopStages(flight);
  return `<ol class="loop-map${flight ? "" : " is-idle"}" aria-label="Agent loop">${stages
    .map(
      (stage) => `<li class="loop-stage is-${escapeHtml(stage.key)} is-${escapeHtml(stage.state)}">
        <span class="loop-node" title="${escapeHtml(`${stage.label}: ${STAGE_STATE_LABELS[stage.state] || stage.state}`)}">${icon(STAGE_ICONS[stage.key], 15)}</span>
        <span class="loop-text">
          <span class="loop-label">${escapeHtml(stage.label)}</span>
          <span class="loop-note">${escapeHtml(stage.note || STAGE_STATE_LABELS[stage.state] || "")}</span>
        </span>
        <span class="sr-only">${escapeHtml(STAGE_STATE_LABELS[stage.state] || stage.state)}</span>
      </li>`
    )
    .join("")}</ol>`;
}

// The loop while a run streams: each stage pulses while it runs and fills in
// with its measured time when it ends.
function liveFlightHtml() {
  const stages = window.FlightRecorder.liveStages(state.liveEvents);
  const current = stages.find((stage) => stage.state === "running");
  const map = `<ol class="loop-map is-live" aria-label="Agent loop, live">${stages
    .map((stage) => {
      const note =
        stage.state === "running"
          ? `${stage.note ? `${stage.note} · ` : ""}running`
          : stage.ms != null
            ? `${stage.note ? `${stage.note} · ` : ""}${formatFlightLatency(stage.ms)}${stage.count > 1 ? ` · ×${stage.count}` : ""}`
            : stage.state === "fail"
              ? "failed"
              : "";
      const cls = stage.state === "idle" ? "is-idle-stage" : stage.state === "running" ? "is-live-running" : `is-${stage.state}`;
      return `<li class="loop-stage is-${escapeHtml(stage.key)} ${cls}">
        <span class="loop-node">${icon(STAGE_ICONS[stage.key], 15)}</span>
        <span class="loop-text">
          <span class="loop-label">${escapeHtml(stage.label)}</span>
          <span class="loop-note">${escapeHtml(note)}</span>
        </span>
      </li>`;
    })
    .join("")}</ol>`;
  const label = current ? `${current.label}${current.note ? ` · ${current.note}` : ""}` : "Writing the trace";
  return `<div class="tc-running is-live">
    <div class="tc-live-head"><span class="pulse" aria-hidden="true"></span><b>${escapeHtml(label)}</b><span class="tc-live-elapsed" id="tc-live-elapsed">${escapeHtml(liveElapsedText())}</span></div>
    ${map}
  </div>`;
}

function liveElapsedText() {
  if (!state.liveStarted) return "";
  return `${((performance.now() - state.liveStarted) / 1000).toFixed(1)}s`;
}

function renderLiveElapsed() {
  const el = $("tc-live-elapsed");
  if (el) el.textContent = liveElapsedText();
}

// Waterfall of the stages of a finished run, from its recorded stage timings.
function timelineHtml(flight) {
  const line = window.FlightRecorder.timelineRows(flight);
  if (!line) return "";
  const rows = line.rows
    .map(
      (row) => `<div class="tl-row is-${escapeHtml(row.stage)}${row.depth ? " is-nested" : ""}${row.status === "error" ? " is-error" : ""}">
        <span class="tl-name">${icon(STAGE_ICONS[row.stage] || "info", 12)}<span>${escapeHtml(row.label)}</span></span>
        <span class="tl-track"><span class="tl-bar" style="left:${row.left}%;width:${row.width}%"></span></span>
        <span class="tl-ms">${escapeHtml(formatFlightLatency(row.durationMs))}</span>
      </div>`
    )
    .join("");
  return `<section class="tc-phase tc-timeline">
    <h2>Timeline <span class="tl-total">${escapeHtml(formatFlightLatency(line.totalMs))} total</span>${infoTip("Measured by the core for each stage of this run. Recovery work is indented under its attempt.")}</h2>
    <div class="tl-rows">${rows}</div>
  </section>`;
}

function flightIdleHtml() {
  return `<div class="tc-idle">
    <p class="tc-idle-kicker">Agent loop</p>
    <h2 class="tc-idle-title">Ask a question and watch the loop work</h2>
    <p class="tc-empty">The agent retrieves passages, drafts an answer, judges its own grounding, diagnoses a failure, recovers, and verifies whether the recovery helped.</p>
    ${loopMapHtml(null)}
  </div>`;
}

function flightHtml(flight, options) {
  const proposal = options && options.propose === false ? "" : flightProposal(flight);
  return `${loopMapHtml(flight)}${flightSummary(flight)}${timelineHtml(flight)}${proposal}${flightWarning(flight)}${flight.phases.map((phase) => phaseHtml(phase, flight)).join("")}${answerCompare(flight)}${evidenceCompare(flight)}`;
}

function flightSummary(flight) {
  const chips = [];
  const mode = inferredFlightMode(flight);
  if (mode) chips.push(["meta", mode]);
  if (flight.topK != null) chips.push(["meta", `Top K: ${flight.topK}`]);
  const guarded = flight.recoveryPolicy === "v2c_gap_aware";
  chips.push([guarded ? "guarded" : "meta", guarded ? "Gap-aware" : "Current v1"]);
  if (guarded) chips.push(["guarded", "Guarded"]);
  if (flight.attemptCount) chips.push(["meta", `${flight.attemptCount} recovery attempt${flight.attemptCount === 1 ? "" : "s"}`]);
  chips.push(["status", statusLabel(flight.status), flight.status || "neutral"]);
  if (flight.latencyMs != null) chips.push(["meta", formatFlightLatency(flight.latencyMs)]);
  return `<div class="tc-summary">${chips
    .map(([kind, label, tone]) =>
      kind === "status"
        ? `<span class="status-pill is-${escapeHtml(tone || "neutral")}">${escapeHtml(label)}</span>`
        : `<span class="tc-chip${kind === "guarded" ? " is-guarded" : ""}">${escapeHtml(label)}</span>`
    )
    .join("")}</div>`;
}

function inferredFlightMode(flight) {
  if (flight.runMode === "retrieve_only") return "Retrieve only";
  if (flight.runMode === "baseline") return "Baseline";
  if (flight.runMode === "loop_confirm") return "Confirm recovery";
  if (flight.runMode === "loop") return "Auto recovery";
  if (flight.pending || flight.joined) return "Confirm recovery";
  if (flight.attemptCount) return "Auto recovery";
  if (flight.status === "retrieve_only") return "Retrieve only";
  if (flight.status === "baseline") return "Baseline";
  if (flight.status === "no_recovery_needed") return "No recovery needed";
  return "";
}

function selectedRecoveryPolicy() {
  const field = $("pg-recovery-policy");
  return field && field.value === "gap_aware" ? "gap_aware" : "v1";
}

function syncPolicyNote() {
  const note = $("pg-policy-note");
  const field = $("pg-recovery-policy");
  const badge = $("pg-guarded");
  const guarded = Boolean(field && field.value === "gap_aware");
  if (note) note.hidden = !guarded;
  if (badge) badge.hidden = !guarded;
}

function formatUsage(usage) {
  if (!usage || typeof usage !== "object" || usage.tokens_observed !== true) return "Token usage unavailable";
  if (usage.prompt_tokens == null || usage.completion_tokens == null) return "Token usage unavailable";
  return `${usage.prompt_tokens} prompt tokens · ${usage.completion_tokens} completion tokens`;
}

function statusLabel(status) {
  const labels = {
    retrieve_only: "Retrieve only",
    baseline: "Baseline",
    no_recovery_needed: "No recovery needed",
    not_executed: "Selected, not executed",
    unsupported_schema: "Unsupported trace schema",
    recovery_proposed: "Recovery proposed",
    improved: "Improved",
    unchanged: "Unchanged",
    still_failing: "Still failing",
    degraded: "Degraded",
    safe_stop: "Safe stop",
    abstained: "Safe abstention",
    applied: "Recovery applied",
  };
  return labels[status] || status || "";
}

function flightProposal(flight) {
  const pending = flight.pending;
  if (!pending) return "";
  const diagnosis = pending.diagnosis
    ? diagnosisText(pending.diagnosis)
    : "Diagnosis not yet attributed.";
  const others = V1_ACTIONS.filter((action) => action !== pending.action);
  const overrides = others
    .map(
      (action) =>
        `<button type="button" class="ghost" data-recover="${escapeHtml(action)}">${escapeHtml(ACTION_LABELS[action] || action)}</button>`
    )
    .join("");
  return `<section class="tc-proposal">
    <h2>Recovery proposed</h2>
    <p>${escapeHtml(pending.reason || "The reliability check asked for a recovery.")}</p>
    <p>Diagnosis: ${escapeHtml(diagnosis)}</p>
    <p>Proposed action: ${escapeHtml(FlightRecorder.labelAction(pending.action))}</p>
    <p>${escapeHtml(pending.effect || "")}</p>
    ${pending.source ? `<p>${escapeHtml(pending.source)}</p>` : ""}
    <div class="tc-actions">
      <button type="button" class="primary" data-recover="${escapeHtml(pending.action)}">Apply recovery</button>
      ${overrides}
    </div>
  </section>`;
}

function flightWarning(flight) {
  const warning = flight.retrievalWarning;
  if (!warning) return "";
  let text = "Retrieval looked unreliable.";
  if (warning.weakTop) text = "Top retrieval scores were weak.";
  else if (warning.ambiguousTop) text = "Top evidence candidates were ambiguous.";
  else if (warning.reason) text = warning.reason;
  if (warning.triggeredRecovery) text += " Recovery was triggered by this retrieval signal.";
  const scores = [];
  if (warning.topScore != null) scores.push(`top ${formatScore(warning.topScore)}`);
  if (warning.runnerUpScore != null) scores.push(`runner-up ${formatScore(warning.runnerUpScore)}`);
  return `<section class="tc-phase">
    <h2>Retrieval warning</h2>
    <p class="tc-step-detail">${escapeHtml(text)}</p>
    ${scores.length ? `<p class="tc-step-detail">${escapeHtml(scores.join(" · "))}</p>` : ""}
  </section>`;
}

function phaseHtml(phase, flight) {
  const safePhase = String(phase.title || "") === "Recovery · Safe stop";
  const steps = (phase.steps || [])
    .map((step) => {
      const shown = window.FlightRecorder.presentStep(phase, step, flight && flight.status);
      const title = shown.title;
      const detail = diagnosisText(shown.detail);
      return `<div class="tc-step is-${escapeHtml(step.kind || "step")}${step.kind === "verify" ? " is-verify" : ""}">
        <span class="tc-rail" aria-hidden="true">${icon(STAGE_ICONS[step.kind] || "info", 12)}</span>
        <div>
          <div class="tc-step-title">${escapeHtml(title)}</div>
          ${detail ? `<div class="tc-step-detail">${escapeHtml(detail)}</div>` : ""}
        </div>
      </div>`;
    })
    .join("");
  const note = safePhase
    ? `<p class="tc-safe-note">Bounded recovery stopped because sufficient support was not found.</p>`
    : "";
  return `<section class="tc-phase${safePhase ? " is-safe" : ""}"><h2>${escapeHtml(phase.title || "")}</h2>${note}${steps}</section>`;
}

function answerCompare(flight) {
  if (!flight.after && !flight.before.answer) return "";
  if (!flight.after) {
    if (!flight.before.answer) return "";
    return `<section class="tc-phase"><h2>Answer</h2><p class="tc-step-detail">${escapeHtml(flight.before.answer)}</p></section>`;
  }
  const initial = flight.before.answer || "The first answer was not stored on this trace.";
  const stopped = flight.status === "safe_stop";
  const finalTitle = stopped ? "Safe stop" : flight.after.abstained ? "Safe abstention" : "Recovered answer";
  const recovered = flight.after.answer || "(empty)";
  const note = stopped
    ? `<p class="tc-safe-note">Bounded recovery stopped because sufficient support was not found.</p>`
    : "";
  return `<section class="tc-phase tc-answers">
    <h2>Answers</h2>
    <div class="tc-compare">
      <div class="tc-answer is-initial"><h3>Initial answer</h3><p class="tc-step-detail">${escapeHtml(initial)}</p></div>
      <div class="tc-answer is-final${stopped ? " is-safe" : ""}"><h3>${escapeHtml(finalTitle)}</h3>${note}<p class="tc-step-detail">${escapeHtml(recovered)}</p></div>
    </div>
  </section>`;
}

function evidenceCompare(flight) {
  if (!flight.evidence) {
    const chunks = flight.before.chunks || [];
    if (!chunks.length) return "";
    return `<section class="tc-phase tc-evidence"><h2>Initial evidence</h2>${chunks.map((chunk) => chunkRow(chunk, "")).join("")}</section>`;
  }
  const same = !flight.evidence.added.length && !flight.evidence.removed.length;
  if (same && flight.attempts.some((attempt) => attempt.action === "regenerate") && flight.attempts.every((attempt) => attempt.action === "regenerate")) {
    return `<section class="tc-phase"><h2>Evidence</h2><p class="tc-step-detail">Same evidence.</p>${flight.evidence.retained.map((chunk) => chunkRow(chunk, "Retained")).join("")}</section>`;
  }
  return `<section class="tc-phase tc-evidence">
    <h2>Evidence</h2>
    ${evidenceGroup("Initial evidence · retained", flight.evidence.retained, "Retained")}
    ${evidenceGroup("Removed", flight.evidence.removed, "Removed")}
    ${evidenceGroup("Recovered evidence · new", flight.evidence.added, "New")}
  </section>`;
}

function evidenceGroup(title, chunks, mark) {
  if (!chunks.length) return `<p class="tc-step-detail">${escapeHtml(title)}: none</p>`;
  return `<h3>${escapeHtml(title)}</h3>${chunks.map((chunk) => chunkRow(chunk, mark)).join("")}`;
}

function chunkRow(chunk, mark) {
  const title = (chunk && (chunk.title || chunk.doc_id)) || "Passage";
  const id = (chunk && chunk.chunk_id) || "";
  const score = chunk && typeof chunk.score === "number" ? chunk.score.toFixed(3) : "";
  const page = chunk && chunk.page != null && chunk.page !== "" ? `p. ${chunk.page}` : "";
  const text = (chunk && chunk.text) || "";
  const bits = [mark, title, id, score, page].filter(Boolean).join(" · ");
  return `<details><summary>${escapeHtml(bits)}</summary><p class="tc-chunk-text">${escapeHtml(text)}</p></details>`;
}

function renderFlightInspector(flight) {
  const inspect = $("pg-inspect");
  const title = $("pg-inspector-title");
  if (title) title.textContent = "Run detail";
  if (!inspect) return;
  const before = judgeLines(flight.before.evaluation);
  const after = flight.after ? judgeLines(flight.after.evaluation) : "";
  const outcome = flight.verification ? FlightRecorder.labelOutcome(flight.verification) : "";
  const judged = Boolean(flight.verification || flight.before.evaluation || (flight.after && flight.after.evaluation));
  const stopped = flight.status === "safe_stop";
  const headline = stopped ? "Safe stop" : outcome || statusLabel(flight.status);
  const safeNote = stopped
    ? `<p class="status-pill is-safe_stop">Safe stop</p><p class="tc-safe-note">Bounded recovery stopped because sufficient support was not found.</p><p class="tc-step-detail">Verifier recorded: ${escapeHtml(outcome || "—")}. That stored result stays on the trace and is not a second status.</p>`
    : `<p class="status-pill is-${escapeHtml(flight.status || "neutral")}">${escapeHtml(headline)}</p>`;
  inspect.innerHTML = `<section class="tc-phase${stopped ? " is-safe" : ""}">
    <h2>${judged ? `Runtime verification${infoTip("Compares runtime judge flags from the first pass to the final state. Not ground-truth correctness.")}` : "Run detail"}</h2>
    <p><span class="tc-k">Initial</span> ${escapeHtml(before || "Not judged")}</p>
    <p><span class="tc-k">Final</span> ${escapeHtml(after || before || "Not judged")}</p>
    ${safeNote}
    ${technicalFlags(flight)}
  </section>
  ${inspectorFacts(flight)}
  ${inspectorPassages(flight)}`;
}

// Run facts and the passages the final answer used, so the detail column
// carries the evidence instead of trailing off into empty space.
function inspectorFacts(flight) {
  const rows = [
    ["Mode", inferredFlightMode(flight) || "—"],
    ["Policy", flight.recoveryPolicy === "v2c_gap_aware" ? "Gap-aware (Guarded)" : "Current v1"],
    ["Top K", flight.topK != null ? String(flight.topK) : "—"],
    ["Attempts", String(flight.attemptCount || 0)],
    ["Latency", flight.latencyMs != null ? formatFlightLatency(flight.latencyMs) : "—"],
    ["Model", (state.trace && state.trace.model) || "—"],
  ];
  return `<section class="tc-phase tc-facts">
    <h2>Run</h2>
    <dl>${rows.map(([k, v]) => `<div><dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd></div>`).join("")}</dl>
  </section>`;
}

function inspectorPassages(flight) {
  const chunks = (flight.after && flight.after.chunks && flight.after.chunks.length ? flight.after.chunks : flight.before.chunks) || [];
  if (!chunks.length) return "";
  const scores = chunks.map((chunk) => Number(chunk.score)).filter(Number.isFinite);
  const max = Math.max(1e-9, ...scores);
  const items = chunks
    .slice(0, 6)
    .map((chunk) => {
      const score = Number(chunk.score);
      const width = Number.isFinite(score) ? Math.max(4, (100 * score) / max) : 0;
      return `<li class="tc-passage">
        <div class="tc-passage-head">
          <span class="tc-passage-title">${escapeHtml(chunk.title || chunk.doc_id || "Passage")}</span>
          <span class="tc-passage-score">${Number.isFinite(score) ? escapeHtml(formatScore(score)) : "—"}</span>
        </div>
        <span class="tc-passage-bar"><span style="width:${width}%"></span></span>
        <p>${escapeHtml(clipFlight(chunk.text || ""))}</p>
      </li>`;
    })
    .join("");
  return `<section class="tc-phase tc-passages">
    <h2>Passages <span class="tc-count">${chunks.length}</span></h2>
    <ol>${items}</ol>
  </section>`;
}

function judgeLines(evaluation) {
  if (!evaluation) return "";
  const evidence = evaluation.evidence_sufficient ? "Evidence sufficient" : "Evidence insufficient";
  let support = "Answer support not checked";
  if (evaluation.answer_supported === true) support = "Answer supported";
  if (evaluation.answer_supported === false) support = "Answer unsupported";
  return `${evidence}. ${support}.`;
}

function technicalFlags(flight) {
  const before = flight.before.evaluation;
  const after = flight.after && flight.after.evaluation;
  const lines = [];
  if (before) {
    lines.push(`evidence_sufficient: ${before.evidence_sufficient}`);
    lines.push(`answer_supported: ${before.answer_supported === null ? "null" : before.answer_supported}`);
  }
  if (after) {
    lines.push(`final evidence_sufficient: ${after.evidence_sufficient}`);
    lines.push(`final answer_supported: ${after.answer_supported === null ? "null" : after.answer_supported}`);
  }
  const source = flight.pending && flight.pending.sourceRaw;
  if (source) lines.push(`source: ${source}`);
  (flight.attempts || []).forEach((attempt, index) => {
    if (attempt.sourceRaw) lines.push(`attempt ${index + 1} source: ${attempt.sourceRaw}`);
    if (attempt.trigger) lines.push(`attempt ${index + 1} trigger: ${attempt.trigger}`);
  });
  if (!lines.length) return "";
  return `<details><summary>Technical detail</summary><p class="tc-chunk-text">${escapeHtml(lines.join("\n"))}</p></details>`;
}

function diagnosisText(value) {
  if (!value) return "";
  if (value === "Diagnosis not yet attributed.") return value;
  if (OV_DIAGNOSES[value]) return OV_DIAGNOSES[value];
  // Recovery reasons arrive as "unsupported_generation: regenerate ...".
  // Show the class label, not the code name. Other text (answers included)
  // passes through untouched.
  const pattern = /\b(unsupported_generation|retrieval_miss|evidence_insufficiency)\b/g;
  const text = String(value);
  if (!pattern.test(text)) return text;
  const labeled = text.replace(pattern, (name) => OV_DIAGNOSES[name].toLowerCase());
  return labeled.charAt(0).toUpperCase() + labeled.slice(1);
}

function clipFlight(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= 72) return text;
  return `${text.slice(0, 71)}…`;
}

function formatScore(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return number.toFixed(3);
}

function formatFlightLatency(ms) {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}

async function inspectOverviewRun(runId) {
  if (!runId) return;
  setEvalTab("runs");
  applyView();
  const row = (state.logicalRuns || []).find(
    (run) =>
      run.inspect_run_id === runId ||
      run.logical_run_id === runId ||
      (run.trace_ids || []).includes(runId)
  );
  if (!row) {
    await selectRun(runId);
    return;
  }
  state.relFocus = row;
  await openFlight(row.trace_ids || [runId], { stay: true, stepsFor: row.inspect_run_id || runId });
}

// Placeholder in the shape of the page while the overview loads, so the
// first paint is the layout, not a blank canvas.
function overviewSkeleton() {
  const node = `<li class="loop-stage"><span class="loop-node skeleton"></span><span class="skeleton sk-line sk-short"></span><span class="skeleton sk-line"></span></li>`;
  const card = (lines) => `<section class="ov-panel sk-card">${'<span class="skeleton sk-line"></span>'.repeat(lines)}</section>`;
  return `<div class="ov-hero" aria-busy="true" aria-label="Loading overview">
      <section class="ov-loop"><ol class="loop-map is-funnel">${node.repeat(5)}</ol></section>
      <div class="ov-metrics is-side">${card(2)}${card(2)}</div>
    </div>
    <div class="ov-grid sk-grid">${card(4)}${card(4)}</div>`;
}

function renderOverview() {
  renderOverviewBody();
  if (state.overviewCountUp && state.overview) {
    state.overviewCountUp = false;
    countUp($("overview-body"));
  }
}

function renderOverviewBody() {
  const root = $("overview-body");
  const lead = $("overview-lead");
  if (!root) return;
  if (state.overviewError && !state.overview) {
    if (lead) lead.textContent = "Overview could not be loaded.";
    root.innerHTML = `<p class="ov-empty">${escapeHtml(state.overviewError)}</p>`;
    return;
  }
  const data = state.overview;
  if (!data) {
    if (lead) lead.textContent = "How reliable this RAG system is right now.";
    root.innerHTML = overviewSkeleton();
    return;
  }
  if (lead) lead.textContent = data.summary || "How reliable this RAG system is right now.";
  const judged = data.judged_runs || 0;
  const observed = data.observed_runs || 0;
  root.innerHTML = `
    ${overviewMetrics(data)}
    ${observed && !judged ? `<p class="ov-note">Recorded runs so far were not judged. Run a loop test to measure runtime reliability.</p>` : ""}
    <section class="ov-panel">
      <h2>Needs attention</h2>
      ${overviewAttention(data)}
    </section>
    <div class="ov-grid">
      <section class="ov-panel">
        <h2>Recovery outcomes</h2>
        ${overviewOutcomes(data)}
      </section>
      <section class="ov-panel">
        <h2>Runtime signals <span class="ov-kicker">Initial → final</span>${infoTip("Runtime judge signals, not ground-truth accuracy. A null answer-supported flag is omitted, not treated as false.")}</h2>
        ${overviewSignals(data)}
      </section>
    </div>
    <div class="ov-grid">
      <section class="ov-panel">
        <h2>Failure diagnoses${infoTip("Observed failure classes. Retrieval miss and evidence insufficiency can be assigned after a rewrite.")}</h2>
        ${overviewDiagnoses(data)}
      </section>
      <section class="ov-panel">
        <h2>Applied recovery actions${infoTip("Applied actions only. A final improvement is not credited separately to each action in a chain.")}</h2>
        ${overviewActions(data)}
      </section>
    </div>
    <section class="ov-panel">
      <div class="ov-panel-head">
        <h2>Recent activity</h2>
        ${overviewLatency(data.latency)}
      </div>
      ${overviewActivity(data)}
    </section>
    ${judged ? "" : `<p class="ov-note"><a href="#test">Run a loop test</a> to begin measuring runtime reliability.</p>`}
  `;
}

// Overview hero: the agent loop as a funnel over every recorded run, with the
// two attention numbers beside it. Same counts the old five cards showed.
function overviewMetrics(data) {
  const required = data.recovery_required || {};
  const verified = data.verified_improved || {};
  const outcomes = data.outcomes || {};
  const ofText = (bucket, suffix) =>
    bucket.total ? `${formatPercent(bucket.rate) || "0%"} ${suffix}` : "";
  const stages = [
    { key: "retrieve", label: "Retrieve", value: data.observed_runs || 0, note: "runs recorded" },
    { key: "judge", label: "Judge", value: data.judged_runs || 0, note: data.judged_runs ? "judged at runtime" : "no judged runs yet" },
    {
      key: "diagnose",
      label: "Needs recovery",
      value: required.count || 0,
      note: ofText(required, "of judged runs") || "nothing judged",
      tone: required.count ? "flagged" : "",
    },
    { key: "recover", label: "Recover", value: outcomes.applied || 0, note: "recoveries applied" },
    {
      key: "verify",
      label: "Verified improved",
      value: verified.total ? `${verified.count || 0}/${verified.total}` : "—",
      note: ofText(verified, "of applied recoveries") || "no applied recoveries",
      tone: verified.count ? "pass" : "",
    },
  ];
  const funnel = stages
    .map((stage) => {
      const empty = stage.value === 0 || stage.value === "—";
      const state = empty ? "skipped" : stage.tone || "done";
      return `<li class="loop-stage is-${stage.key} is-${state}">
        <span class="loop-node">${icon(STAGE_ICONS[stage.key], 15)}</span>
        <span class="loop-text">
          <span class="loop-value" data-count>${escapeHtml(String(stage.value))}</span>
          <span class="loop-label">${escapeHtml(stage.label)}</span>
          <span class="loop-note">${escapeHtml(stage.note)}</span>
        </span>
      </li>`;
    })
    .join("");
  return `<div class="ov-hero">
    <section class="ov-loop" aria-label="Agent loop across all runs">
      <div class="ov-loop-head"><h2>Agent loop</h2><span>All recorded runs in this system</span></div>
      <ol class="loop-map is-funnel">${funnel}</ol>
    </section>
    <div class="ov-metrics is-side">
    ${metric(
      "Unresolved",
      String(data.unresolved || 0),
      "Pending, still failing, or degraded. Safe stops are not included.",
      data.unresolved ? "is-attention" : ""
    )}
    ${metric(
      "Safe stops",
      String(data.safe_stops || 0),
      "Bounded recovery stopped. Not an improved answer."
    )}
    </div>
  </div>`;
}

function metric(label, value, sub, tone = "") {
  return `<div class="ov-metric ${tone}">
    <div class="ov-metric-k">${escapeHtml(label)}</div>
    <div class="ov-metric-v" data-count>${escapeHtml(value)}</div>
    <div class="ov-metric-s">${escapeHtml(sub)}</div>
  </div>`;
}

function rateMetric(label, bucket, ofLabel, emptyLabel) {
  const total = bucket.total || 0;
  const count = bucket.count || 0;
  if (!total) {
    return metric(label, "—", emptyLabel);
  }
  const percent = formatPercent(bucket.rate);
  return `<div class="ov-metric">
    <div class="ov-metric-k">${escapeHtml(label)}</div>
    <div class="ov-metric-v">${count}<span class="ov-metric-of"> / ${total}</span></div>
    <div class="ov-metric-s">${escapeHtml(percent ? `${percent} ${ofLabel}` : ofLabel)}</div>
  </div>`;
}

function overviewAttention(data) {
  const items = data.needs_attention || [];
  if (!items.length) return `<p class="ov-empty is-clear">${icon("check", 14)} No unresolved recovery runs.</p>`;
  return `<ul class="ov-list">${items.map((item) => `<li class="ov-row">
      <div class="ov-row-main">
        <div class="ov-query" title="${escapeHtml(item.query || "")}">${escapeHtml(item.query || "Untitled run")}</div>
        <div class="ov-sub">${escapeHtml(attentionLine(item))}</div>
      </div>
      <div class="ov-row-side">
        ${outcomeBadge(item.pending ? "pending" : item.verification)}
        <span class="ov-time">${escapeHtml(formatStamp(item.timestamp))}</span>
        <button type="button" class="btn btn-ghost btn-sm" data-inspect-run="${escapeHtml(item.inspect_run_id)}">Inspect</button>
      </div>
    </li>`).join("")}</ul>`;
}

function attentionLine(item) {
  const diagnosis = (item.diagnoses || []).map(labelDiagnosis).filter(Boolean).join(", ");
  if (item.pending) {
    const proposal = `Recovery proposed: ${labelAction(item.action)} → awaiting confirmation`;
    return diagnosis ? `${diagnosis} → ${proposal}` : proposal;
  }
  const actions = (item.actions || []).map(labelAction).join(" → ");
  const outcome = OV_OUTCOMES[item.verification] || "";
  return [diagnosis, actions, outcome].filter(Boolean).join(" → ");
}

function overviewOutcomes(data) {
  const outcomes = data.outcomes || {};
  const total = outcomes.with_outcome || 0;
  if (!outcomes.applied) return `<p class="ov-empty">No recovery attempts yet.</p>`;
  if (!total) return `<p class="ov-empty">Recovery was applied, but none of those runs have a verification outcome yet.</p>`;
  const rows = ["improved", "unchanged", "still_failing", "degraded"]
    .map((name) => barRow(OV_OUTCOMES[name], outcomes[name] || 0, total, name))
    .join("");
  const other = outcomes.other
    ? barRow("Other", outcomes.other, total, "other")
    : "";
  const missing = (outcomes.applied || 0) - total;
  const note = missing > 0 ? `<p class="ov-sub">${missing} applied ${missing === 1 ? "recovery has" : "recoveries have"} no verification outcome and ${missing === 1 ? "is" : "are"} not in this split.</p>` : "";
  return `${rows}${other}<p class="ov-sub">${total} applied ${total === 1 ? "recovery" : "recoveries"} with a final verification outcome.</p>${note}`;
}

function overviewSignals(data) {
  const judged = data.judged_runs || 0;
  if (!judged) return `<p class="ov-empty">No judged runs yet.</p>`;
  const signals = data.signals || {};
  return `${signalRow("Evidence sufficient", signals.evidence_sufficient)}
    ${signalRow("Answer supported", signals.answer_supported)}
`;
}

function signalRow(label, pair) {
  const initial = (pair && pair.initial) || {};
  const final = (pair && pair.final) || {};
  return `<div class="ov-signal">
    <div class="ov-signal-name">${escapeHtml(label)}</div>
    <div class="ov-signal-values">
      <span><em>Initial</em> ${escapeHtml(signalPercent(initial))}</span>
      <span class="ov-arrow" aria-hidden="true">→</span>
      <span><em>Final</em> ${escapeHtml(signalPercent(final))}</span>
    </div>
    <div class="ov-sub">${escapeHtml(signalCount(initial))} → ${escapeHtml(signalCount(final))}</div>
  </div>`;
}

function signalPercent(bucket) {
  if (!bucket || !bucket.total) return "—";
  return formatPercent(bucket.rate) || "—";
}

function signalCount(bucket) {
  if (!bucket || !bucket.total) return "no judged value";
  return `${bucket.true} of ${bucket.total}`;
}

function overviewDiagnoses(data) {
  const rows = data.diagnoses || [];
  const unattributed = data.unattributed || 0;
  if (!rows.length && !unattributed) return `<p class="ov-empty">No failure diagnoses yet.</p>`;
  const max = Math.max(...rows.map((row) => row.count || 0), unattributed, 1);
  const unattributedRow = unattributed ? barRow("Not attributed", unattributed, max, "diagnosis") : "";
  return `${rows.map((row) => barRow(labelDiagnosis(row.name), row.count || 0, max, "diagnosis")).join("")}${unattributedRow}`;
}

function overviewActions(data) {
  const rows = data.applied_actions || [];
  const pending = data.pending_actions || [];
  if (!rows.length && !pending.length) return `<p class="ov-empty">No recovery attempts yet.</p>`;
  const max = Math.max(1, ...rows.map((row) => row.count || 0));
  const bars = rows.length
    ? rows.map((row) => barRow(labelAction(row.name), row.count || 0, max, "action")).join("")
    : `<p class="ov-empty">No applied recoveries yet.</p>`;
  const pendingLine = pending.length
    ? `<p class="ov-sub">Pending, not applied: ${escapeHtml(pending.map((row) => `${labelAction(row.name)} ${row.count}`).join(" · "))}</p>`
    : "";
  return `${bars}${pendingLine}`;
}

function overviewActivity(data) {
  const rows = data.recent_activity || [];
  if (!rows.length) return `<p class="ov-empty">No runs yet.</p>`;
  return `<table class="ov-table">
    <thead><tr>
      <th>Question</th><th>Initial</th><th>Recovery</th><th>Verification</th><th>Latency</th><th></th>
    </tr></thead>
    <tbody>${rows.map((row) => `<tr class="ov-activity" data-inspect-run="${escapeHtml(row.inspect_run_id)}">
      <td><div class="ov-query" title="${escapeHtml(row.query || "")}">${escapeHtml(row.query || "Untitled run")}</div><div class="ov-sub">${escapeHtml(formatStamp(row.timestamp))}</div></td>
      <td>${escapeHtml(OV_STATES[row.initial_state] || "Not judged")}</td>
      <td>${escapeHtml(recoveryCell(row))}</td>
      <td>${verificationCell(row)}</td>
      <td class="tnum">${escapeHtml(formatLatency(row.latency_ms))}</td>
      <td><button type="button" class="btn btn-ghost btn-sm" data-inspect-run="${escapeHtml(row.inspect_run_id)}">Inspect</button></td>
    </tr>`).join("")}</tbody>
  </table>`;
}

function recoveryCell(row) {
  if (row.recovery_pending) return `Pending: ${labelAction(row.recovery_pending)}`;
  if (row.recovery && row.recovery.length) {
    return row.recovery
      .map((name) => (row.safe_stop && name === "abstain" ? "Safe stop" : labelAction(name)))
      .join(" → ");
  }
  return "No recovery";
}

function verificationCell(row) {
  if (row.safe_stop) return outcomeBadge("safe_stop");
  if (row.recovery_pending) return outcomeBadge("pending");
  if (row.verification) return outcomeBadge(row.verification);
  return `<span class="ov-quiet">—</span>`;
}

function overviewLatency(latency) {
  if (!latency || latency.median_ms == null) return `<p class="ov-sub">No latency recorded.</p>`;
  const runs = latency.runs || 0;
  return `<p class="ov-sub" title="${escapeHtml(latency.definition || "")}">Median ${escapeHtml(formatLatency(latency.median_ms))} across ${runs} ${runs === 1 ? "run" : "runs"}</p>`;
}

function barRow(label, count, total, tone) {
  const width = total > 0 ? Math.max(0, Math.min(100, (count / total) * 100)) : 0;
  return `<div class="ov-bar" title="${escapeHtml(`${label}: ${count}`)}">
    <span class="ov-bar-label">${escapeHtml(label)}</span>
    <span class="ov-bar-track"><span class="ov-bar-fill is-${escapeHtml(tone)}" style="width:${width}%"></span></span>
    <span class="ov-bar-count">${count}</span>
  </div>`;
}

function outcomeBadge(name) {
  const label = name === "pending" ? "Recovery pending" : name === "safe_stop" ? "Safe stop" : OV_OUTCOMES[name] || name || "—";
  const tone = name === "pending" ? "pending" : name || "neutral";
  const glyph = {
    improved: "check",
    unchanged: "minus",
    pending: "clock",
    still_failing: "alert-circle",
    degraded: "x",
    safe_stop: "info",
  }[name] || "minus";
  return `<span class="ov-badge is-${escapeHtml(tone)}">${icon(glyph, 12)} ${escapeHtml(label)}</span>`;
}

function labelAction(name) {
  if (!name) return "Recovery";
  return OV_ACTIONS[name] || String(name).replaceAll("_", " ");
}

function labelDiagnosis(name) {
  if (!name) return "";
  return OV_DIAGNOSES[name] || String(name).replaceAll("_", " ");
}

function formatPercent(rate) {
  if (rate == null || Number.isNaN(Number(rate))) return "";
  return `${Math.round(Number(rate) * 100)}%`;
}

function formatLatency(ms) {
  if (ms == null || Number.isNaN(Number(ms))) return "—";
  const value = Number(ms);
  if (value >= 10000) return `${Math.round(value / 1000)}s`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
  return `${Math.round(value)}ms`;
}

function formatStamp(value) {
  return window.ReliabilityView.formatWhen(value);
}

async function boot() {
  hydrateIcons();
  state.navCollapsed = initialNavCollapsed();
  applyView();
  applyEvalTab();
  renderExamples();
  bind();
  bindShell();
  render();
  try {
    await loadMeta();
    await loadCorpora();
    await loadTraces();
    await loadDocuments().catch(() => {
      state.documents = [];
    });
    await loadKeys();
    render();
    renderPlaygroundKnowledge();
  } catch (error) {
    if (!state.meta) renderEnvStatus();
    showError(error.message || String(error));
    renderPlaygroundKnowledge();
  }
}

boot();
