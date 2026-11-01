// Static snapshot mode. Loaded only by the page that scripts/build_static_demo.py
// writes. It answers the console's GET /api/* requests from JSON files saved
// next to the page, so the whole UI works on any static host. Anything that
// would change data or run the model is refused with a plain explanation.
// When the page lists several systems (window.GROUNDLOOP_SNAPSHOT), switching
// system is answered here too: the choice is kept for the tab and requests
// read that system's saved files.

(function () {
  const realFetch = window.fetch.bind(window);
  const base = new URL(".", document.baseURI);
  const READ_ONLY =
    "This is a read-only snapshot of recorded runs. Asking new questions needs the live version or a local install.";
  const config = window.GROUNDLOOP_SNAPSHOT || null;
  const KEY = "groundloop.snapshot.system";

  function currentSystem() {
    if (!config) return null;
    try {
      const saved = sessionStorage.getItem(KEY);
      if (saved && config.systems.includes(saved)) return saved;
    } catch (error) {
      // Storage can be blocked; fall back to the first system.
    }
    return config.default;
  }

  function chooseSystem(id) {
    try {
      sessionStorage.setItem(KEY, id);
    } catch (error) {
      // Without storage the choice lasts until the page reloads.
    }
    memory = id;
  }
  let memory = null;
  const activeSystem = () => memory || currentSystem();

  function readCorpora() {
    return realFetch(new URL("api/corpora.json", base)).then((response) => response.json());
  }

  function json(status, body) {
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  }

  window.fetch = function (input, init) {
    const raw = typeof input === "string" ? input : input.url;
    const url = new URL(raw, window.location.href);
    const method = ((init && init.method) || (typeof input !== "string" && input.method) || "GET").toUpperCase();
    if (!url.pathname.startsWith("/api/") && !raw.startsWith("/api/")) return realFetch(input, init);
    const path = raw.startsWith("/api/") ? raw.split("?")[0] : url.pathname;
    if (config && method === "POST" && path === "/api/corpus") {
      let id = null;
      try {
        id = JSON.parse((init && init.body) || "{}").id;
      } catch (error) {
        id = null;
      }
      if (!config.systems.includes(id)) return Promise.resolve(json(404, { detail: "Not part of this snapshot." }));
      chooseSystem(id);
      return readCorpora().then((list) => {
        const corpus = (list.corpora || []).find((item) => item.id === id) || { id };
        return json(200, { active_id: id, corpus, traces_dir: "" });
      });
    }
    if (method !== "GET") return Promise.resolve(json(403, { detail: READ_ONLY }));
    if (config && path === "/api/corpora") {
      return readCorpora().then((list) => json(200, { ...list, active_id: activeSystem() }));
    }
    const prefix = config ? `systems/${activeSystem()}/` : "";
    const file = new URL(prefix + path.replace(/^\//, "") + ".json", base);
    return realFetch(file).then((response) =>
      response.ok ? response : json(404, { detail: "Not part of this snapshot." })
    );
  };
})();
