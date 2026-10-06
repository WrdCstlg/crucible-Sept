# Study results

Pre-registration sha256 `428a412cd7ba`, commit `7c9587e2d0`. Problem: `experiment/bizsla` (225 hidden cases, all-or-nothing). Spend cap $100.00; spent $27.3666.

| Arm | Planned | Valid (harness errors) | Strict passes | Rate (95% Wilson) | Mean cases | Cost |
|---|---|---|---|---|---|---|
| A: gemini-3.8-flash, 1 call | 30 | 30 (0) | 29 | 97% (83%-99%) | 222.5 | $4.50 |
| B: gemini-3.8-flash in Crucible | 20 | 20 (0) | 18 | 90% (70%-97%) | 202.5 | $8.69 |
| C: claude-opus-5-5, 1 call | 30 | 30 (0) | 30 | 100% (89%-100%) | 225.0 | $8.36 |

**H1 (primary) B vs C:** no detectable difference (p = 0.155); with these n, gaps under ~100% could not be detected at 80% power
**H2 B vs A:** no detectable difference (p = 0.556); with these n, gaps under ~100% could not be detected at 80% power
**H3 Crucible verdict vs hidden grader:** {'candidates': 38, 'promoted': 36, 'promoted_but_fail_hidden': 2, 'rejected_but_pass_hidden': 0, 'false_promotion_wilson95': [0.015, 0.181]}
**H4 mutation gate out of sample:** {'suites': 18, 'admitted': 11, 'false_security': 0, 'lost_signal': 0, 'agreement': '18/18', 'agreement_wilson95': [0.824, 1.0], 'criterion_met': True}

## Runs

| Run | Status | Cases | Strict | First failure |
|---|---|---|---|---|
| A1 | done | 225/225 | PASS |  |
| A10 | done | 225/225 | PASS |  |
| A11 | done | 149/225 | FAIL | R001: expected {'ticket_id': 't1', 'priority': 'P3', 'used_minutes': 960, 'breached': False, 'breached_at': None, 'statu |
| A12 | done | 225/225 | PASS |  |
| A13 | done | 225/225 | PASS |  |
| A14 | done | 225/225 | PASS |  |
| A15 | done | 225/225 | PASS |  |
| A16 | done | 225/225 | PASS |  |
| A17 | done | 225/225 | PASS |  |
| A18 | done | 225/225 | PASS |  |
| A19 | done | 225/225 | PASS |  |
| A2 | done | 225/225 | PASS |  |
| A20 | done | 225/225 | PASS |  |
| A21 | done | 225/225 | PASS |  |
| A22 | done | 225/225 | PASS |  |
| A23 | done | 225/225 | PASS |  |
| A24 | done | 225/225 | PASS |  |
| A25 | done | 225/225 | PASS |  |
| A26 | done | 225/225 | PASS |  |
| A27 | done | 225/225 | PASS |  |
| A28 | done | 225/225 | PASS |  |
| A29 | done | 225/225 | PASS |  |
| A3 | done | 225/225 | PASS |  |
| A30 | done | 225/225 | PASS |  |
| A4 | done | 225/225 | PASS |  |
| A5 | done | 225/225 | PASS |  |
| A6 | done | 225/225 | PASS |  |
| A7 | done | 225/225 | PASS |  |
| A8 | done | 225/225 | PASS |  |
| A9 | done | 225/225 | PASS |  |
| B1 | done | 225/225 | PASS |  |
| B10 | done | 225/225 | PASS |  |
| B11 | timeout (no meta) | 0/- | FAIL |  |
| B12 | done | 225/225 | PASS |  |
| B13 | done | 225/225 | PASS |  |
| B14 | done | 225/225 | PASS |  |
| B15 | done | 225/225 | PASS |  |
| B16 | done | 225/225 | PASS |  |
| B17 | done | 225/225 | PASS |  |
| B18 | done | 225/225 | PASS |  |
| B19 | done | 225/225 | PASS |  |
| B2 | done | 225/225 | PASS |  |
| B20 | timeout (no meta) | 0/- | FAIL |  |
| B3 | done | 225/225 | PASS |  |
| B4 | done | 225/225 | PASS |  |
| B5 | done | 225/225 | PASS |  |
| B6 | done | 225/225 | PASS |  |
| B7 | done | 225/225 | PASS |  |
| B8 | done | 225/225 | PASS |  |
| B9 | done | 225/225 | PASS |  |
| C1 | done | 225/225 | PASS |  |
| C10 | done | 225/225 | PASS |  |
| C11 | done | 225/225 | PASS |  |
| C12 | done | 225/225 | PASS |  |
| C13 | done | 225/225 | PASS |  |
| C14 | done | 225/225 | PASS |  |
| C15 | done | 225/225 | PASS |  |
| C16 | done | 225/225 | PASS |  |
| C17 | done | 225/225 | PASS |  |
| C18 | done | 225/225 | PASS |  |
| C19 | done | 225/225 | PASS |  |
| C2 | done | 225/225 | PASS |  |
| C20 | done | 225/225 | PASS |  |
| C21 | done | 225/225 | PASS |  |
| C22 | done | 225/225 | PASS |  |
| C23 | done | 225/225 | PASS |  |
| C24 | done | 225/225 | PASS |  |
| C25 | done | 225/225 | PASS |  |
| C26 | done | 225/225 | PASS |  |
| C27 | done | 225/225 | PASS |  |
| C28 | done | 225/225 | PASS |  |
| C29 | done | 225/225 | PASS |  |
| C3 | done | 225/225 | PASS |  |
| C30 | done | 225/225 | PASS |  |
| C4 | done | 225/225 | PASS |  |
| C5 | done | 225/225 | PASS |  |
| C6 | done | 225/225 | PASS |  |
| C7 | done | 225/225 | PASS |  |
| C8 | done | 225/225 | PASS |  |
| C9 | done | 225/225 | PASS |  |
