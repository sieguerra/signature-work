// Light / dark theme. The preference is "light" (the default), "dark", or
// "system" (follow the OS); the
// applied theme is always "light" or "dark" on <html data-theme>. index.html
// runs the same resolution inline before first paint so there is no flash.

(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Theme = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const KEY = "swrag.theme";
  const PREFS = ["system", "light", "dark"];
  const DEFAULT_PREF = "light";

  function normalize(pref) {
    return PREFS.includes(pref) ? pref : DEFAULT_PREF;
  }

  function resolveTheme(pref, systemPrefersLight) {
    const p = normalize(pref);
    if (p === "system") return systemPrefersLight ? "light" : "dark";
    return p;
  }

  // The top-bar button flips to the opposite of what is on screen and makes
  // that an explicit choice.
  function toggled(applied) {
    return applied === "light" ? "dark" : "light";
  }

  function systemPrefersLight() {
    try {
      return window.matchMedia("(prefers-color-scheme: light)").matches;
    } catch {
      return false;
    }
  }

  function readPref() {
    try {
      return normalize(localStorage.getItem(KEY));
    } catch {
      return DEFAULT_PREF;
    }
  }

  function apply(pref) {
    const p = normalize(pref);
    const theme = resolveTheme(p, systemPrefersLight());
    const html = document.documentElement;
    html.dataset.theme = theme;
    html.dataset.themePref = p;
    try {
      localStorage.setItem(KEY, p);
    } catch {
      /* private mode: the choice lasts for this page only */
    }
    document.dispatchEvent(new CustomEvent("themechange", { detail: { pref: p, theme } }));
    return theme;
  }

  function current() {
    return document.documentElement.dataset.theme === "light" ? "light" : "dark";
  }

  function watchSystem() {
    try {
      window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => {
        if (readPref() === "system") apply("system");
      });
    } catch {
      /* older browsers: the theme updates on next load */
    }
  }

  return { KEY, PREFS, DEFAULT_PREF, normalize, resolveTheme, toggled, readPref, apply, current, watchSystem };
});
