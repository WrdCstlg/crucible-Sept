# SLA pilot results

Test set frozen at 2026-09-29T17:52:07.651315+00:00; 39 hidden cases, all-or-nothing scoring.

| Arm | Valid runs (harness errors) | Strict passes | Mean cases passed | Mean time (s) | Tokens | Claude cost |
|---|---|---|---|---|---|---|
| A: Gemini Flash, 1 call | 5 (0) | 5 | 39.0 | 38.1 | 146740 | - |
| B: Gemini Flash in Crucible | 2 (0) | 2 | 39.0 | 180.6 | 205961 | - |
| C: Claude Opus 5.5, 1 call | 5 (0) | 5 | 39.0 | 11.3 | 13441 | $0.15 |

H1 gap closed (B-A)/(C-A): undefined (an arm has no valid runs, or A and C tie)

H3 Crucible verdict vs hidden grader (all arm-B candidates): {'crucible_pass_hidden_pass': 4, 'false_pass': 0, 'false_fail': 0, 'crucible_fail_hidden_fail': 0}

## Runs

| Run | Status | Cases | Strict | First failure |
|---|---|---|---|---|
| A1 | done | 39/39 | PASS |  |
| A2 | done | 39/39 | PASS |  |
| A3 | done | 39/39 | PASS |  |
| A4 | done | 39/39 | PASS |  |
| A5 | done | 39/39 | PASS |  |
| B1 | done | 39/39 | PASS |  |
| B2 | done | 39/39 | PASS |  |
| C1 | done | 39/39 | PASS |  |
| C2 | done | 39/39 | PASS |  |
| C3 | done | 39/39 | PASS |  |
| C4 | done | 39/39 | PASS |  |
| C5 | done | 39/39 | PASS |  |
