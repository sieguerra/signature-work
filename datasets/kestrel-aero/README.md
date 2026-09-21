# Kestrel Aero Components

**Industry:** Aerospace machining

A made-up machine shop in Red Mesa. Hangar 2 cuts titanium; Shop 6 cuts aluminum. 2018 vs 2025 spec letters disagree.

Fictional on purpose (ADR 003 / ADR 010). Not a real company. 16 notes, 16 gold questions.

`gold/recovery.jsonl` (`ka-017`–`ka-019`) is an issue #32 split: the traveler
question does not name 2018 vs 2025. Emit overwrites `questions.jsonl` only.

`gold/first-pass-fail.jsonl` (`ka-020`–`ka-024`) is an issue #69 split:
answerable questions that miss the supporting note at `top_k=1` and hit it
at `top_k=8`, plus one unanswerable row. Use
`experiments/configs/v3_kestrel_expand_vs_loop.json` (`max_recoveries: 2`).
Do not quote scores until you have confirmed the spans.

