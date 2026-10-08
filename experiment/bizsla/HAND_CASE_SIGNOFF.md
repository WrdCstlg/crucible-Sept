# Hand-case sign-off (bizsla)

Required by [PREREGISTRATION.md](../PREREGISTRATION.md) §9. Recorded exactly as given.

| Field | Value |
|---|---|
| Date of review | 2026-10-08 |
| Reviewed by | The author |
| Cases covered | All 20 in `hand_cases.json` (H01–H20) |
| Kind of review | Case by case: each case's expected output was worked out from `SPEC.md` and compared with the case and its written justification |
| Outcome | **All 20 agree.** No case was changed. |
| File reviewed | `hand_cases.json`, sha256 `31828c4b2db00be30d70a60eb4f59ec28c7c932f82782ab27616da6fe7959942` |
| Matches the freeze | Yes. Same hash as in [`FROZEN.json`](FROZEN.json), whose own sha256 is the pre-registered `39c19fed1490ee3007ef63e543c16d0f24c9ec8827bae94188589d34db2528b0` |

## Timing

§9 asks for this review **before** the live run. The live run started 2026-10-05T22:41:31Z
(`experiment/runs/study_20261005T224131Z`). This review was done afterwards, so it does not satisfy §9 as written, and
[STUDY_RESULTS.md](../STUDY_RESULTS.md) keeps Deviation 3. Because the reviewed file is byte-identical to the frozen
one, the review covers exactly the cases the study was graded on.

## What guards the cases

- This human review, which can catch a misreading of the spec that the oracles share. Both oracles and the cases were
  drafted by Claude (STUDY_RESULTS.md §6, "Who wrote the ground truth"), so their agreement alone could not.
- Both oracles (`reference.py` and `brute_force.py`) must match every hand case
  ([`tests/test_bizsla_oracles.py`](../../tests/test_bizsla_oracles.py)), and every case must carry a written
  justification.

If a case is later found to be wrong, the published study is not edited. The error and its effect on the 225-case
grades go into STUDY_RESULTS.md under "Deviations".
