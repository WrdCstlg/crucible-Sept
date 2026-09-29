# Illustrative Failure Scenario: Iteration 1 (Contract Mismatch)

> **Specification Fixture:** This document illustrates a canonical failure pattern (API Contract Mismatch) demonstrating the Crucible's deterministic rejection criteria. For machine-generated empirical tournament logs from live runs, see the `results_*.json` telemetry archives.

**Verdict:** COMPLETE SYSTEMIC FAILURE: ZERO SURVIVORS  
**Exit Code:** 1 (DISCARDED)

**Autopsy Summary:**  
The LLM agents failed at Step Zero (API Contract Ignorance). None implemented standard entrypoint hooks (e.g., `def detect_cascades(stream)`). Python attempted to instantiate hallucinated dataclasses and uninitialized objects with a data generator, throwing fatal `TypeError` exceptions. 

**Action Taken:**  
The orchestrator intercepted the traceback, generated a diagnostic post-mortem, and passed the failure log back into the system prompt for Iteration 2.
