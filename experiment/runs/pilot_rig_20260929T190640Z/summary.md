# SLA pilot results

Spec given to all arms: `SPEC.md`. Test set frozen at 2026-09-29T17:52:07.651315+00:00; 39 hidden cases, all-or-nothing scoring.

| Arm | Valid runs (harness errors) | Strict passes | Mean cases passed | Mean time (s) | Tokens | Claude cost |
|---|---|---|---|---|---|---|
| A: gemini-3.8-flash, 1 call | 5 (0) | 5 | 39.0 | 99.0 | 137070 | - |
| B: gemini-3.8-flash in Crucible | 2 (0) | 1 | 19.5 | 429.8 | 244744 | - |
| C: claude-opus-5-5, 1 call | 5 (0) | 5 | 39.0 | 18.8 | 17947 | $0.24 |

H1 gap closed (B-A)/(C-A): undefined (an arm has no valid runs, or A and C tie)

H3 Crucible verdict vs hidden grader (all arm-B candidates): {'crucible_pass_hidden_pass': 2, 'false_pass': 0, 'false_fail': 4, 'crucible_fail_hidden_fail': 0}

## Runs

| Run | Status | Cases | Strict | First failure |
|---|---|---|---|---|
| A1 | done | 39/39 | PASS |  |
| A2 | done | 39/39 | PASS |  |
| A3 | done | 39/39 | PASS |  |
| A4 | done | 39/39 | PASS |  |
| A5 | done | 39/39 | PASS |  |
| B1 | done | 39/39 | PASS |  |
| B2 | done | 0/- | FAIL |  |
| C1 | done | 39/39 | PASS |  |
| C2 | done | 39/39 | PASS |  |
| C3 | done | 39/39 | PASS |  |
| C4 | done | 39/39 | PASS |  |
| C5 | done | 39/39 | PASS |  |
