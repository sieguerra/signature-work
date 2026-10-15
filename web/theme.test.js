const assert = require("node:assert/strict");
const test = require("node:test");
const { resolveTheme, toggled, normalize } = require("./theme.js");

test("system follows the OS, explicit choices win", () => {
  assert.equal(resolveTheme("system", true), "light");
  assert.equal(resolveTheme("system", false), "dark");
  assert.equal(resolveTheme("light", false), "light");
  assert.equal(resolveTheme("dark", true), "dark");
});

test("unknown or missing preferences fall back to system", () => {
  assert.equal(normalize(null), "system");
  assert.equal(normalize("sepia"), "system");
  assert.equal(resolveTheme(undefined, true), "light");
});

test("the toggle flips what is on screen", () => {
  assert.equal(toggled("dark"), "light");
  assert.equal(toggled("light"), "dark");
});
