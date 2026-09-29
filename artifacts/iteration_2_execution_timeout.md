# Illustrative Failure Scenario: Iteration 2 (Execution Timeout)

> **Specification Fixture:** This document illustrates a canonical failure pattern (Watchdog Kill / O(n^2) Timeout) demonstrating the Crucible's deterministic rejection criteria. For machine-generated empirical tournament logs from live runs, see the `results_*.json` telemetry archives.

**Verdict:** TOTAL DISQUALIFICATION: ZERO SURVIVORS  
**Exit Code:** 124 (TIMEOUT EXPIRED)

**Autopsy Summary:**  
The agents successfully fixed the API contract errors from Iteration 1, but introduced a catastrophic O(n^2) deadlock when processing the simulated 5GB stream. None of the branches emitted a single byte of standard output before hitting the orchestrator's 120-second watchdog timer.

**Action Taken:**  
The Crucible's hard-kill switch (`subprocess.TimeoutExpired`) successfully aborted the hanging threads, preventing host machine resource exhaustion. The orchestrator flagged the timeout and forced a third architectural rewrite.
