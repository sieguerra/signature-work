# Gold set: AI review (not a student sign-off)

Reviewer: AI assistant (Cursor), 2026-10-11. This is a machine review requested
by the student to speed up issue #99. It does **not** replace the student
sign-off that #99 requires, and no `audit.jsonl` row was changed. Rows stay
`"auditor": "substring-search"` until the student confirms them.

Scope: all 88 rows in `datasets/gold/`, `datasets/dku/gold/`, and
`datasets/kestrel-aero/gold/`.

## Method

- Answerable rows (64): read the question, the gold answers, and the cited
  note; checked that the first gold answer is in that note and answers the
  question asked.
- Unanswerable rows (24): searched the whole collection for the requested fact
  with `rg` on the key terms, and read the matching lines.
- Scoring check: ran `swrag.evaluation.scoring.contains_answer` on deliberately
  wrong answers to see whether short aliases accept them.

## Result: every answer is in its note

All 64 answerable rows: the gold answer appears in the cited note and answers
the question. No row has a wrong answer or a wrong supporting file.

All 24 unanswerable rows: the requested fact is absent from the collection. In
most cases the collection says so explicitly, for example
`tideline-shuttle.txt` ("There is no shuttle stop at the boat museum"),
`tideline-winter-recess.txt` ("Recess dates … are not listed here"),
`dku-about.txt` ("does not list tuition, enrollment headcounts, or the names of
current officers"), and `kestrel-aero/corpus/omitted.txt`.

## Problem 1: short aliases make the contains-answer score accept wrong answers

`contains_answer` lowercases the answer, strips punctuation, and checks whether
any gold string is a **substring**. It does not require a whole word and does
not remove citations. Generated answers end with chunk citations such as
`[meetings::c000]`, which normalize to `meetingsc000`, so every answer carries
digits.

Observed with the real scorer:

| Row | Wrong answer tested | Accepted? |
|---|---|---|
| seed-002 (gold `Level 3` / `3`) | "The quiet study floor is Level 1 [harbor-library-2019-notice#3]." | yes |
| gold-023 (gold `Level 2` / `2`) | "The quiet floor is Level 3; group rooms are on Level 1 [annex-2]." | yes |
| ka-011 (gold `no` / `does not cut titanium`) | "Yes, Shop 6 cuts titanium on mill M-11 [shop-6] and has no titanium tank." | yes |

`no` also matches inside "not", "note", "know", and "North".

High risk (one or two characters, or a word fragment):
seed-002 `3`, seed-004 `15`, seed-005 `31`, gold-014 `10`, gold-016 `3`,
gold-019 `19`, gold-020 `30`, gold-021 `2`, gold-022 `1`, gold-023 `2`,
dku-010 `3`, ka-011 `no`.

Cross-question collisions (a three-digit alias that is also a different fact in
the same collection):
- gold-018 `214` (Storm Ledger reports) and gold-032 `214` (Coastal Memory
  room). "Room 214" would score correct for gold-018.
- dku-005 `200` (campus acres) and dku-028 `200` (guest rooms). "200 acres"
  would score correct for dku-028.

Low risk: dku-009 `560`, dku-025 `1893`, dku-026 `1924`, dku-027 `300`,
dku-030 `36657053`, seed-006 `7pm`, gold-017 `8pm`, dku-010 `3rd`.

Exact match and token F1 are not affected the same way; this is a
contains-answer problem.

**Fixed (2026-10-11, branch `fix/contains-answer-whole-word`).**
`contains_answer` now removes bracketed citations and requires a gold alias to
match whole words. Rescoring the committed Harbor snapshot
`experiments/results/20260910T070623/` in memory with the fixed scorer gives
the same answerable contains-answer as recorded: 19/22 for both baseline and
eval-guided. No answer in that snapshot was accepted only because of a loose
alias. The snapshot files were not rewritten.

## Problem 2: some notes tell the model the answer is missing

`kestrel-aero/corpus/omitted.txt` says the prices, owner name, and ITAR numbers
are omitted "so those questions are unanswerable from local evidence." Several
DKU notes end with "This note does not list …". That makes ka-013, ka-014,
ka-015, and several DKU unanswerable rows easier to abstain on than an
unanswerable question in a real collection would be. It is not a gold error,
but abstention rates on these rows should be described with that in mind.

## Minor notes

- dku-010: alias `Level 3` is not the note's wording ("3rd floor"); harmless
  for scoring once whole-word matching is used.
- dku-028: the note says "over 200"; the bare `200` alias drops "over".
- gold-028: unanswerable because North Jetty mentions a soldering bench, not a
  wet bench. A correct system answer may explain that rather than use the exact
  abstention phrase, so check how `looks_like_abstention` scores those answers.

## What the student still needs to do for #99

1. Skim this review and the worksheet. For the 64 answerable rows the passages
   are already shown; a quick read is enough.
2. Decide what to do about Problem 1. Committed Harbor questions are not edited
   (issue #99). The options are a scorer fix (whole-word match, citations
   removed before matching) or reporting contains-answer with this caveat.
3. Sign off. Only then do the `audit.jsonl` rows change from
   `substring-search` to the student's name.
