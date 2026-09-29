# Crucible Execution Artifacts

This directory contains execution artifacts, failure scenario fixtures, and empirical telemetry from Crucible tournament cycles.

## Illustrative Failure Scenarios (Specification Fixtures)

The `.md` files document an illustrative 3-iteration tournament scenario where **all candidate branches are rejected**, demonstrating the Crucible's hard-rejection authority across canonical systems failure modes:

| File | Failure Mode | Description |
|:---|:---|:---|
| [`iteration_1_contract_mismatch.md`](iteration_1_contract_mismatch.md) | Contract Mismatch | Runtime typing instantiation (`Any()`, `Generator()`) |
| [`iteration_2_execution_timeout.md`](iteration_2_execution_timeout.md) | Execution Timeout | $O(n^2)$ deadlock triggering 120-second watchdog kill |
| [`iteration_3_type_hijack.md`](iteration_3_type_hijack.md) | Type Hijack | Non-callable dataclass violating execution contract |

> **Note:** The `.md` failure scenarios are specification fixtures illustrating specific failure forensics; the `results_*.json` files provide complete, machine-readable telemetry from live executions.

---

## Empirical Tournament Telemetry (Automated Live Runs)

The `results_*.json` files capture machine-generated telemetry from verified live tournaments across three evolutionary phases of the protocol:

### 1. `results_1790664878.json` (Run ID: `crucible-1790662868`)
- **Status:** `PASSED` (3 promoted winners)
- **Protocol State:** Historical exploratory baseline (pre-lockdown, per-round test gating).
- **Execution Profile:** 3 iterations against a simulated 5GB continuous stream (200,000+ records). Promoted three winners (`branch_1`, `branch_2`, `branch_3`) under Iteration 3's test suite.
- **Audit Context:** This historical baseline predates both the agent security policy lockdown and cumulative regression gating (its promoted winners passed round 3 tests but failed round 2's test suite).

### 2. `results_1790668156.json` (Run ID: `crucible-1790667552`)
- **Status:** `PASSED` (1 promoted winner: `branch_1`)
- **Protocol State:** Live run with agent lockdown (`policy.deny_all()`) and single-round validation (`--force-iterations=1`).
- **Security Telemetry:** Agents attempted 16 unauthorized tool calls (directory listings, file reads); the Antigravity SDK security policy denied every attempt.
- **Execution Profile:** Promoted `branch_1` upon passing Iteration 1's adversarial harness.

### 3. `results_1790673816.json` (Run ID: `crucible-1790671763` — Matches Root `results.json`)
- **Status:** `FAILED` (Zero survivors across 3 iterations, 9 evaluations)
- **Protocol State:** Full agent lockdown (`policy.deny_all()`), cumulative regression gates, and forced multi-round hardening (`--force-iterations=3`).
- **Security Telemetry:** Agents attempted 26 unauthorized tool calls; the Antigravity SDK policy denied 100% of attempts.
- **Forensic Audit Finding:** 8 of 9 candidate rejections were triggered by Round 1's cumulative test harness. Independent auditing revealed a logic defect in the adversarial QA generator's synthetic data stream (`arena_test_iter_1.py:196-217`): an "isolated" 96.0°C spike followed 20ms later by a 91.0°C reading was emitted every 1,000 records, creating 549 actual cascade events against a hardcoded assertion expecting 49. Because the cumulative regression gate carried Round 1's flawed test into all subsequent iterations, total elimination was guaranteed regardless of candidate correctness.
