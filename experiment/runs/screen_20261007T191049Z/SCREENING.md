# Problem screening

Spend cap $31.07; spent $23.3736. Single oracle per problem (reference.py); a failure counts only after it is traced to the spec by hand.

Keep rule (fixed before running): A strict-pass rate <= 25% and C strict passes >= 1.

| Problem | A passes (valid) | A mean cases | C passes (valid) | C mean cases | Cost | Keep candidate |
|---|---|---|---|---|---|---|
| policy | 1/4 | 0.25 | 0/2 | 0.0 | $2.77 | no: strong model passed 0/2 (needs >= 1) |
| washsale | 2/3 | 0.667 | 2/2 | 1.0 | $1.17 | no: cheap model passed 2/3 (> 25%) |
| roster | 3/4 | 0.75 | 2/2 | 1.0 | $2.78 | no: cheap model passed 3/4 (> 25%) |
| reconcile | 3/3 | 1.0 | 1/2 | 0.5 | $3.00 | no: cheap model passed 3/3 (> 25%) |
| recur | 1/4 | 0.498 | 2/2 | 1.0 | $2.10 | yes: cheap model usually fails and the strong model can solve it |
| schema | 0/4 | 0.0 | 0/2 | 0.0 | $2.60 | no: strong model passed 0/2 (needs >= 1) |
| ignore | 2/4 | 0.5 | 0/2 | 0.0 | $2.94 | no: cheap model passed 2/4 (> 25%); strong model passed 0/2 (needs >= 1) |
| merge3 | 4/4 | 1.0 | 2/2 | 1.0 | $1.66 | no: cheap model passed 4/4 (> 25%) |

## Runs

| Problem | Run | Status | Cases | Strict | First failure |
|---|---|---|---|---|---|
| ignore | A1 | timeout (no meta) | 0/- | FAIL |  |
| ignore | A2 | timeout (no meta) | 0/- | FAIL |  |
| ignore | A3 | done | 166/166 | PASS |  |
| ignore | A4 | done | 166/166 | PASS |  |
| ignore | C1 | done | 0/166 | FAIL | P1: import failed: AttributeError: module 'solution' has no attribute 'ignored' |
| ignore | C2 | done | 0/166 | FAIL | P1: import failed: AttributeError: module 'solution' has no attribute 'ignored' |
| merge3 | A1 | done | 193/193 | PASS |  |
| merge3 | A2 | done | 193/193 | PASS |  |
| merge3 | A3 | done | 193/193 | PASS |  |
| merge3 | A4 | done | 193/193 | PASS |  |
| merge3 | C1 | done | 193/193 | PASS |  |
| merge3 | C2 | done | 193/193 | PASS |  |
| policy | A1 | timeout (no meta) | 0/- | FAIL |  |
| policy | A2 | timeout (no meta) | 0/- | FAIL |  |
| policy | A3 | done | 133/133 | PASS |  |
| policy | A4 | timeout (no meta) | 0/- | FAIL |  |
| policy | C1 | done | 0/133 | FAIL | P1: import failed: AttributeError: module 'solution' has no attribute 'authorize' |
| policy | C2 | done | 0/133 | FAIL | P1: import failed: AttributeError: module 'solution' has no attribute 'authorize' |
| reconcile | A1 | done | 178/178 | PASS |  |
| reconcile | A2 | error (ReadError: [WinError 10054] An existing connection was forci) | 0/- | FAIL |  |
| reconcile | A3 | done | 178/178 | PASS |  |
| reconcile | A4 | done | 178/178 | PASS |  |
| reconcile | C1 | done | 178/178 | PASS |  |
| reconcile | C2 | done | 0/178 | FAIL | P1: import failed: AttributeError: module 'solution' has no attribute 'reconcile' |
| recur | A1 | done | 293/295 | FAIL | H23: OverflowError: date value out of range |
| recur | A2 | timeout (no meta) | 0/- | FAIL |  |
| recur | A3 | timeout (no meta) | 0/- | FAIL |  |
| recur | A4 | done | 295/295 | PASS |  |
| recur | C1 | done | 295/295 | PASS |  |
| recur | C2 | done | 295/295 | PASS |  |
| roster | A1 | timeout (no meta) | 0/- | FAIL |  |
| roster | A2 | done | 152/152 | PASS |  |
| roster | A3 | done | 152/152 | PASS |  |
| roster | A4 | done | 152/152 | PASS |  |
| roster | C1 | done | 152/152 | PASS |  |
| roster | C2 | done | 152/152 | PASS |  |
| schema | A1 | timeout (no meta) | 0/- | FAIL |  |
| schema | A2 | timeout (no meta) | 0/- | FAIL |  |
| schema | A3 | timeout (no meta) | 0/- | FAIL |  |
| schema | A4 | timeout (no meta) | 0/- | FAIL |  |
| schema | C1 | done | 0/177 | FAIL | P1: import failed: AttributeError: module 'solution' has no attribute 'validate' |
| schema | C2 | done | 0/177 | FAIL | P1: import failed: AttributeError: module 'solution' has no attribute 'validate' |
| washsale | A1 | done | 130/130 | PASS |  |
| washsale | A2 | error (ReadError: [WinError 10054] An existing connection was forci) | 0/- | FAIL |  |
| washsale | A3 | timeout (no meta) | 0/- | FAIL |  |
| washsale | A4 | done | 130/130 | PASS |  |
| washsale | C1 | done | 130/130 | PASS |  |
| washsale | C2 | done | 130/130 | PASS |  |
