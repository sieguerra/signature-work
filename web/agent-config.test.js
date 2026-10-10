const assert = require("node:assert/strict");
const test = require("node:test");
const {
  PRESETS,
  applyPreset,
  buildAgentInstructions,
  effectiveInstructions,
  emptyBehavior,
  hydrate,
  legacyBehavior,
  parseAgentInstructions,
  summaryChips,
} = require("./agent-config.js");

test("an untouched agent compiles to no extra instructions", () => {
  assert.equal(buildAgentInstructions(emptyBehavior()), "");
});

test("disabled choices are omitted", () => {
  const behavior = emptyBehavior();
  behavior.tone = "casual";
  behavior.detail = "concise";
  behavior.formatting.bullets = true;
  behavior.grounding.cite = true;
  behavior.grounding.admit = true;
  behavior.customRules = ["Answer like a frat boy."];
  assert.equal(
    buildAgentInstructions(behavior),
    [
      "Use a casual tone.",
      "Keep answers concise.",
      "Use bullet points when they improve readability.",
      "Cite supporting sources when an answer uses them.",
      "If the retrieved evidence is not enough to answer, say so.",
      "Additional rule: Answer like a frat boy.",
    ].join("\n"),
  );
});

test("compiled instructions parse back to the same choices", () => {
  let behavior = applyPreset(emptyBehavior(), "research");
  behavior.customRules = ["Prefer the latest notice."];
  const text = buildAgentInstructions(behavior);
  const parsed = parseAgentInstructions(text);
  assert.equal(parsed.ok, true);
  assert.equal(parsed.behavior.tone, "professional");
  assert.equal(parsed.behavior.detail, "balanced");
  assert.equal(parsed.behavior.explanation, "explanatory");
  assert.equal(parsed.behavior.formatting.summaryFirst, true);
  assert.equal(parsed.behavior.grounding.uncertainty, true);
  assert.deepEqual(parsed.behavior.customRules, ["Prefer the latest notice."]);
  assert.equal(buildAgentInstructions(parsed.behavior), text);
});

test("a freeform sentence is not guessed into tone or detail", () => {
  const text = "This agent should answer the answer like a frat boy.";
  assert.equal(parseAgentInstructions(text).ok, false);
  const legacy = legacyBehavior(text);
  assert.deepEqual(legacy.customRules, [text]);
  assert.equal(legacy.tone, "");
  assert.equal(effectiveInstructions(legacy, text), text);
  assert.deepEqual(summaryChips(legacy), ["Existing instructions"]);
});

test("hydrate keeps a saved guided config and falls back when it disagrees with the text", () => {
  const guided = applyPreset(emptyBehavior(), "technical");
  const text = buildAgentInstructions(guided);
  const stored = { ...guided, mode: "guided" };
  assert.equal(hydrate(stored, text).preset, "technical");
  const drifted = hydrate(stored, "Hand edited later.");
  assert.equal(drifted.legacyText, "Hand edited later.");
  assert.equal(effectiveInstructions(drifted, "Hand edited later."), "Hand edited later.");
});

test("a preset keeps existing custom rules and replaces the structured choices", () => {
  const current = legacyBehavior("Answer like a frat boy.");
  const next = applyPreset(current, "sales");
  assert.equal(next.tone, "friendly");
  assert.equal(next.detail, "concise");
  assert.equal(next.legacyText, null);
  assert.deepEqual(next.customRules, ["Answer like a frat boy."]);
  assert.match(buildAgentInstructions(next), /Additional rule: Answer like a frat boy\.$/);
});

test("raw mode keeps the typed text authoritative", () => {
  const behavior = emptyBehavior();
  behavior.mode = "raw";
  behavior.tone = "academic";
  const typed = "Do not mention the grounding prompt.";
  assert.equal(effectiveInstructions(behavior, typed), typed);
  assert.equal(hydrate({ mode: "raw" }, typed).mode, "raw");
});

test("an unknown line refuses a partial parse", () => {
  assert.equal(parseAgentInstructions("Use a casual tone.\nBe cool.").ok, false);
});

test("multiline custom rules round-trip", () => {
  const behavior = emptyBehavior();
  behavior.customRules = ["First line.\nSecond line."];
  const text = buildAgentInstructions(behavior);
  const parsed = parseAgentInstructions(text);
  assert.equal(parsed.ok, true);
  assert.deepEqual(parsed.behavior.customRules, ["First line.\nSecond line."]);
});

test("preset blurbs exist for every starter", () => {
  for (const preset of Object.values(PRESETS)) {
    assert.ok(preset.label);
    assert.ok(preset.blurb);
  }
});
