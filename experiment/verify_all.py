"""Verifies every piece of recorded evidence that can be checked without API keys.

  python experiment/verify_all.py

  1. Frozen test set: spec, cases and references still match FROZEN.json.
  2. Grader self-test: both references score every case, and every deliberate bug is caught.
  3. Audit records: every trial's audit.json still matches the fingerprint in its pilot's audit_summary.json.
  4. Observer ledgers: every chain is intact and every observer report is unedited.
Exit code 1 if anything fails. Runs in CI on every push.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "rig"))
import grade  # noqa: E402
import run_pilot  # noqa: E402


def main() -> bool:
    ok = True
    try:
        run_pilot.verify_freeze()
        print("[pass] frozen test set matches FROZEN.json")
    except SystemExit as e:
        print(f"[FAIL] frozen test set: {e}")
        ok = False

    print("--- grader self-test ---")
    ok &= grade.self_test()

    runs = sorted((HERE / "runs").glob("*/audit_summary.json"))
    for summary_path in runs:
        pilot = summary_path.parent
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        bad = [t for t, info in summary["trials"].items()
               if not (pilot / t / "audit.json").exists()
               or hashlib.sha256((pilot / t / "audit.json").read_bytes()).hexdigest() != info["sha256"]]
        print(f"[{'pass' if not bad else 'FAIL'}] audit records unedited in {pilot.name}" + (f": {bad}" if bad else ""))
        ok &= not bad

    ledgers = sorted((HERE / "runs").glob("*/ledger.jsonl"))
    if ledgers:
        import observe  # imported only when there is something to verify
        for ledger in ledgers:
            print(f"--- observer ledger: {ledger.parent.name} ---")
            ok &= observe.verify(ledger.parent)
    print("ALL EVIDENCE VERIFIED" if ok else "VERIFICATION FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
