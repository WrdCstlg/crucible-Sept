"""Verifies every piece of recorded evidence that can be checked without API keys.

  python experiment/verify_all.py

  1. Frozen test set: spec, cases and references still match FROZEN.json.
  2. Grader self-test: both references score every case, and every deliberate bug is caught.
  3. Audit records: every trial's audit.json still matches the fingerprint in its pilot's audit_summary.json.
  4. Observer ledgers: every chain is intact and every observer report is unedited.
  5. Replay: every recorded Crucible verdict reproduces when its recorded code and tests are re-executed (no model calls).
  6. Problem 5 (the pre-registered study's problem): its frozen set matches bizsla/FROZEN.json, and its grader
     self-test passes (both oracles agree; all 22 planted bugs are caught). Runs in crucible.sandbox (Docker by
     default; set CRUCIBLE_SANDBOX=subprocess-unsafe where Docker is unavailable).
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

    import replay  # imported only here: it loads the Crucible orchestrator
    for pilot in sorted(p for p in (HERE / "runs").iterdir() if p.is_dir() and p.name.startswith("pilot")):
        crucible_runs = [r for r in sorted(pilot.iterdir()) if r.is_dir() and (r / "results.json").exists()]
        if not crucible_runs:
            continue
        reports = [replay.replay_run(r, counterfactual=False) for r in crucible_runs]
        total = sum(len(v["verdicts"]) for rep in reports for v in rep["rounds"])
        bad = sum(rep["mismatches"] for rep in reports)
        if total == 0:
            continue  # e.g. the invalid pilot: its Crucible runs crashed before judging anything
        print(f"[{'pass' if not bad else 'FAIL'}] replay reproduces {total - bad}/{total} recorded Crucible verdicts in {pilot.name}")
        ok &= not bad

    print("--- Problem 5 (bizsla): freeze and grader self-test ---")
    import importlib.util

    def load(name, path):                    # by path: experiment/sla and experiment/ have modules with these names
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod
    bizgen = load("bizsla_generate_cases", HERE / "bizsla" / "generate_cases.py")
    ok &= bizgen.check()
    sys.modules["generate_cases"] = bizgen   # grade.py does `from generate_cases import stress_lines`
    bizgrade = load("bizsla_grade", HERE / "bizsla" / "grade.py")
    ok &= bizgrade.self_test()
    print("ALL EVIDENCE VERIFIED" if ok else "VERIFICATION FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
