// Guided agent behavior -> the instruction string the runtime already prepends
// to the grounding prompt. No DOM. The saved `instructions` string stays what
// generation reads; `behavior` only remembers the choices that produced it.

(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.AgentConfig = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const TONE_LINES = {
    professional: "Use a professional tone.",
    friendly: "Use a friendly tone.",
    casual: "Use a casual tone.",
    academic: "Use an academic tone.",
  };
  const CUSTOM_TONE_PREFIX = "Use this tone: ";
  const DETAIL_LINES = {
    concise: "Keep answers concise.",
    balanced: "Give a balanced amount of detail.",
    detailed: "Give detailed answers.",
  };
  const EXPLAIN_LINES = {
    direct: "Answer directly.",
    step: "Explain step by step when the question calls for it.",
    explanatory: "Explain the reasoning, not only the conclusion.",
  };
  const FORMAT_LINES = [
    ["bullets", "Use bullet points when they improve readability."],
    ["numbered", "Use numbered steps for procedures."],
    ["tables", "Use a table when comparing items."],
    ["summaryFirst", "Start with a short answer, then the details."],
  ];
  const GROUND_LINES = [
    ["evidence", "Base factual claims on the retrieved evidence."],
    ["cite", "Cite supporting sources when an answer uses them."],
    ["admit", "If the retrieved evidence is not enough to answer, say so."],
    ["uncertainty", "When the evidence is incomplete or ambiguous, say why."],
  ];
  const RULE_PREFIX = "Additional rule: ";

  const TONE_LABELS = {
    professional: "Professional",
    friendly: "Friendly",
    casual: "Casual",
    academic: "Academic",
  };
  const DETAIL_LABELS = { concise: "Concise", balanced: "Balanced", detailed: "Detailed" };
  const EXPLAIN_LABELS = { direct: "Direct", step: "Step-by-step", explanatory: "Explanatory" };

  function emptyFormatting() {
    return { bullets: false, numbered: false, tables: false, summaryFirst: false };
  }

  function emptyGrounding() {
    return { evidence: false, cite: false, admit: false, uncertainty: false };
  }

  function emptyBehavior() {
    return {
      mode: "guided",
      preset: "custom",
      tone: "",
      customTone: "",
      detail: "",
      explanation: "",
      formatting: emptyFormatting(),
      grounding: emptyGrounding(),
      customRules: [],
      legacyText: null,
    };
  }

  const PRESETS = {
    research: {
      label: "Research assistant",
      blurb: "Professional and evidence-first. Asks the model to cite sources and to say when the record is incomplete.",
      tone: "professional",
      detail: "balanced",
      explanation: "explanatory",
      formatting: { bullets: false, numbered: false, tables: false, summaryFirst: true },
      grounding: { evidence: true, cite: true, admit: true, uncertainty: true },
    },
    knowledge: {
      label: "Internal knowledge assistant",
      blurb: "Concise answers from this system. Asks the model to cite sources and to say when something is not in them.",
      tone: "professional",
      detail: "concise",
      explanation: "direct",
      formatting: { bullets: true, numbered: false, tables: false, summaryFirst: false },
      grounding: { evidence: true, cite: true, admit: true, uncertainty: false },
    },
    support: {
      label: "Customer support",
      blurb: "Friendly and concise, with steps when a task needs them. Asks the model not to invent policy.",
      tone: "friendly",
      detail: "concise",
      explanation: "step",
      formatting: { bullets: false, numbered: true, tables: false, summaryFirst: true },
      grounding: { evidence: true, cite: false, admit: true, uncertainty: false },
    },
    technical: {
      label: "Technical assistant",
      blurb: "Precise and detailed. Step-by-step when useful, and it may use technical terms.",
      tone: "professional",
      detail: "detailed",
      explanation: "step",
      formatting: { bullets: false, numbered: true, tables: false, summaryFirst: false },
      grounding: { evidence: true, cite: true, admit: true, uncertainty: false },
    },
    sales: {
      label: "Sales assistant",
      blurb: "Clear and concise. Asks the model not to invent product facts that are not in the sources.",
      tone: "friendly",
      detail: "concise",
      explanation: "direct",
      formatting: { bullets: true, numbered: false, tables: false, summaryFirst: true },
      grounding: { evidence: true, cite: false, admit: true, uncertainty: false },
    },
    custom: {
      label: "Custom",
      blurb: "No preset. Only the choices you turn on are written into the instructions.",
      tone: "",
      detail: "",
      explanation: "",
      formatting: emptyFormatting(),
      grounding: emptyGrounding(),
    },
  };

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function normalize(raw) {
    const base = emptyBehavior();
    const source = raw && typeof raw === "object" ? raw : {};
    base.mode = source.mode === "raw" ? "raw" : "guided";
    base.preset = Object.prototype.hasOwnProperty.call(PRESETS, source.preset) ? source.preset : "custom";
    base.tone = Object.prototype.hasOwnProperty.call(TONE_LINES, source.tone) || source.tone === "custom" ? source.tone : "";
    if (base.tone === "") base.tone = "";
    base.customTone = String(source.customTone || "").replace(/\s+/g, " ").trim().slice(0, 240);
    if (base.tone !== "custom") base.customTone = "";
    base.detail = Object.prototype.hasOwnProperty.call(DETAIL_LINES, source.detail) ? source.detail : "";
    base.explanation = Object.prototype.hasOwnProperty.call(EXPLAIN_LINES, source.explanation) ? source.explanation : "";
    FORMAT_LINES.forEach(([key]) => {
      base.formatting[key] = Boolean(source.formatting && source.formatting[key]);
    });
    GROUND_LINES.forEach(([key]) => {
      base.grounding[key] = Boolean(source.grounding && source.grounding[key]);
    });
    const rules = Array.isArray(source.customRules) ? source.customRules : [];
    base.customRules = rules
      .map((rule) => String(rule || "").trim())
      .filter(Boolean)
      .slice(0, 30);
    base.legacyText = typeof source.legacyText === "string" ? source.legacyText : null;
    return base;
  }

  function serialize(behavior) {
    const next = normalize(behavior);
    return {
      mode: next.mode,
      preset: next.preset,
      tone: next.tone,
      customTone: next.customTone,
      detail: next.detail,
      explanation: next.explanation,
      formatting: next.formatting,
      grounding: next.grounding,
      customRules: next.customRules,
      legacyText: next.legacyText,
    };
  }

  function sameBehavior(a, b) {
    return JSON.stringify(serialize(a || emptyBehavior())) === JSON.stringify(serialize(b || emptyBehavior()));
  }

  function buildAgentInstructions(behavior) {
    const config = normalize(behavior);
    const lines = [];
    if (config.tone === "custom") {
      if (config.customTone) lines.push(CUSTOM_TONE_PREFIX + config.customTone);
    } else if (TONE_LINES[config.tone]) {
      lines.push(TONE_LINES[config.tone]);
    }
    if (DETAIL_LINES[config.detail]) lines.push(DETAIL_LINES[config.detail]);
    if (EXPLAIN_LINES[config.explanation]) lines.push(EXPLAIN_LINES[config.explanation]);
    FORMAT_LINES.forEach(([key, line]) => {
      if (config.formatting[key]) lines.push(line);
    });
    GROUND_LINES.forEach(([key, line]) => {
      if (config.grounding[key]) lines.push(line);
    });
    config.customRules.forEach((rule) => {
      const parts = String(rule).split(/\n/);
      lines.push(RULE_PREFIX + parts[0]);
      for (let i = 1; i < parts.length; i += 1) lines.push(parts[i]);
    });
    return lines.join("\n");
  }

  function lineSetters() {
    const map = new Map();
    Object.entries(TONE_LINES).forEach(([tone, line]) => {
      map.set(line, (config) => {
        if (config.tone) return false;
        config.tone = tone;
        return true;
      });
    });
    Object.entries(DETAIL_LINES).forEach(([detail, line]) => {
      map.set(line, (config) => {
        if (config.detail) return false;
        config.detail = detail;
        return true;
      });
    });
    Object.entries(EXPLAIN_LINES).forEach(([explanation, line]) => {
      map.set(line, (config) => {
        if (config.explanation) return false;
        config.explanation = explanation;
        return true;
      });
    });
    FORMAT_LINES.forEach(([key, line]) => {
      map.set(line, (config) => {
        if (config.formatting[key]) return false;
        config.formatting[key] = true;
        return true;
      });
    });
    GROUND_LINES.forEach(([key, line]) => {
      map.set(line, (config) => {
        if (config.grounding[key]) return false;
        config.grounding[key] = true;
        return true;
      });
    });
    return map;
  }

  const SETTERS = lineSetters();

  function parseAgentInstructions(text) {
    const config = emptyBehavior();
    const source = String(text || "").replace(/\r\n/g, "\n");
    if (!source.trim()) return { ok: true, behavior: config };
    const lines = source.split("\n");
    let rule = null;
    const rules = [];
    function finishRule() {
      if (rule === null) return;
      const value = rule.join("\n").trim();
      if (value) rules.push(value);
      rule = null;
    }
    for (const line of lines) {
      if (rule !== null && !SETTERS.has(line) && !line.startsWith(RULE_PREFIX) && !line.startsWith(CUSTOM_TONE_PREFIX)) {
        rule.push(line);
        continue;
      }
      finishRule();
      if (!line.trim()) continue;
      if (line.startsWith(RULE_PREFIX)) {
        rule = [line.slice(RULE_PREFIX.length)];
        continue;
      }
      if (line.startsWith(CUSTOM_TONE_PREFIX)) {
        const custom = line.slice(CUSTOM_TONE_PREFIX.length).trim();
        if (!custom || config.tone) return { ok: false };
        config.tone = "custom";
        config.customTone = custom;
        continue;
      }
      const set = SETTERS.get(line);
      if (!set || !set(config)) return { ok: false };
    }
    finishRule();
    config.customRules = rules;
    config.preset = detectPreset(config);
    if (buildAgentInstructions(config) !== source.trim()) return { ok: false };
    return { ok: true, behavior: config };
  }

  function fieldsMatch(behavior, preset) {
    const config = normalize(behavior);
    if (config.tone !== preset.tone) return false;
    if (config.detail !== preset.detail) return false;
    if (config.explanation !== preset.explanation) return false;
    return FORMAT_LINES.every(([key]) => config.formatting[key] === Boolean(preset.formatting[key]))
      && GROUND_LINES.every(([key]) => config.grounding[key] === Boolean(preset.grounding[key]));
  }

  function detectPreset(behavior) {
    const found = Object.entries(PRESETS).find(([id, preset]) => id !== "custom" && fieldsMatch(behavior, preset));
    if (found) return found[0];
    return "custom";
  }

  function applyPreset(behavior, presetId) {
    const preset = PRESETS[presetId] || PRESETS.custom;
    const next = normalize(behavior);
    next.mode = "guided";
    next.legacyText = null;
    next.preset = PRESETS[presetId] ? presetId : "custom";
    next.tone = preset.tone;
    next.customTone = "";
    next.detail = preset.detail;
    next.explanation = preset.explanation;
    next.formatting = { ...emptyFormatting(), ...preset.formatting };
    next.grounding = { ...emptyGrounding(), ...preset.grounding };
    return next;
  }

  function legacyBehavior(text) {
    const next = emptyBehavior();
    const value = String(text || "");
    next.customRules = value.trim() ? [value] : [];
    next.legacyText = value;
    next.preset = "custom";
    return next;
  }

  function rawBehavior() {
    const next = emptyBehavior();
    next.mode = "raw";
    return next;
  }

  function effectiveInstructions(behavior, rawText) {
    const config = normalize(behavior);
    if (config.mode === "raw") return String(rawText || "");
    if (typeof config.legacyText === "string") return config.legacyText;
    return buildAgentInstructions(config);
  }

  function hydrate(stored, instructions) {
    const text = String(instructions || "");
    if (stored && stored.mode === "raw") return rawBehavior();
    if (stored && stored.mode === "guided") {
      const behavior = normalize(stored);
      if (effectiveInstructions(behavior, text) === text) return behavior;
      return text.trim() ? legacyBehavior(text) : emptyBehavior();
    }
    if (text.trim()) return legacyBehavior(text);
    return emptyBehavior();
  }

  function summaryChips(behavior) {
    const config = normalize(behavior);
    if (config.mode === "raw") return ["Raw instructions"];
    if (config.legacyText != null) return ["Existing instructions"];
    const chips = [];
    if (config.tone === "custom" && config.customTone) chips.push(config.customTone);
    else if (TONE_LABELS[config.tone]) chips.push(TONE_LABELS[config.tone]);
    if (DETAIL_LABELS[config.detail]) chips.push(DETAIL_LABELS[config.detail]);
    if (EXPLAIN_LABELS[config.explanation]) chips.push(EXPLAIN_LABELS[config.explanation]);
    FORMAT_LINES.forEach(([key, line]) => {
      if (config.formatting[key]) chips.push(line.replace(/\.$/, ""));
    });
    if (config.grounding.evidence) chips.push("Evidence-first");
    if (config.grounding.cite) chips.push("Citations");
    if (config.grounding.admit) chips.push("Admits gaps");
    if (config.grounding.uncertainty) chips.push("Explains uncertainty");
    if (config.customRules.length) chips.push(config.customRules.length === 1 ? "1 custom rule" : `${config.customRules.length} custom rules`);
    if (!chips.length) chips.push("Grounding prompt only");
    return chips;
  }

  return {
    PRESETS,
    TONE_LINES,
    DETAIL_LINES,
    EXPLAIN_LINES,
    FORMAT_LINES,
    GROUND_LINES,
    RULE_PREFIX,
    emptyBehavior,
    normalize,
    serialize,
    sameBehavior,
    buildAgentInstructions,
    parseAgentInstructions,
    detectPreset,
    applyPreset,
    legacyBehavior,
    rawBehavior,
    effectiveInstructions,
    hydrate,
    summaryChips,
    clone,
  };
});
