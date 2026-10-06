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
  7. The published study (runs/study_*, non-mock): its recorded pre-registration and freeze hashes match the files
     in this repository; every run's summary row matches its grade.json; and re-running the pre-registered analysis
     on the recorded rows reproduces every tally and p-value. With --regrade-study, every recorded solution and
     every Crucible candidate is re-graded by the hidden grader in the sandbox and must match (slow: ~116 grades).
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


def verify_study(study: Path, bizgrade, regrade: bool) -> bool:
    """Step 7 for one runs/study_* folder. Never writes to it."""
    import importlib.util
    config = json.loads((study / "config.json").read_text(encoding="utf-8"))
    summary = json.loads((study / "summary.json").read_text(encoding="utf-8"))
    if config.get("mock"):
        return True
    ok = True

    def report(passed, what):
        nonlocal ok
        print(f"[{'pass' if passed else 'FAIL'}] {study.name}: {what}")
        ok &= bool(passed)

    prereg_sha = hashlib.sha256((HERE / "PREREGISTRATION.md").read_bytes()).hexdigest()
    report(prereg_sha == config["prereg"]["sha256"], "recorded pre-registration sha256 matches PREREGISTRATION.md")
    frozen = json.loads((HERE / "bizsla" / "FROZEN.json").read_text(encoding="utf-8"))["sha256"]
    report(frozen == config["freeze_sha256"], "test set at launch matches bizsla/FROZEN.json")

    bad = []
    for row in summary["runs"]:
        g_path = study / row["run"] / "grade.json"
        if g_path.exists():
            g = json.loads(g_path.read_text(encoding="utf-8"))
            if (g["strict_pass"], g["passed"]) != (row["strict_pass"], row["cases_passed"]):
                bad.append(row["run"])
        elif row["strict_pass"] or row["cases_passed"]:
            bad.append(row["run"])
    report(not bad, f"{len(summary['runs']) - len(bad)}/{len(summary['runs'])} summary rows match their grade.json"
           + (f": {bad}" if bad else ""))

    spec = importlib.util.spec_from_file_location("study_run_study", HERE / "study" / "run_study.py")
    run_study = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_study)
    rec = summary["analysis"]
    an = run_study.analyze(summary["runs"], summary["b_candidates"], summary["gate_out_of_sample"],
                           {a: rec["arms"][a]["planned"] for a in "ABC"})
    same = (an["arms"] == rec["arms"] and an["H3_crucible_vs_hidden"] == rec["H3_crucible_vs_hidden"]
            and an["H4_gate_out_of_sample"] == rec["H4_gate_out_of_sample"] and an["integrity"] == rec["integrity"]
            and all(an[h]["p_two_sided"] == rec[h]["p_two_sided"] for h in ("H1_B_vs_C", "H2_B_vs_A")))
    report(same, "pre-registered analysis reproduces every recorded tally and p-value")

    if regrade:
        from crucible.sandbox import default_sandbox
        sandbox = default_sandbox()
        mism = []
        for row in summary["runs"]:
            sol = study / row["run"] / "solution.py"
            if sol.exists():
                g = bizgrade.grade(sol, sandbox)
                if (g["strict_pass"], g["passed"]) != (row["strict_pass"], row["cases_passed"]):
                    mism.append(row["run"])
        for c in summary["b_candidates"]:
            g = bizgrade.grade(study / c["run"] / "candidates" / f"{c['candidate']}.py", sandbox)
            if (g["strict_pass"], g["passed"]) != (c["hidden_pass"], c["cases_passed"]):
                mism.append(f"{c['run']}/{c['candidate']}")
        report(not mism, f"re-grading every solution and candidate in the {sandbox.backend} sandbox reproduces the "
               "recorded grades" + (f": {mism}" if mism else ""))
    return ok


def main(regrade_study: bool = False) -> bool:
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

    studies = sorted(p for p in (HERE / "runs").glob("study_*") if (p / "summary.json").exists())
    if studies:
        print("--- published study: hashes, grades and pre-registered analysis ---")
    for study in studies:
        ok &= verify_study(study, bizgrade, regrade_study)
    print("ALL EVIDENCE VERIFIED" if ok else "VERIFICATION FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main(regrade_study="--regrade-study" in sys.argv[1:]) else 1)
