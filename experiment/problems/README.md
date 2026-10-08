# Candidate problems (screening stage)

Candidate problems for the next study. They exist because the bizsla study hit a ceiling: the cheap model alone
passed 29 of 30 runs, so no process could show it helps. Each problem below is meant to be hard enough that the
cheap model (`gemini-3.8-flash`) working alone usually fails.

- **P6–P10** were screened on 2026-10-06 ([results](../runs/screen_20261006T195836Z/SCREENING.md)). semver and
  sheet are keep candidates; orderbook, promo and payroll were too easy.
- **P11–P18** were added and screened on 2026-10-07 ([results](../runs/screen_20261007T191049Z/SCREENING.md)).
  recur is the only keep candidate, and a weak one: of its 4 cheap-model runs, 1 passed, 1 failed and 2 timed out.
  The failure is traced to the spec (the calendar-edge rule). merge3, roster, reconcile and washsale were too easy.
  policy, schema and ignore could not be judged: both strong-model runs on each used all 64 000 output tokens
  without writing code (the cheap model even solved policy and ignore).

> [!WARNING]
> These are **screening artifacts, not frozen test sets.** Each problem has **one checked oracle** (`reference.py`).
> semver and sheet also have a second oracle (`oracle2.py`). An outside run reports that each agrees with its reference
> on every stored case and on 1 500 random inputs; that check is not yet part of the test suite.
> Nothing here has author-signed hand cases or a freeze hash. No study result may be drawn from them until a problem
> passes screening and gets full ground truth (see "After screening").

| # | Folder | Entry point | What makes it hard |
|---|---|---|---|
| P6 | [orderbook](orderbook/SPEC.md) | `run_book(commands)` | Price-time priority, partial fills, cancel/replace that keeps or loses queue position, stop orders that trigger in cascades |
| P7 | [semver](semver/SPEC.md) | `resolve(registry, root)` | Caret, tilde, hyphen and OR ranges with prerelease rules; backtracking search with a fixed tie-break order; unsatisfiable cases |
| P8 | [sheet](sheet/SPEC.md) | `evaluate(cells)` | Formula parser with precedence and ranges; error propagation; cycle detection that marks exactly the cells in a cycle; a 20 000-cell dependency chain |
| P9 | [promo](promo/SPEC.md) | `price_cart(catalog, cart, promotions)` | Stacked promotions with fixed order, per-unit allocation, bundles, caps and exclusive groups; integer-cent rounding with remainder distribution |
| P10 | [payroll](payroll/SPEC.md) | `compute_pay(punches, rate)` | Punch rounding, overlap removal, shifts across midnight, daily and weekly overtime, the seventh-day rule, meal penalties |
| P11 | [policy](policy/SPEC.md) | `authorize(principals, policies, requests)` | Allow/deny statements with `*`/`?` globs and resource variables; condition operators with `IfExists` and any/all-value qualifiers on missing or empty keys; role inheritance with cycles; permission boundaries |
| P12 | [washsale](washsale/SPEC.md) | `compute_gains(trades, identical)` | FIFO lots with exact cent splitting; wash sales that look 30 days ahead and behind across groups of identical symbols; chained basis and holding-period carry-over; the anniversary rule for long-term gains |
| P13 | [roster](roster/SPEC.md) | `make_roster(staff, shifts, rules)` | An exact depth-first search with dynamic candidate order; rest, weekly-cap, consecutive-day, availability, pairing and seniority constraints on overnight shifts; searches 30 000 slots deep |
| P14 | [reconcile](reconcile/SPEC.md) | `reconcile(ledger, bank, params)` | Five matching passes in fixed order: reference tokens, exact amounts, 2–3-way splits in both directions, fees; global tie-break keys; 20 000 records a side |
| P15 | [recur](recur/SPEC.md) | `occurrences(event, range_start, range_end)` | A recurrence-rule subset with BYDAY ordinals, BYSETPOS and WKST; COUNT, UNTIL and excluded dates; missing dates skipped, never clamped; ranges thousands of years after the start |
| P16 | [schema](schema/SPEC.md) | `validate(schema, instance)` | A schema language defined in full: Python type traps (`bool`, `1.0`), JSON equality, exact `multipleOf`, error suppression in combinators, `$ref` resolution and cycle detection; 20 000-deep instances |
| P17 | [ignore](ignore/SPEC.md) | `ignored(files, rules)` | Ignore-file rules: escapes, anchoring, directory-only rules, character classes, `**` forms, nested files with precedence, and the parent-exclusion rule; deep trees and many-`*` patterns |
| P18 | [merge3](merge3/SPEC.md) | `merge(base, ours, theirs)` | A diff defined by an exact greedy shortest-edit procedure and tie rule; diff3 chunking with conflicts on adjacent edits; exact newline handling; 50 000-line files |

## What each folder holds

| File | Purpose | Seen by a model? |
|---|---|---|
| `SPEC.md` | The full task, including the public worked examples | **Yes**: the only text a model sees |
| `reference.py` | Trusted implementation (standard library only) | No |
| `oracle2.py` | semver and sheet only: a second implementation written from `SPEC.md` alone, built a different way, for differential testing against `reference.py` | No |
| `cases.py` | Public, hidden and stress cases. Every public example has a `spec_expected` output worked out by hand from `SPEC.md`, and so do at least 18 hidden cases per problem (25–72 for P11–P18). The build fails if the reference disagrees with any of them. | No |
| `mutants.py` | 14 to 21 plausible misreadings planted into `reference.py` | No |
| `screen_cases.json` | Expected outputs built from `reference.py` (`common.py build`) | No |

## Checks run so far

- `python experiment/problems/common.py self-test <name>`, in the Docker sandbox:
  - the reference passes every case;
  - every planted bug is caught by at least one **scored** (hidden or stress) case.

  P6–P10 pass. For P11–P18, each reference was graded in Docker on 2026-10-07 and passes every case, stress
  included. Their planted bugs were checked in-process by the tests below. Each problem's build agent also reports
  passing the full self-test in the subprocess sandbox (acceptable only for trusted code), which was not re-run in
  Docker.
- [`tests/test_problems.py`](../../tests/test_problems.py) covers all 13 problems:
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
