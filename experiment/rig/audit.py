"""Deterministic audit record for every trial in a pilot run. No model is involved.

  python experiment/rig/audit.py experiment/runs/<pilot folder>

Writes <trial>/audit.json for each trial and audit_summary.json for the pilot. Every check has an ID,
a status (pass / fail / n/a) and evidence, so the observer's report can cite checks by ID and a reader can
verify every claim. Checks:
  freeze.hashes_match           spec, tests and references still match FROZEN.json
  spec.hash_matches_config      the spec file still matches the fingerprint recorded when the pilot started
  mutation.self_test            references score 39/39 and all deliberate bugs are caught (run once per pilot)
  harness.no_exception          the arm's own code did not crash
  isolation.no_tool_calls       no model call attempted a tool (rig runs declare none)
  output.matches_response       solution.py is exactly the code extracted from the model's raw response
  grade.reproduced              regrading now gives the same result as recorded in the pilot summary
  crucible.telemetry_consistent Crucible's results.json is untouched pipeline output (arm B)
  crucible.graded_is_winner     the graded solution is Crucible's first surviving branch (arm B)
  crucible.verdicts_vs_hidden   Crucible's own verdicts compared with the hidden grader (arm B)
"""
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RIG = Path(__file__).resolve().parent
EXP = RIG.parent
sys.path.insert(0, str(EXP))
import grade  # noqa: E402

sys.path.insert(0, str(EXP.parent))
from run_crucible import extract_code  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(cid, ok, evidence):
    status = "n/a" if ok is None else ("pass" if ok else "fail")
    return {"id": cid, "status": status, "evidence": evidence}


def pilot_level_checks(pilot: Path, summary: dict) -> list:
    frozen = json.loads((EXP / "sla" / "FROZEN.json").read_text(encoding="utf-8"))
    changed = [n for n, h in frozen["sha256"].items() if sha(EXP / "sla" / n) != h]
    checks = [check("freeze.hashes_match", not changed,
                    f"{len(frozen['sha256'])} files checked; changed: {changed or 'none'}")]
    cfg = summary["config"]
    spec_file = EXP / "sla" / cfg.get("spec", "SPEC.md")
    recorded = cfg.get("spec_sha256")
    checks.append(check("spec.hash_matches_config", None if not recorded else sha(spec_file) == recorded,
                        f"{spec_file.name}: recorded {recorded}, now {sha(spec_file)}"))
    proc = subprocess.run([sys.executable, str(EXP / "grade.py"), "--self-test"], capture_output=True, text=True)
    checks.append(check("mutation.self_test", proc.returncode == 0, proc.stdout.strip().splitlines()[-1] if proc.stdout else proc.stderr[-200:]))
    return checks


def telemetry_consistent(run_dir: Path):
    results = run_dir / "results.json"
    if not results.exists():
        return None, "no results.json"
    raw = results.read_text(encoding="utf-8")
    data = json.loads(raw)
    problems = []
    if json.dumps(data, indent=2) != raw:
        problems.append("not byte-identical to json.dump output")
    start = datetime.fromisoformat(data["start_time"]).timestamp()
    end = datetime.fromisoformat(data["end_time"]).timestamp()
    if abs(start - int(data["run_id"].split("-")[1])) > 5:
        problems.append("run_id does not match start_time")
    if abs((end - start) - data["total_duration_seconds"]) > 5:
        problems.append("duration does not match start/end times")
    archives = list((run_dir / "artifacts").glob("results_*.json"))
    if not any(sha(a) == sha(results) for a in archives):
        problems.append("no identical archive copy in artifacts/")
    return not problems, "; ".join(problems) or "byte-identical, times consistent, archive copy identical"


def audit_trial(run_dir: Path, row: dict) -> dict:
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8")) if (run_dir / "meta.json").exists() else {}
    checks = [check("harness.no_exception", not meta.get("traceback"), meta.get("error") or "no exception")]

    if meta.get("runner") == "rig":
        attempted = meta.get("tool_calls", 0)
        checks.append(check("isolation.no_tool_calls", attempted == 0,
                            f"{attempted} tool calls attempted across {meta.get('agent_calls', 1)} model calls; no tools were declared"))
    else:
        checks.append(check("isolation.no_tool_calls", None, "agent-framework run: see the SDK session logs instead"))

    solution, response = run_dir / "solution.py", run_dir / "response.txt"
    if solution.exists() and response.exists():
        same = extract_code(response.read_text(encoding="utf-8")) == solution.read_text(encoding="utf-8")
        checks.append(check("output.matches_response", same, f"solution sha256 {sha(solution)}"))
    else:
        checks.append(check("output.matches_response", None, "no raw response (arm B) or no solution"))

    if solution.exists():
        g = grade.grade(solution)
        recorded = (row or {}).get("failed_cases")
        now_failed = [c["id"] for c in g["cases"] if not c["pass"]]
        checks.append(check("grade.reproduced", recorded is None or recorded == now_failed,
                            f"now {g['passed']}/{g['total']}, failed {now_failed or 'none'}; recorded failed {recorded if recorded is not None else 'n/a'}"))
    else:
        checks.append(check("grade.reproduced", None, "no solution to grade"))

    if meta.get("arm") == "B":
        ok, ev = telemetry_consistent(run_dir)
        checks.append(check("crucible.telemetry_consistent", ok, ev))
        winners = meta.get("winners") or []
        if winners and solution.exists():
            rounds = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))["summary"]["total_iterations_run"]
            cand = run_dir / "candidates" / f"round{rounds}_{winners[0]}.py"
            checks.append(check("crucible.graded_is_winner", cand.exists() and sha(cand) == sha(solution),
                                f"graded solution vs {cand.name}"))
        else:
            checks.append(check("crucible.graded_is_winner", None, "Crucible promoted no winner"))
        verdicts = []
        for cand in sorted((run_dir / "candidates").glob("round*_branch_*.py")):
            cg = grade.grade(cand)
            verdicts.append({"candidate": cand.stem, "crucible": meta.get("crucible_verdicts", {}).get(cand.stem),
                             "hidden_grader": "PASS" if cg["strict_pass"] else f"FAIL ({cg['passed']}/{cg['total']})"})
        wrong = [v["candidate"] for v in verdicts if v["crucible"] is not None and (v["crucible"] == "PASS") != v["hidden_grader"].startswith("PASS")]
        checks.append(check("crucible.verdicts_vs_hidden", not wrong, {"disagreements": wrong, "candidates": verdicts}))

    return {"trial": run_dir.name, "arm": meta.get("arm"), "runner": meta.get("runner", "antigravity"), "checks": checks,
            "facts": {"spec": meta.get("spec"), "seconds": meta.get("seconds"), "agent_calls": meta.get("agent_calls"),
                      "cost_usd": meta.get("cost_usd"), "crucible_status": meta.get("crucible_status"),
                      "rounds_run": meta.get("rounds_run"), "strict_pass": (row or {}).get("strict_pass"),
                      "cases_passed": (row or {}).get("cases_passed"), "cases_total": (row or {}).get("cases_total")}}


def main(pilot: Path):
    summary = json.loads((pilot / "summary.json").read_text(encoding="utf-8"))
    rows = {r["run"]: r for r in summary["runs"]}
    pilot_checks = pilot_level_checks(pilot, summary)
    trials = {}
    for run_dir in sorted(p for p in pilot.iterdir() if p.is_dir() and p.name in rows):
        record = audit_trial(run_dir, rows[run_dir.name])
        record["pilot_checks"] = pilot_checks
        path = run_dir / "audit.json"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        trials[run_dir.name] = {"sha256": sha(path),
                                "failed_checks": [c["id"] for c in record["checks"] + pilot_checks if c["status"] == "fail"]}
        print(f"{run_dir.name}: {'all checks pass' if not trials[run_dir.name]['failed_checks'] else 'FAILED ' + ', '.join(trials[run_dir.name]['failed_checks'])}")
    out = {"pilot": pilot.name, "pilot_checks": pilot_checks, "trials": trials}
    (pilot / "audit_summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
