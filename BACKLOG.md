# Backlog

Open items, newest first within each section. Each one names the evidence that would close it.

## Needs the author

- *(Optional)* **Case-by-case check of the 20 bizsla hand cases.** The author approved them on 2026-10-06 without
  a case-by-case check ([HAND_CASE_SIGNOFF.md](experiment/bizsla/HAND_CASE_SIGNOFF.md)). Deviation 3 stands either
  way, because §9 asked for the review before the run.
  **Worth doing because:** both oracles and the cases were drafted by Claude, so their agreement cannot rule out a
  shared misreading of `SPEC.md`. **Done when:** each case's expected output has been checked against `SPEC.md` and
  its justification, and the outcome is added to the sign-off note.

## In progress

- **Problems hard enough to separate the arms.** The bizsla study hit a ceiling: the cheap model alone scored 29/30.
  Five candidate problems (P6–P10) are built in [`experiment/problems/`](experiment/problems/README.md).
  - **Built and checked:** for each problem, a spec, reference, hand-derived expectations, planted bugs and a
    screening case set. The Docker self-test passes for all 5.
  - **Approved 2026-10-06:** a live screening run (`experiment/problems/screen.py`) capped at $20. The worst case
    for all 30 runs is $19.42.
  - **Done when:** each problem is kept or dropped under the keep rule fixed in `screen.py`, with every failing run
    traced to the spec by hand. Kept problems then get a second oracle, 20 signed-off hand cases and a freeze.

## Not started

- **Out-of-sample test of the gate against weak but reference-passing suites.** None occurred in the study, so the
  code, output and input axes were never challenged out of sample.
- **Stronger isolation for hostile code** (gVisor or similar). Docker shares the host kernel.
- **Arm B is tied to bizsla.** `experiment/study/arm_study.py` hard-codes the `compute_sla` entry point, the
  bizsla public cases and bizsla paradigms. Needs a per-problem configuration before a multi-problem study.
