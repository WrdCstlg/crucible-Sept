# Pre-registration: does a cheaper model inside Crucible beat a stronger model working alone?

This file fixes the hypotheses, sample sizes, exclusion rules and analysis **before any live study run**.
`experiment/study/run_study.py` refuses a live run unless this file is committed with no local edits. Every
result file records this file's sha256 and commit. Anything in the results that is not listed here must be labelled
exploratory.

## 1. Why this exists

The pilots (`experiment/runs/`, Problems 1–4) had at most 5 runs per arm, on a problem both models mostly solved.
A "5 of 5" from that setup shows the result can be reproduced, but it says nothing about rates. After the pilots,
`rig/roles.json` pinned the evaluated model to temperature 0 and seed 0. That would make repeated runs
near-copies, so this study unpins it (§3). This study replaces the pilots with a harder problem, independent
samples, a sample size chosen from a power calculation, and fixed statistical tests.

## 2. Problem (frozen)

`experiment/bizsla/`: business-hours SLA tracking. It covers priorities P1–P4, holidays, priority changes,
pause/resume/close/reopen, an exact breach-minute rule and a performance requirement.

| Artifact | Role |
|---|---|
| `SPEC.md` | The only problem text any arm sees |
| `public_cases.json` | The 4 worked examples printed in SPEC.md (graded but not scored) |
| `hand_cases.json` | 20 cases whose expected outputs were derived **by hand**, each with a written justification |
| `generated_cases.json` | 201 cases: edge 35, random 80, holiday 40, churn 40, medium 6 |
| `stress_cases.json` | 4 large inputs (SplitMix PRNG); only the expected output's sha256 is stored |
| `reference.py` / `brute_force.py` | Two independent oracles: closed-form, and minute-by-minute simulation |
| `grade.py` | Hidden grader with 22 planted bugs (B01–B22) |

Freeze: `FROZEN.json` sha256 `39c19fed1490ee3007ef63e543c16d0f24c9ec8827bae94188589d34db2528b0`
(hashes of SPEC, the case files, both oracles and the generator). Grader `grade.py` sha256
`e9a5db597dfc40c0939b22e4a1f5716d45d3d987b150bc94dc926144782a41b5`.
`run_study.py` refuses to start if the freeze check fails.

**Why we trust the test set:**

- Expected outputs come from two independently written oracles that must agree on every non-stress case.
- 20 of the cases were checked by hand against the spec, not by either oracle.
- `tests/test_bizsla_oracles.py` adds a 2,500-stream differential fuzz plus calendar and metamorphic properties.
- Every planted bug except the performance bug B21 is killed by at least 2 hidden cases, and B21 is killed by stress.

No model under test has seen any of this test data. Who wrote it is disclosed in §9.

**Scoring:** a run passes only if all 225 scored hidden cases pass (20 hand + 201 generated + 4 stress): exact values
and types, and the stress compute time within 10 s.

## 3. Arms

Model names and settings are fixed in `experiment/study/roles_study.json`.

| Arm | What runs | Model calls (hard ceiling) |
|---|---|---|
| A | Evaluated role (`gemini-3.8-flash`, thinking HIGH), one call | 1 |
| B | Evaluated role inside Crucible: 2 generators, an advisory QA suite, deterministic verdict policy, up to 2 rounds | 10 |
| C | Competitor role (`claude-opus-5-5`, effort xhigh), one call | 1 |

**Information parity:**

- Every arm receives exactly SPEC.md.
- Arm B's only ground truth is the 4 worked examples already printed in SPEC.md, used as acceptance cases.
- Arm B gets no reference solution, so its AI-written suites are advisory and can never decide its verdict.
- No arm ever sees the hidden grader.

**Sampling:** temperature and seed are **not** fixed, so runs are independent samples (unlike the later
`rig/roles.json` setting; see §1).

**Price:** prices in the roles file only control the spend cap. They do not affect any outcome, so filling in a
missing price after this file is committed is not a deviation. The run records the roles file's sha256.

## 4. Sample size and power

The sample sizes are fixed before any run: **A = 30, B = 20, C = 30**. B is smaller because each B run makes up
to 10 calls.

Power figures come from the exact Fisher test, two-sided, α = 0.05, computed by `experiment/stats.py`:

- **Minimum detectable B–C gap at 80% power:** about 37–41 percentage points for a C rate between 0.1 and 0.5,
  and 34 points at 0.6.
- **Power for specific scenarios:**
  - B 0.8 vs C 0.4: power 0.81.
  - B 0.7 vs C 0.4: power 0.53.
  - B 0.6 vs C 0.4: power 0.26.

**Consequence:** this study can detect a large effect. A null result does **not** show the arms are equivalent.
It only shows that any gap is probably smaller than about 40 points, and the report must say so in those words.

## 5. Hypotheses and tests

Each hypothesis has a fixed test and decision rule:

- **H1 (primary): B vs C strict-pass rate.**
  - Test: two-sided Fisher exact test, α = 0.05.
  - If p < 0.05, report the direction.
  - If p ≥ 0.05, report "no detectable difference" together with the minimum detectable gap.
  - Report each arm's rate with its 95% Wilson interval.
- **H2 (secondary): B vs A.** Same test. This isolates the effect of the process itself, since both arms use the
  same model.
- **H3 (descriptive): Crucible's own verdict vs the hidden grader**, for every arm-B candidate.
  - Report "promoted but fails hidden" (false promotion, with its Wilson interval).
  - Report "rejected but passes hidden".
- **H4 (gate, out of sample): the mutation gate on every arm-B AI-written suite.**
  - Gate settings: code, output and input axes; threshold **0.60**, unchanged from in-sample calibration.
  - The gate is judged against an independent yardstick: the suite's kill rate on the 21 planted bugs (B21 excluded).
  - A suite counts as "independently strong" if it passes the reference and kills ≥ 60% of the planted bugs.
  - **Criterion:** 0 admitted-but-weak suites (false security) **and** ≥ 80% agreement.
  - If the criterion fails, the gate's calibration is reported as not generalising.

There are no other confirmatory tests. Secondary metrics (mean cases passed, cost, latency) are descriptive only.

## 6. Exclusions (as coded in `run_study.is_harness_error`)

- **Excluded, and reported per arm:** a crash of the harness itself (an exception in our code or the provider
  client, or a missing meta.json).
- **Counted as failures:** model refusals, truncated output, unparseable code, the 45-minute run timeout, and a
  BudgetGuard stop (a call or prompt beyond the run's ceiling).
- **Integrity rule:** if harness errors exceed 10% of an arm's planned runs, the results are labelled
  **COMPROMISED** and H1/H2 must not be relied on.

## 7. Spend cap and stopping

- A hard dollar cap is given on the command line, and the user confirms it before any live run.
- Each run reserves its worst-case cost before it starts. A run that reports no cost is charged its worst case.
- Runs are interleaved A, C, B, so if the cap is hit every arm is cut back by about the same amount.
- Runs that never start are recorded as "not run (spend cap)". They are excluded from rates and listed in the
  results.
- **No peeking:** there is no interim analysis and no early stopping on results. Analysis runs once, after all
  launched runs finish.

## 8. Publication

Whatever the outcome, the results are committed to `experiment/runs/study_*` and linked from the README. That
includes a null result, a B < C result, a compromised study, and an H4 failure. Recorded evidence is never edited
after the fact. Any deviation from this file is listed in the results under "Deviations".

## 9. Known limits (stated in advance)

- **One problem.** The results apply to this problem and these two models only.
- **Calibration is in-sample.** The gate's thresholds were calibrated in-sample on 11 suites from the pilots;
  H4 is their first out-of-sample test.
- **Who wrote the ground truth.** The spec, both oracles, the hand cases and the planted bugs were drafted by an AI coding assistant (Claude, via Antigravity) under the author's direction. No model under test has seen them. The competitor arm is also a Claude model, so a misreading the two share would favour **arm C**: this biases *against* the hypothesis that B beats C, not toward it. Mitigations: two algorithmically independent oracles, and 20 hand-derived cases with written justifications, which the author reviews before the live run. Any case corrected after that review requires a re-freeze, recorded under "Deviations", before any live run.
- **The sandbox runs the code, not the AST lint.** Model-written code runs inside the Docker sandbox. The AST lint
  is a code-quality filter, not a security boundary.
