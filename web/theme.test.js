const assert = require("node:assert/strict");
const test = require("node:test");
const { resolveTheme, toggled, normalize } = require("./theme.js");

test("system follows the OS, explicit choices win", () => {
  assert.equal(resolveTheme("system", true), "light");
  assert.equal(resolveTheme("system", false), "dark");
  assert.equal(resolveTheme("light", false), "light");
  assert.equal(resolveTheme("dark", true), "dark");
});

test("unknown or missing preferences fall back to light, the default", () => {
  assert.equal(normalize(null), "light");
  assert.equal(normalize("sepia"), "light");
  assert.equal(resolveTheme(undefined, false), "light");
  assert.equal(resolveTheme("system", false), "dark");
});

test("the toggle flips what is on screen", () => {
  assert.equal(toggled("dark"), "light");
  assert.equal(toggled("light"), "dark");
});
