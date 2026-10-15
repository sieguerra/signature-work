# Frontend audit (Oct 2026)

Scope: `web/index.html`, `web/styles.css`, `web/app.js`, `web/charts.js` as of the start of the UI pass. Phase 1 (tokens) and Phase 2 (shell + primitives) were done after this audit; Playground and Evaluation internals were deliberately left for a later pass.

## Findings

**Duplicated styles.** `styles.css` was ~3,000 lines with repeated overrides: two separate `@media (max-width: 960px)` blocks that fight each other, `.pg-palette` / `.pg-inspect` rules declared more than once, and base `button`/`input`/`select` rules re-patched per feature.

**Inconsistent scales.** 15 distinct font sizes (9–28px, including 10.5 / 11.5 / 12.5), 13 radius values, ad-hoc paddings. No spacing scale.

**Excessive borders.** 54 one-pixel borders; almost every region is an identical bordered card, so nothing reads as primary. The Evaluation overview has ~10 cards of equal weight.

**Weak hierarchy.** Heavy use of uppercase tracked micro-labels; the old sidebar status line was a small monospace string that was hard to read; page titles and section titles were close in size.

**Hard-coded colors.** `#0e1118` appeared 11×, plus several other hex/rgba values in feature CSS. `charts.js` hard-codes ~12 hex colors (`CHART_COLORS`, `DOC_PALETTE`, ring colors) that do not follow the CSS variables.

**Reusable-component candidates.** Button variants, segmented tabs (`.eval-tabs`), status pills, banners, empty states, key/value rows, metric cards, and the node card on the canvas all re-implement the same patterns.

**Accessibility.**
- Status was often a colored dot alone (node state, env status).
- The old workspace picker wrapped a `select` and a `button` inside one `label`.
- Many custom buttons had no visible focus style.
- Tooltips were `title` attributes only (no keyboard access, slow, unstyled).

**Responsive.** The two conflicting 960px blocks; the inspector and library panels do not adapt well between 960 and 1200px.

**Canvas UX (Playground, not changed yet).** Fixed grid layout, no zoom readout, no running state on nodes or edges, edges never change state, node state shown only as a 7px dot. The inspector permanently shows a key/value dump, and its Sources section repeats what the dock shows.

**Dashboard UX (Evaluation, not changed yet).** Same-weight cards with no clear reading order; the runs table is plain text.

**Contextual vs. permanent information.** The run kv dump, environment details, and counts were permanently visible. Environment details now live in a popover; the inspector dump is still permanent (left for the Playground pass).

**Visualization / animation opportunities** (only where the backend has the data):
- recovery funnel (first-pass flagged → recovered → improved / abstained)
- first-try vs. final judge checks per run
- node execution states during a run (only as "running" vs. "done": the backend exposes total `latency_ms` per run, not per-stage timings or streaming, so per-stage progress must not be faked)
- latency sparkline across runs

## What Phases 1–2 changed

- **Tokens:** palette, semantic colors (retrieval, generation, judge, recovery, success, warning, danger, abstain), surfaces, borders, text levels, spacing, radius, type, shadow, focus ring, motion, `prefers-reduced-motion`. Old variable names are kept as aliases so existing feature CSS picked up the palette.
- **Shell:** collapsible sidebar (⌘B, persisted, tooltips when collapsed), Lucide icons (`web/icons.js`), workspace switcher, compact environment indicator with popover, top bar with breadcrumb / mode badge / run state, working ⌘K command palette, toasts.
- **Primitives:** buttons, form controls, segmented tabs, badges/pills with text + icon dot, tooltips, focus-visible ring, banners, empty states, skeleton. Base styles use `:where()` so feature classes still win.

## Tech debt left

- `web/styles.css` is now generated: the shell/primitives header was spliced in front of the filtered feature CSS. Edit the file directly from here on; there is no build step in the repo.
- Legacy alias variables (`--line`, `--muted`, `--accent`, …) should be replaced with the new names when each feature area is redesigned.
- `charts.js` colors are not tokenized.
- Feature CSS for Playground and Evaluation still carries its old duplicated rules and radius/size values.
- ADR 008 (static HTML/CSS/JS, no Node toolchain) rules out shadcn, React Flow, and Tremor unless that decision is revisited.
