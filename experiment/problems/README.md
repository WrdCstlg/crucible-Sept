# Candidate problems (screening stage)

Five new problems for the next study. They exist because the bizsla study hit a ceiling: the cheap model alone
passed 29 of 30 runs, so no process could show it helps. Each problem below is meant to be hard enough that the
cheap model (`gemini-3.8-flash`) working alone usually fails.

> [!WARNING]
> These are **screening artifacts, not frozen test sets.** Each problem has **one oracle** (`reference.py`). Nothing
> here has a second independent implementation, author-signed hand cases or a freeze hash. No study result may be
> drawn from them until a problem passes screening and gets full ground truth (see "After screening").

| # | Folder | Entry point | What makes it hard |
|---|---|---|---|
| P6 | [orderbook](orderbook/SPEC.md) | `run_book(commands)` | Price-time priority, partial fills, cancel/replace that keeps or loses queue position, stop orders that trigger in cascades |
| P7 | [semver](semver/SPEC.md) | `resolve(registry, root)` | Caret, tilde, hyphen and OR ranges with prerelease rules; backtracking search with a fixed tie-break order; unsatisfiable cases |
| P8 | [sheet](sheet/SPEC.md) | `evaluate(cells)` | Formula parser with precedence and ranges; error propagation; cycle detection that marks exactly the cells in a cycle; a 20 000-cell dependency chain |
| P9 | [promo](promo/SPEC.md) | `price_cart(catalog, cart, promotions)` | Stacked promotions with fixed order, per-unit allocation, bundles, caps and exclusive groups; integer-cent rounding with remainder distribution |
| P10 | [payroll](payroll/SPEC.md) | `compute_pay(punches, rate)` | Punch rounding, overlap removal, shifts across midnight, daily and weekly overtime, the seventh-day rule, meal penalties |

## What each folder holds

| File | Purpose | Seen by a model? |
|---|---|---|
| `SPEC.md` | The full task, including the public worked examples | **Yes**: the only text a model sees |
| `reference.py` | Trusted implementation (standard library only) | No |
| `cases.py` | Public, hidden and stress cases. Every public example and 162 hidden cases in total have a `spec_expected` output worked out by hand from `SPEC.md`. The build fails if the reference disagrees with any of them. | No |
| `mutants.py` | 14 to 21 plausible misreadings planted into `reference.py` | No |
| `screen_cases.json` | Expected outputs built from `reference.py` (`common.py build`) | No |

## Checks run so far

- `python experiment/problems/common.py self-test <name>`, in the Docker sandbox:
  - the reference passes every case;
  - every planted bug is caught by at least one **scored** (hidden or stress) case.

  All 5 problems pass.
- [`tests/test_problems.py`](../../tests/test_problems.py) covers:
  - the hand-derived outputs;
  - stored cases equal a fresh, deterministic build;
  - strict comparison (`1` vs `1.0`, `True` vs `1`, tuples, NaN);
  - each planted bug applies exactly once and is caught by a scored case;
  - the spec names the entry point and leaks nothing from the grader;
  - standard-library-only code;
  - the screening harness's refusals;
  - (slow) a mock screening run end to end, checked against byte-identity ground truth.

## Screening

[`screen.py`](screen.py) runs a few single calls per problem through the same `experiment/study/arm_study.py` the
study used:
- A is the cheap model, one call;
- C is the strong model, one call;
- there is no Crucible arm, because screening measures difficulty only.

It has the same fail-closed spend cap as the study and refuses to start if any `screen_cases.json` is stale.

**Keep rule, fixed in code before any live run:**
- the cheap model passes at most 25% of its valid runs, **and**
- the strong model passes at least once.

A problem flagged by the rule is only a candidate. Every failing run must be read by hand and traced to the spec, not
to a bug in `reference.py` or in the cases, before the problem is kept.

### Known biases of screening (disclosed in advance)

- **Regression to the mean.** Choosing problems because the cheap model failed them selects for problems where it
  had bad luck. On a re-run it will tend to do better. This works *against* finding that Crucible helps, so it does
  not inflate a positive result.
- **Claude-drafted ground truth.** The specs, references and hand expectations were written with Claude, which may
  favour arm C (also a Claude model).
- **One oracle.** A reference bug would mark correct solutions as failures. The hand review of every failure is the
  only guard at this stage.
- **Small samples.** Screening uses about 4 A + 2 C runs per problem. It only sorts problems; it estimates no effect.

## After screening (only for kept problems)

1. A second, independently written oracle that agrees with the reference on every case.
2. 20 hand cases with written justifications, signed off by the author.
3. A freeze (`FROZEN.json`-style hash) before any study run.
4. Arm B generalised beyond bizsla: per-problem entry point, public cases and paradigms.
5. A new pre-registration for the multi-problem study, committed before any run.
