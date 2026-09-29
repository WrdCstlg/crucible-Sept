# SLA pilot results

Spec given to all arms: `SPEC_v0_original.md`. Test set frozen at 2026-09-29T17:52:07.651315+00:00; 39 hidden cases, all-or-nothing scoring.

| Arm | Valid runs (harness errors) | Strict passes | Mean cases passed | Mean time (s) | Tokens | Claude cost |
|---|---|---|---|---|---|---|
| A: Gemini Flash, 1 call | 5 (0) | 0 | 27.6 | 115.4 | 310776 | - |
| B: Gemini Flash in Crucible | 2 (0) | 0 | 27.5 | 282.8 | 305558 | - |
| C: Claude Opus 5.5, 1 call | 5 (0) | 0 | 29.0 | 18.9 | 14716 | $0.22 |

H1 gap closed (B-A)/(C-A): undefined (an arm has no valid runs, or A and C tie)

H3 Crucible verdict vs hidden grader (all arm-B candidates): {'crucible_pass_hidden_pass': 0, 'false_pass': 4, 'false_fail': 0, 'crucible_fail_hidden_fail': 0}

## Runs

| Run | Status | Cases | Strict | First failure |
|---|---|---|---|---|
| A1 | done | 28/39 | FAIL | E07: expected {'ticket_id': 'T1', 'used_ms': 500, 'breached': False, 'status': 'closed'}, got {'ticket_id': 'T1', 'used_ms': 20000000, 'breached': True, 'status': 'closed'} |
| A2 | done | 27/39 | FAIL | E07: expected {'ticket_id': 'T1', 'used_ms': 500, 'breached': False, 'status': 'closed'}, got {'ticket_id': 'T1', 'used_ms': 20000000, 'breached': True, 'status': 'closed'} |
| A3 | done | 27/39 | FAIL | E07: expected {'ticket_id': 'T1', 'used_ms': 500, 'breached': False, 'status': 'closed'}, got {'ticket_id': 'T1', 'used_ms': 20000000, 'breached': True, 'status': 'closed'} |
| A4 | done | 28/39 | FAIL | E07: expected {'ticket_id': 'T1', 'used_ms': 500, 'breached': False, 'status': 'closed'}, got {'ticket_id': 'T1', 'used_ms': 20000000, 'breached': True, 'status': 'closed'} |
| A5 | done | 28/39 | FAIL | E07: expected {'ticket_id': 'T1', 'used_ms': 500, 'breached': False, 'status': 'closed'}, got {'ticket_id': 'T1', 'used_ms': 20000000, 'breached': True, 'status': 'closed'} |
| B1 | done | 28/39 | FAIL | E07: expected {'ticket_id': 'T1', 'used_ms': 500, 'breached': False, 'status': 'closed'}, got {'ticket_id': 'T1', 'used_ms': 20000000, 'breached': True, 'status': 'closed'} |
| B2 | done | 27/39 | FAIL | E07: expected {'ticket_id': 'T1', 'used_ms': 500, 'breached': False, 'status': 'closed'}, got {'ticket_id': 'T1', 'used_ms': 20000000, 'breached': True, 'status': 'closed'} |
| C1 | done | 29/39 | FAIL | E07: expected {'ticket_id': 'T1', 'used_ms': 500, 'breached': False, 'status': 'closed'}, got {'ticket_id': 'T1', 'used_ms': 20000000, 'breached': True, 'status': 'closed'} |
| C2 | done | 29/39 | FAIL | E07: expected {'ticket_id': 'T1', 'used_ms': 500, 'breached': False, 'status': 'closed'}, got {'ticket_id': 'T1', 'used_ms': 20000000, 'breached': True, 'status': 'closed'} |
| C3 | done | 29/39 | FAIL | E07: expected {'ticket_id': 'T1', 'used_ms': 500, 'breached': False, 'status': 'closed'}, got {'ticket_id': 'T1', 'used_ms': 20000000, 'breached': True, 'status': 'closed'} |
| C4 | done | 29/39 | FAIL | E07: expected {'ticket_id': 'T1', 'used_ms': 500, 'breached': False, 'status': 'closed'}, got {'ticket_id': 'T1', 'used_ms': 20000000, 'breached': True, 'status': 'closed'} |
| C5 | done | 29/39 | FAIL | E07: expected {'ticket_id': 'T1', 'used_ms': 500, 'breached': False, 'status': 'closed'}, got {'ticket_id': 'T1', 'used_ms': 20000000, 'breached': True, 'status': 'closed'} |
