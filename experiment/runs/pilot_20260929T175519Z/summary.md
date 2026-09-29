# SLA pilot results

Test set frozen at 2026-09-29T17:52:07.651315+00:00; 39 hidden cases, all-or-nothing scoring.

| Arm | Runs | Strict passes | Mean cases passed | Mean time (s) | Tokens | Claude cost |
|---|---|---|---|---|---|---|
| A: Gemini Flash, 1 call | 5 | 0 | 0.0 | 0.0 | - | - |
| B: Gemini Flash in Crucible | 2 | 0 | 0.0 | 0.0 | - | - |
| C: Claude Opus 5.5, 1 call | 5 | 5 | 39.0 | 11.0 | 13263 | $0.15 |

H1 gap closed (B-A)/(C-A): 0.0

H3 Crucible verdict vs hidden grader (all arm-B candidates): {'crucible_pass_hidden_pass': 0, 'false_pass': 0, 'false_fail': 0, 'crucible_fail_hidden_fail': 0}

## Runs

| Run | Status | Cases | Strict | First failure |
|---|---|---|---|---|
| A1 | error (TypeError: 'UsageMetadata' object is not callable) | 0/- | FAIL |  |
| A2 | error (TypeError: 'UsageMetadata' object is not callable) | 0/- | FAIL |  |
| A3 | error (TypeError: 'UsageMetadata' object is not callable) | 0/- | FAIL |  |
| A4 | error (TypeError: 'UsageMetadata' object is not callable) | 0/- | FAIL |  |
| A5 | error (TypeError: 'UsageMetadata' object is not callable) | 0/- | FAIL |  |
| B1 | error (TypeError: 'UsageMetadata' object is not callable) | 0/- | FAIL |  |
| B2 | error (TypeError: 'UsageMetadata' object is not callable) | 0/- | FAIL |  |
| C1 | done | 39/39 | PASS |  |
| C2 | done | 39/39 | PASS |  |
| C3 | done | 39/39 | PASS |  |
| C4 | done | 39/39 | PASS |  |
| C5 | done | 39/39 | PASS |  |
