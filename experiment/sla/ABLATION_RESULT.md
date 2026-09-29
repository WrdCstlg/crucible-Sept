# Spec ablation: result

Compared with the prediction in `ABLATION_PREDICTION.md`, written before the run.

| Arm | Reviewed spec (`SPEC.md`) | Original spec (`SPEC_v0_original.md`) |
|---|---|---|
| A: Gemini Flash, 1 call | 5/5 runs passed all 39 cases (38 s, ~29k tokens per run) | 0/5 (mean 27.6/39; 115 s, ~62k tokens per run) |
| B: Gemini Flash in Crucible | 2/2 (39/39) | 0/2 (mean 27.5/39; 283 s) |
| C: Claude Opus 5.5, 1 call | 5/5 (39/39; 11 s, $0.03 per run) | 0/5 (mean 29.0/39; 19 s, $0.04 per run) |

Runs: `runs/pilot_20260929T180102Z` (reviewed spec) and `runs/pilot_ablation_v0_20260929T181350Z`
(original spec). Same models, settings, harness and frozen test set; only the spec text differs.

## Prediction scorecard
- Hand cases H1-H6 still pass: correct (never failed in any run).
- OPEN reset (E07, E22) fails: correct (failed in all 12 runs).
- Closed-ticket RESUME/PAUSE (E05, E06) fails: wrong. Never failed; every model read the intent
  (a closed ticket ignores them) rather than the literal loophole in the original wording.
- Malformed lines and "now" (E15, E16) fail: correct for Gemini (E16 failed in 7/7 Gemini runs,
  E15 in 3/7); wrong for Claude (0/5).
- Random and stress layers fail: correct (all but R4 failed in every run).

## Attribution (`python experiment/attribution.py runs/pilot_ablation_v0_20260929T181350Z`)
- One decision absent from the original spec, OPEN on a closed ticket, changes the correct answer
  for 10 of 39 cases. It caused failures in every run of every arm.
- For 3 of 5 Claude runs it explains every failure (39/39 on the alternative answer key).
- For every Gemini run, failures remain after removing it: the unstated well-formed-line rules
  (E16 always, E15 sometimes) and related stress cases. The stronger model inferred those rules;
  the cheaper model needed them written down.

## Crucible's own verification (H3)
Crucible's LLM-written tests, generated from the original spec, passed all 4 candidates that the
hidden grader failed (4 false passes). A verifier can only check what the spec says: gaps in the
spec pass straight through automated verification.

## Caveats
One problem, small numbers (12 runs per condition). The hidden tests encode decisions made during
spec review, so this measures the value of the review, not model capability. Flash token counts
include roughly 11k tokens per call of SDK harness instructions.
