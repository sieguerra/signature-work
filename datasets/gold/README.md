# Gold set

Hand-written evaluation questions over `datasets/corpus/`, per ADR 003.

These answers are the **offline ground truth** for the whole project. Every
number in the final report traces back to this file, so it is student-authored
work and must be verified by hand against the corpus.

Per ADR 003, nothing in here may be read at runtime. The pipeline sees the
`question` field only; `answers` and `answerable` exist for offline scoring.

## Format

JSON Lines — one question per line. Blank lines and lines starting with `#` are
ignored, so the file can be grouped with comments.

| Field | Required | Meaning |
|---|---|---|
| `question_id` | yes | Unique, stable. Never reuse an id for a different question |
| `question` | yes | The question as asked. This is all the pipeline sees |
| `answerable` | yes | `true` if the corpus contains the answer, `false` otherwise |
| `answers` | if answerable | Acceptable short answers. Empty when `answerable` is `false` |
| `supporting_doc_ids` | no | Which corpus documents contain the answer. Used to check retrieval |
| `notes` | no | Why this question exists, or what makes it hard |

## Writing good questions

**Keep answers short.** Exact Match and F1 are computed after normalisation
(lowercase, punctuation and articles stripped). A gold answer of
`"Level 3"` is scorable; `"The quiet study floor is on Level 3"` is not.

**List aliases.** If `08:00-21:00` and `8am to 9pm` are both acceptable, put
both in `answers`. Under-listing aliases shows up as a false failure and will
pollute the failure taxonomy.

**Name the entity explicitly.** The corpus contains deliberate near-neighbours
(ADR 004): two libraries, two teaching labs, two canteens, two archive units.
"How long is a booking held before it is cancelled?" was unambiguous when there
was one lab and is ambiguous now. Write "At the North Jetty Teaching Lab, how
long...". A question that does not name its entity has no single gold answer,
and will show up as a failure that is really a bug in the question.

**Write unanswerable questions deliberately.** They are not filler — the
corpus-gap failure class does not exist without them, and the recovery for that
class is abstention. Aim for questions that *sound* answerable from the corpus
but are not, such as asking about a service the documents mention only to deny,
or asking a near-neighbour's fact about the wrong entity.

**Target the classes you want to measure.** A question whose answer sits in one
obvious chunk tests generation. A question whose answer needs an easily-missed
detail tests retrieval. Note which you intended in `notes`.

## Current state

`questions.jsonl` is the V1 gold set (issue #5): 32 questions, 22 answerable
and 10 unanswerable. Every corpus document is the supporting document for at
least one answerable question. Contrast pairs cover the near-neighbour
entities from ADR 004 (two libraries, two labs, two canteens, two archive
units, current vs superseded library hours, term vs recess shuttle).

Original `seed-*` ids are kept so earlier traces stay joinable. New items use
`gold-*` ids.

Every row must be checked by hand against `datasets/corpus/` before any scored
experiment. Do not edit a question after results exist for it; add a new id
instead.
