# Hand-case sign-off (bizsla)

Required by [PREREGISTRATION.md](../PREREGISTRATION.md) §9. Recorded exactly as given.

| Field | Value |
|---|---|
| Date of approval | 2026-10-06 |
| Approved by | The author |
| Cases covered | All 20 in `hand_cases.json` |
| Kind of review | **Approval without a case-by-case check.** The author did not compare each case's expected output against `SPEC.md` and its written justification. |
| Disagreements found | None reported. Because no case-by-case check was done, this is not evidence that every case is correct. |
| File approved | `hand_cases.json`, sha256 `31828c4b2db00be30d70a60eb4f59ec28c7c932f82782ab27616da6fe7959942` |
| Matches the freeze | Yes. Same hash as in [`FROZEN.json`](FROZEN.json), whose own sha256 is the pre-registered `39c19fed1490ee3007ef63e543c16d0f24c9ec8827bae94188589d34db2528b0` |

## Timing

§9 asks for this review **before** the live run. The live run started 2026-10-05T22:41:31Z
(`experiment/runs/study_20261005T224131Z`). This approval was given afterwards, so it does not satisfy §9 as written.
[STUDY_RESULTS.md](../STUDY_RESULTS.md) keeps Deviation 3 open and records this note there.

## What still guards the cases

- Both oracles (`reference.py` and `brute_force.py`) must match every hand case
  ([`tests/test_bizsla_oracles.py`](../../tests/test_bizsla_oracles.py)).
- Every case carries a written justification, which that test checks for.
- Both oracles and the cases were drafted by Claude (STUDY_RESULTS.md §6, "Who wrote the ground truth"). So oracle
  agreement cannot rule out a misreading of the spec that all of them share. A case-by-case human check is the step
  that would.

If a case is later found to be wrong, the published study is not edited. The error and its effect on the 225-case
grades go into STUDY_RESULTS.md under "Deviations".
