# Comparison across pilots

Every number below comes from `summary.json`, `audit.json`, `observer_report.json` and `suite_check.json` in the run folders named. All pilots used the same frozen 39-case test set (frozen 2026-09-29T17:52:07Z).

## Conditions

| Pilot | Runner | Spec | Evaluated (A, B) | Competitor (C) | Judge |
|---|---|---|---|---|---|
| `pilot_20260929T180102Z` | Antigravity agent SDK, tools denied by policy | reviewed | Gemini 3.8 Flash, default thinking | Claude Opus 5.5, effort high | none |
| `pilot_ablation_v0_20260929T181350Z` | same | original | same | same | none |
| `pilot_rig_20260929T190640Z` | provider-agnostic rig, plain API calls, no tools | reviewed | Gemini 3.8 Flash, thinking HIGH | Claude Opus 5.5, effort xhigh | Kimi K3, blinded |

## Results

| Pilot | A: evaluated, 1 call | B: evaluated in Crucible | C: competitor, 1 call |
|---|---|---|---|
| Agent SDK, reviewed spec | **5/5** · 38 s · ~29k tokens* | **2/2** · 181 s · ~103k tokens | **5/5** · 11 s · ~2.7k tokens · $0.031 |
| Agent SDK, original spec | 0/5 (27.6/39) · 115 s · ~62k* | 0/2 (27.5/39) · 283 s · ~153k | 0/5 (29.0/39) · 19 s · ~2.9k · $0.045 |
| Rig, reviewed spec | **5/5** · 99 s · ~27k tokens | **1/2** · 430 s · ~122k tokens | **5/5** · 19 s · ~3.6k tokens · $0.049 |

Per-run averages. \*Agent-SDK token counts include about 11k tokens per call of built-in SDK instructions; the rig sends only the prompt. Gemini and Kimi cost wasn't measured in dollars.

## Crucible's own verdicts vs. the hidden grader

| Pilot | Candidates | Agree | False pass | False fail | Crucible-written suites that fail the trusted reference |
|---|---|---|---|---|---|
| Agent SDK, reviewed spec | 4 | 4 | 0 | 0 | 0 of 2 |
| Agent SDK, original spec | 4 | 0 | 4 | 0 | 2 of 2 (built from the vague spec, so this may reflect the spec, not a test bug) |
| Rig, reviewed spec | 6 | 2 | 0 | **4** | **2 of 3** |

In the rig pilot's B2, Crucible's test writer produced a wrong test in *both* rounds, independently:
- **Round 1** treated `444444444,-10,OPEN` as malformed. It's well-formed: ticket `-10`, an all-digit timestamp and a valid event.
- **Round 2** expected a ticket to still be open after `"500,A,CLOSE "`, a valid CLOSE once trimmed. The suite's own comment on that line says *"wait, trimmed event is CLOSE, so that WOULD be valid"*.

The cumulative gate carried the round-1 error forward, and all 4 candidates were rejected, although all 4 pass every hidden test. Crucible promoted nothing, so B2 scores as a failure.

`experiment/rig/check_suites.py` runs every Crucible-written suite against the trusted reference implementation. It flags both broken suites; had it been part of the pipeline, it would have caught this before any candidate was judged.

## What the judge (Kimi K3) added

12 blinded reports, 76 findings (6 concerns, 0 violations), 0 tool calls, about 33k input and 41k output tokens.

| Finding | Assessment |
|---|---|
| B2: Crucible failed all 4 candidates that the hidden grader passed; the error runs one way, pointing to "systematic miscalibration" of an AI-generated harness | ✅ Correct. It restated a failing audit check and added a sound explanation |
| B2: the candidates' output was "the identical erroneous value (… phantom ticket `-10`)" | ❌ Wrong. That output is correct; the judge adopted the faulty test's framing, contradicting its own finding above |
| B1: Crucible's AI synthesis memo "rejected" branch 1 as inferior and declared branch 2 the "sole survivor", but both passed, both were promoted, and branch 1 was graded | ✅ Correct and new. No code check compares the synthesis narrative with the pipeline's actual decision |
| B2: the grader summary says "nothing to grade" while the audit lists hidden-grader results for all 4 candidates | ✅ A fair wording issue in the evidence. Each describes something different (the promoted solution vs. every candidate), but the labels don't say so |
| A5: model identity is redacted, so a reviewer can't verify which model ran | Low value: blinding is by design |
| C3: facts show `crucible_status: null` for a single-call trial | Low value: not applicable to that arm |
| 9 citation problems flagged by code | All formatting (`E1:facts`, or a bare `E2`); none cite evidence that doesn't exist |

## Conclusions

1. **On a precisely specified task, the model under evaluation matched the stronger competitor:** 10 of 10 runs each, across both runners. Raising Gemini's thinking to HIGH didn't change correctness; it made each run about 2.6× slower.
2. **Crucible didn't help, and in the rig pilot it hurt:** 3 of 4 runs passed across both reviewed-spec pilots, against 10 of 10 for the same model alone. Its failure mode is always the same: an AI-written test with a wrong expectation. That has now decided three separate Crucible runs: two earlier live runs ("expected 10", "expected 49") and rig B2.
3. **The cheapest fix is deterministic:** check every AI-written test suite against a trusted reference (or the hand-written cases) before it can judge anything.
4. **The judge is worth having as a second pair of eyes, not as an authority.** It surfaced one real issue no code check covered, and restated the key failure correctly. It also got one attribution wrong, which is exactly why its findings must cite evidence and never decide scores.
5. **H1 (how much of the gap Crucible closes) is still unmeasurable:** there's no gap on this task. Measuring it needs a harder problem where the evaluated model alone sometimes fails.

## Improvements identified by this run (not applied, to keep recorded evidence unambiguous)

- Add the reference check for Crucible-written suites to the pipeline itself, as a gate before admitting a suite.
- In the observer's evidence, label "no promoted solution" separately from per-candidate grades, and omit fields that don't apply to an arm.
- Accept section citations such as `E1:facts` and whole-item citations such as `E2`.
- Tell Crucible's synthesis agent it may explain but not accept or reject candidates, or add a code check that its narrative matches the promotion decision.
