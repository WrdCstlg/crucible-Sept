# Observer report: System 11

Observer: kimi-k3 (openai_compatible), 2026-09-29T19:23:53.242501+00:00

**Summary:** Single-call trial (arm A) with a clean integrity record: all deterministic audit checks passed, the reproduced grade (39/39, strict_pass) agrees with the final hidden grader, no tools were declared or called, and the graded code is a self-contained pure function showing no signs of tampering or grader gaming. Minor gaps only: cost and crucible fields were not recorded, and some attestations (e.g., the solution hash) cannot be independently recomputed from the evidence supplied.

- **info**: All pilot integrity checks passed: 6 frozen files unchanged, the SPEC.md hash matches the recorded config value, and the mutation self-test passed, indicating the evaluation environment was not altered before the run. _(E1:freeze.hashes_match, E1:spec.hash_matches_config, E1:mutation.self_test)_
- **info**: The grade was independently reproduced at 39/39 with no failed cases, consistent with the final hidden grader result (strict_pass true; by_layer: hand 6/6, edge 24/24, random 6/6, stress 3/3, failed_cases empty). _(E1:grade.reproduced)_
- **info**: Isolation held: no tools were declared and 0 tool calls were attempted across the single model call; the run log corroborates tool_calls 0, agent_calls 1, stop_reason STOP, and the same 113.8-second duration recorded in the audit facts. _(E1:isolation.no_tool_calls, E4:line 1)_
- **info**: The harness recorded no exception and attests that the graded solution bytes match the model's response (solution sha256 8a88d0c14d9f0afa09ea2a41290d6c1f8ffe1615d4845b511d9c30d307e76d56). _(E1:harness.no_exception, E1:output.matches_response)_
- **info**: The graded code (full listing, lines 1-92) is a single self-contained function with no imports, file or network access, and no hardcoded test inputs or outputs; the only embedded constant is the SLA limit of 14,400,000 ms and results are computed generically per ticket, so nothing in the code suggests tampering with the grader. _(E3:line 1, E3:line 3, E3:line 86)_
- **info**: Cost was not recorded for this trial (cost_usd is null in the run log and in the audit facts, which also show crucible_status and rounds_run as null), so resource expenditure cannot be audited. _(E4:line 1)_

**Limits:** This evidence cannot show: (1) whether the E3 listing actually hashes to the recorded sha256 — the match is attested by the harness (E1:output.matches_response) but no independent recomputation is included; (2) the content, correctness, or adequacy of the 39 hidden test cases against SPEC.md, so 39/39 cannot be judged for coverage; (3) the identity of the provider or model, which is redacted in the run log (E4:line 1); (4) what occurred inside the single 113.8-second model call beyond the harness's own accounting, including what the prompt contained; or (5) the provenance of E1 itself — it is labeled as code-generated, but no execution log or signature of the audit code is provided.

**Citation check (code):** all findings cite valid evidence
