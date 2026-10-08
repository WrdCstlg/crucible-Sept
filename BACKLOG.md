# Backlog

Open items, newest first within each section. Each one names the evidence that would close it.

## Needs the author

- **Choose how to test the keep candidates, given no further paid runs** (decided 2026-10-07). Options include the
  local models or a mock-only study. **Done when:** the choice is recorded here.

## In progress

- **Problems hard enough to separate the arms.** The bizsla study hit a ceiling: the cheap model alone scored 29/30.
  Thirteen candidates (P6–P18) are built and screened in [`experiment/problems/`](experiment/problems/README.md).
  - **Keep candidates:** semver and sheet (each with a second oracle that agrees with its reference), and recur
    (weak: 2 of its 4 cheap-model runs timed out).
  - **Could not be judged:** policy, schema and ignore. Every strong-model run used all 64 000 output tokens without
    writing code.
  - **Done when:** each keep candidate has a second oracle, 20 signed-off hand cases and a freeze.

## Not started

- **Out-of-sample test of the gate against weak but reference-passing suites.** None occurred in the study, so the
  code, output and input axes were never challenged out of sample.
- **Stronger isolation for hostile code** (gVisor or similar). Docker shares the host kernel.
- **Arm B is tied to bizsla.** `experiment/study/arm_study.py` hard-codes the `compute_sla` entry point, the
  bizsla public cases and bizsla paradigms. Needs a per-problem configuration before a multi-problem study.
