// Static snapshot mode. Loaded only by the page that scripts/build_static_demo.py
// writes. It answers the console's GET /api/* requests from JSON files saved
// next to the page, so the whole UI works on any static host. Anything that
// would change data or run the model is refused with a plain explanation.

(function () {
  const realFetch = window.fetch.bind(window);
  const base = new URL(".", document.baseURI);
  const READ_ONLY =
    "This is a read-only snapshot of recorded runs. Asking new questions needs the live version or a local install.";

  function json(status, body) {
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  }

  window.fetch = function (input, init) {
    const raw = typeof input === "string" ? input : input.url;
    const url = new URL(raw, window.location.href);
    const method = ((init && init.method) || (typeof input !== "string" && input.method) || "GET").toUpperCase();
    if (!url.pathname.startsWith("/api/") && !raw.startsWith("/api/")) return realFetch(input, init);
    const path = raw.startsWith("/api/") ? raw.split("?")[0] : url.pathname;
    if (method !== "GET") return Promise.resolve(json(403, { detail: READ_ONLY }));
    const file = new URL(path.replace(/^\//, "") + ".json", base);
    return realFetch(file).then((response) =>
      response.ok ? response : json(404, { detail: "Not part of this snapshot." })
    );
  };
})();
