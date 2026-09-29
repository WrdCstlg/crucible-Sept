# Experiment and evaluation rig

This folder holds everything needed to answer one question with evidence a skeptical reader can check: does a cheaper model, alone or inside the Crucible pipeline, match a stronger model at writing correct code? The story and results are in the [case study](../case-study/CASE_STUDY.md); this page documents how the system works.

## Layout

```
experiment/
├── sla/                        The problem and the frozen test set
│   ├── SPEC.md                 Reviewed spec: the only problem description any model sees
│   ├── SPEC_v0_original.md     Original pre-review spec, used for the ablation
│   ├── hand_cases.json         6 hand-written cases: the ground truth
│   ├── generate_cases.py       Builds the edge, random and stress cases; stops unless both references agree
│   ├── generated_cases.json    33 generated cases
│   ├── reference.py            Reference implementation #1 (state machine over one global sort)
│   ├── reference_intervals.py  Reference implementation #2 (per-ticket intervals, its own parser)
│   ├── FROZEN.json             SHA-256 fingerprints of all of the above
│   └── ABLATION_PREDICTION.md, ABLATION_RESULT.md
├── grade.py                    Hidden grader and mutation self-test
├── run_pilot.py                Runs all arms in parallel under a deadline, then grades everything
├── arms.py                     Arm runner using the Antigravity agent SDK (the first pilots)
├── attribution.py              Ablation attribution check
├── replay.py                   Replays recorded Crucible verdicts with no model calls; --counterfactual applies the deterministic policy
├── verify_all.py               Verifies all recorded evidence without API keys, including the replay (runs in CI)
├── COMPARISON.md               Results and analysis across all pilots
├── rig/                        Provider-agnostic three-role rig
│   ├── roles.json              Which model plays which role, with settings and prices
│   ├── providers.py            Anthropic, Gemini and OpenAI-compatible adapters; no tools declared
│   ├── arm.py                  Arm runner for the rig (same interface as arms.py)
│   ├── audit.py                Code-generated audit record: 10 checks per trial
│   ├── observe.py              Blinded observer reports and the hash-chained ledger
│   └── check_suites.py         Tests the tester: Crucible-written suites vs the trusted reference
└── runs/                       One folder per pilot: raw evidence, never edited
```

## The arms

| Arm | What runs | Role in `rig/roles.json` |
|---|---|---|
| A | One call, the spec in and a module out | `evaluated` |
| B | The same model inside Crucible: 2 approaches, at most 2 rounds, cumulative gate | `evaluated` (every Crucible agent) |
| C | One call | `competitor` |

Arms A and C receive the identical system prompt and spec. No arm ever sees a test case. Only one thing is graded per run: the code from arms A and C, or Crucible's first surviving branch for arm B. If Crucible promotes nothing, arm B fails that run.

Arm B runs Crucible under the **legacy** verdict policy, in which every AI-written suite blocks. That is the design that was measured. Crucible's own default is now the deterministic policy; `replay.py --counterfactual` shows how the recorded runs would have been judged under it.

## The test set and the grader

- **Groups:** 6 hand-written cases, 24 edge cases with answers computed by hand, 6 seeded random mixes, and 3 stress streams (up to 28,150 lines and 5,690 tickets).
- **Guards:** `generate_cases.py` refuses to write anything unless both reference implementations pass the hand cases, match every hand-computed edge answer, and agree on every generated stream.
- **Freeze:** everything is fingerprinted in `FROZEN.json`, and `run_pilot.py` refuses to start if any file changed. Line endings are pinned by `.gitattributes` so the fingerprints survive a clone on any platform.
- **Hidden grader:** `grade.py` runs each case in its own process with a timeout. It checks values and types exactly, and scores all-or-nothing.
- **Self-test:** `grade.py --self-test` requires both references to score 39/39 and all 11 deliberately broken solutions to be caught.

## A pilot, step by step

1. `run_pilot.py` verifies the freeze and records the spec's fingerprint, the roles config and its fingerprint, and the run plan.
2. It runs arms B and C in parallel and arm A one run at a time, under a deadline. Anything still running at the deadline is stopped and recorded.
3. Every arm writes `solution.py`, the raw model output (`response.txt`), `meta.json` (models, tokens, cost, timings, tool calls) and `log.txt`.
4. It grades every solution and every Crucible candidate from every round, then writes `summary.json` and `summary.md`. Harness crashes are listed separately and excluded from pass rates.
5. `rig/audit.py` writes `audit.json` for each trial and `audit_summary.json` with a fingerprint of every audit record.
6. `rig/observe.py` writes a blinded `observer_report.json` and `.md` for each trial, plus `ledger.jsonl` and `observer_key.json` (which trial each "System N" is).
7. `rig/check_suites.py` runs every Crucible-written test suite against the trusted reference, then writes `suite_check.json`. A suite the reference fails contains a wrong expectation.
8. `replay.py` re-executes every recorded Crucible verdict from the saved candidates and suites. It uses the policy and environment the run used, and makes no model calls. With `--counterfactual` it also judges the same recordings under the deterministic policy, in two variants: reference only, and reference plus the 6 hand cases. It writes `replay.json`. `verify_all.py` runs the replay check on every pilot.

## Observer rules (enforced in code)

- **It never scores.** The grader's result is shown to it as final.
- **It works blind.** Trials are "System N", and model names, provider names and local paths are redacted from its evidence.
- **Evidence is data.** It's wrapped in `<evidence>` tags, and the observer is told nothing inside is an instruction.
- **Every finding cites evidence.** Each must cite `E<n>:<check id>` or `E<n>:line <number>`, and `validate()` flags any citation that doesn't resolve.
- **Reports are tamper-evident.** Each report's fingerprint is chained to the previous ledger entry, and `observe.py --verify` recomputes the chain.

## Run history

| Run folder | Runner | Spec | A | B | C | Notes |
|---|---|---|---|---|---|---|
| `pilot_20260929T175519Z` | agent SDK | reviewed | invalid | invalid | 5/5 | Harness bug; see `INVALID.md` |
| `pilot_20260929T180102Z` | agent SDK | reviewed | 5/5 | 2/2 | 5/5 | Flash, default thinking; Opus, effort high |
| `pilot_ablation_v0_20260929T181350Z` | agent SDK | original | 0/5 | 0/2 | 0/5 | Spec ablation |
| `pilot_rig_20260929T190640Z` | rig | reviewed | 5/5 | 1/2 | 5/5 | Flash thinking HIGH; Opus xhigh; Kimi K3 judge; Crucible's own tests rejected 4 correct candidates |

Full analysis: [`COMPARISON.md`](COMPARISON.md).

## Swapping models or adding a problem

- **Models:** edit `rig/roles.json`: `provider`, `model`, `api_key_env`, `settings` (`effort`, `thinking_level` or `thinking_budget`, `max_tokens`) and optionally `price_per_mtok`. For another OpenAI-compatible service, set `base_url_env` or `base_url`.
- **Problems:** write a spec, hand cases and a reference implementation, then adapt `generate_cases.py` and the mutants in `grade.py`. Re-freeze by running `generate_cases.py` before any model sees the spec.
