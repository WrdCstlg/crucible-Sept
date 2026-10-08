# Problem screening

Spend cap $20.00; spent $8.3832. Single oracle per problem (reference.py); a failure counts only after it is traced to the spec by hand.

Keep rule (fixed before running): A strict-pass rate <= 25% and C strict passes >= 1.

| Problem | A passes (valid) | A mean cases | C passes (valid) | C mean cases | Cost | Keep candidate |
|---|---|---|---|---|---|---|
| orderbook | 3/4 | 0.75 | 2/2 | 1.0 | $1.76 | no: cheap model passed 3/4 (> 25%) |
| semver | 0/4 | 0.48 | 2/2 | 1.0 | $1.06 | yes: cheap model usually fails and the strong model can solve it |
| sheet | 0/4 | 0.492 | 1/2 | 0.5 | $2.79 | yes: cheap model usually fails and the strong model can solve it |
| promo | 4/4 | 1.0 | 2/2 | 1.0 | $0.66 | no: cheap model passed 4/4 (> 25%) |
| payroll | 4/4 | 1.0 | 2/2 | 1.0 | $0.65 | no: cheap model passed 4/4 (> 25%) |

## Runs

| Problem | Run | Status | Cases | Strict | First failure |
|---|---|---|---|---|---|
| orderbook | A1 | done | 120/120 | PASS |  |
| orderbook | A2 | done | 120/120 | PASS |  |
| orderbook | A3 | timeout (no meta) | 0/- | FAIL |  |
| orderbook | A4 | done | 120/120 | PASS |  |
| orderbook | C1 | done | 120/120 | PASS |  |
| orderbook | C2 | done | 120/120 | PASS |  |
| payroll | A1 | done | 118/118 | PASS |  |
| payroll | A2 | done | 118/118 | PASS |  |
| payroll | A3 | done | 118/118 | PASS |  |
| payroll | A4 | done | 118/118 | PASS |  |
| payroll | C1 | done | 118/118 | PASS |  |
| payroll | C2 | done | 118/118 | PASS |  |
| promo | A1 | done | 123/123 | PASS |  |
| promo | A2 | done | 123/123 | PASS |  |
| promo | A3 | done | 123/123 | PASS |  |
| promo | A4 | done | 123/123 | PASS |  |
| promo | C1 | done | 123/123 | PASS |  |
| promo | C2 | done | 123/123 | PASS |  |
| semver | A1 | done | 166/173 | FAIL | RP03: result.ok: expected true, got false |
| semver | A2 | done | 166/173 | FAIL | RP03: result.ok: expected true, got false |
| semver | A3 | timeout (no meta) | 0/- | FAIL |  |
| semver | A4 | timeout (no meta) | 0/- | FAIL |  |
| semver | C1 | done | 173/173 | PASS |  |
| semver | C2 | done | 173/173 | PASS |  |
| sheet | A1 | timeout (no meta) | 0/- | FAIL |  |
| sheet | A2 | done | 125/127 | FAIL | H11: result.A6: expected dict {"error": "#VALUE!"}, got int 0 |
| sheet | A3 | timeout (no meta) | 0/- | FAIL |  |
| sheet | A4 | done | 125/127 | FAIL | H11: result.A6: expected dict {"error": "#VALUE!"}, got int 0 |
| sheet | C1 | done | 0/127 | FAIL | P1: import failed: AttributeError: module 'solution' has no attribute 'evaluate' |
| sheet | C2 | done | 127/127 | PASS |  |
