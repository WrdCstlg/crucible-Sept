# Illustrative Failure Scenario: Iteration 3 (Type Hijack)

> **Specification Fixture:** This document illustrates a canonical failure pattern (Non-Callable Type Hijack) demonstrating the Crucible's deterministic rejection criteria. For machine-generated empirical tournament logs from live runs, see the `results_*.json` telemetry archives.

**Verdict:** ZERO SURVIVORS (Total Disqualification)  
**Exit Code:** 1 (DISCARDED)

**Autopsy Summary:**  
A zero-copy memory-mapped streaming engine (`branch_2`) and a bounded ring buffer FSM (`branch_3`) failed catastrophically at the API harness contract boundary. The test harness attempted to initialize the agents' architectures, but the LLMs exposed dataclasses and rigid finite-state machines without callable execution methods. 

**Action Taken:**  
The orchestrator correctly identified that interface contract fidelity is as vital as memory bounds. Having reached the maximum configuration limit of 3 iterations without a passing test suite, the Crucible aborted the deployment to protect the main branch from unverified code.
