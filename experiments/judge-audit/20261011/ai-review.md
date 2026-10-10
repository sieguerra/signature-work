# Judge audit: AI second-rater review (not the human audit)

Reviewer: AI assistant (Cursor), 2026-10-11, at the student's request. Issue
#38 requires a human to label the sample. These labels are not that. They are
a second rater, and they were **not blind**: the reviewer saw the judge's
verdicts before labeling. Treat the agreement below as an upper-biased cross
check, not as the human-agreement number ADR 003 asks for.

`labels.jsonl` still has `human_sufficient` and `human_supported` set to null.

## Sample

40 judge calls from the #100 runs (`experiments/results/20261010T203121/`,
`20261010T203115/`, `20261010T202849/`), seed 38:

- 20 `recovery_trigger`: every first-pass judge call that started a recovery
  and returned a non-null support flag (Harbor 5, DKU 11, Kestrel 4)
- 20 `accepted`: random accepted runs (Harbor 8, DKU 8, Kestrel 4)

Rubric is the one in `worksheet.md`.

## Agreement, AI rater vs judge (n = 40)

| Flag | Agree | Disagree |
|---|---|---|
| Evidence sufficient | 39 | 1 |
| Answer supported | 38 | 2 |

By stratum: `recovery_trigger` 20/20 sufficient, 18/20 supported;
`accepted` 19/20 sufficient, 20/20 supported.

## Disagreements

- **Item 30 (Harbor, accepted).** "How many hours did the 1921 Green Lamp Flood
  last according to the Storm Ledger Unit?" The Storm Ledger note says it holds
  no Green Lamp Flood material. The answer reports the Coastal Memory Group's
  31 hours. The judge called the evidence sufficient and the answer supported,
  so the run was accepted. The AI rater calls the evidence insufficient for the
  question asked. This is the wrong-source trap the question was written for.
- **Item 24 (DKU, recovery trigger).** Enrollment question. The answer says the
  evidence has no enrollment figure and that it does not know. The judge called
  that answer unsupported; the AI rater calls it supported.
- **Item 25 (DKU, recovery trigger), borderline.** The evidence says no
  breakfast hours are *listed* for Executive Dining. The answer says the venue
  has no breakfast hours. The judge called it supported; the AI rater did not.

Item 18 (Annex group-room lead time) is also borderline on sufficiency. The
judge and the AI rater both said insufficient.

## Limits

- Not blind, and not human. A human label set is still required for #38.
- 16 of the 40 rows are unanswerable questions whose notes say outright that
  the fact is missing. Those are easy to agree on and push agreement up.
- One model run per corpus; the sample is not a census of judge calls.
