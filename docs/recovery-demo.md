# Recovery demonstrations

These questions belong to the corpus **Recovery demo (not a benchmark)**.
They are not included in the research metrics.

Open Test Console, choose that corpus, set mode to **Auto recover**, and leave
top-k at 4. That is the frozen operating point: up to two recovery attempts.

The expected path is a hypothesis about the corpus. It is not a result.
The observed path is filled only after the real runtime runs. A path that does
not happen is recorded as what the runtime actually did.

| Case | Question | Hypothesis |
|---|---|---|
| No recovery | What is the weekday opening time at the Northport Workshop? | The hours page answers it, so the run accepts. |
| Rewrite | What password does the Northport Workshop use for the red cabinet? | Password pages do not contain the code. The code is on the cabinet plate: 4419. |
| Expand | What weekday opening time is printed on the Northport Workshop hours card? | Nearby pages mention hours without the card. The card says 09:00. |
| Regenerate | What number is printed on the Northport Workshop cabinet plate? | The plate says 4419. Recovery is expected only if the first answer is unsupported. |
| Absent | What is the Northport Workshop espresso machine model? | No document contains an espresso machine. |

In Test Console, read the first answer and its evidence, then the recovery
action, then the final answer and the verification line. A failed recovery
should remain a failure on that line.

The system menu lists writable projects first, then the read-only corpora,
including **Duke Kunshan University** and **Recovery demo (not a benchmark)**.
Opening the app still lands on a writable project when one exists. Choosing a
read-only corpus stays on that corpus.

These demonstrations are not in `experiments/recovery-benchmark/runs/`.

## Observed runtime

Each case was executed three times through `scripts/run_recovery_demo.py`
(mode loop, top-k 4, max recoveries 2, the environment chat and embedding
models). The script writes `experiments/recovery-benchmark/demo-runs/`, which
is not part of the benchmark. A case is reproducible when all three repeats
took the same action path.

| Case | Repeats | Observed path | Final verification | Hypothesis |
|---|---|---|---|---|
| Weekday opening time | 3/3 | accept | none (accepted) | Met. Answer 09:00 from the hours page. |
| Red cabinet password | 3/3 | rewrite, then expand, then abstain | Still failing | Not met. The plate (4419) was not retrieved. The final answer abstains. |
| Hours card | 3/3 | accept | none (accepted) | Not met. The card was already in the first four passages. Expand did not run. |
| Cabinet plate number | 3/3 | expand | Unchanged | Not met. The first answer was already 4419. Regenerate did not run. |
| Espresso machine model | 3/3 | rewrite, then expand | Still failing | The absence is visible. Both answers abstain. The budget ended on expand, so the abstain action was not recorded. |

## What Test Console showed

Opened on the running app at `http://127.0.0.1:8001`, Auto recovery, top-k 4.
No screenshots are stored.

**Weekday opening time.** First answer: "The weekday opening time at the Northport Workshop is 09:00." Judge: evidence sufficient, answer supported. No recovery section.

**Red cabinet password.** Initial answer abstains. Rewrite query: "What is the password for the red cabinet at the Northport Workshop?" That attempt is still failing. Expand to top-k 12 still does not include the plate, and the answer still abstains. Then abstain. The run header is **Still failing**. The expand step's own attempt check said Improved while the answer was still an abstention. The final verification line does not.

**Espresso machine model.** Initial answer abstains. Rewrite, then expand to top-k 12. The final answer is still "I do not know based on the retrieved documents." The run list says **Still failing · rewrite → expand**. The expand attempt check again said Improved. The runtime verification line says Still failing.

**DKU Library street address** (research corpus, not a demo item; repeated because the designed rewrite and expand demos did not succeed). Three script repeats: rewrite then expand, gold span present, verification Improved. In Test Console the first answer abstains, rewrite stays insufficient, expand answers "No. 8 Duke Avenue", and runtime verification says **Improved**. The new evidence includes `dku-library-hours`.

The designed regenerate demo did not produce a regenerate step, and the designed expand demo did not produce an expand step. Those two questions were not opened again in the browser after the three script repeats. The product owner can run them from the table above. Do not read a demo outcome as a benchmark rate.
