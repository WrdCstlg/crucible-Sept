"""Replays recorded Crucible arenas with zero model calls.

  python experiment/replay.py experiment/runs/<pilot folder>                    replay and write replay.json
  python experiment/replay.py --check experiment/runs/<pilot folder>            exit 1 on any mismatch; writes nothing (CI)
  python experiment/replay.py --counterfactual experiment/runs/<pilot folder>   also apply the deterministic policy

Replay: for every arm-B run, each recorded candidate is re-executed against the suites that were in force when it
was judged, under the verdict policy recorded for that run, and every verdict is compared with results.json.
Runs recorded before the deterministic policy existed are replayed under the legacy policy (every suite blocks,
unseeded environment), exactly as they ran.

Counterfactual: the same recorded code and tests are judged under the deterministic policy: a suite blocks only if the
trusted reference passes it in every one of 3 runs, the environment is seeded, and a candidate with no decisive check
is UNVERIFIED and never promoted. Two variants: reference only, and reference plus the author's 6 hand cases as
acceptance cases (which are also 6 of the 39 hidden cases). The report says what Crucible would have promoted and how
the hidden grader scores it. It cannot say what the models would have written next: from round 2 on, the recorded
candidates were generated with feedback from the policy that actually ran.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP))
sys.path.insert(0, str(EXP.parent))
import grade  # noqa: E402
from run_crucible import ACCEPTANCE_RUNNER, CrucibleOrchestrator, deterministic_env, load_acceptance_cases, run_python  # noqa: E402

REFERENCE = EXP / "sla" / "reference.py"
HAND_CASES = EXP / "sla" / "hand_cases.json"
STABILITY_RUNS = 3


def recordings(run_dir: Path) -> dict:
    """{round: {"branches": {name: path}, "suite": path}} for experiment runs (candidates/) and Crucible runs (rounds/)."""
    rounds = {}
    for f in (run_dir / "candidates").glob("round*_branch_*.py"):
        r, name = f.stem.split("_", 1)
        rounds.setdefault(int(r[5:]), {"branches": {}})["branches"][name] = f
    for f in (run_dir / "candidates").glob("round*_crucible_tests.py"):
        rounds.setdefault(int(f.stem.split("_")[0][5:]), {"branches": {}})["suite"] = f
    for d in (run_dir / "rounds").glob("round*"):
        r = int(d.name[5:])
        rounds[r] = {"branches": {f.stem: f for f in d.glob("branch_*.py")},
                     "suite": next(iter(d.glob("arena_test_iter_*.py")), None)}
    return dict(sorted(rounds.items()))


def run_suite(candidate: Path, suite: Path, deterministic: bool) -> int:
    with tempfile.TemporaryDirectory(prefix="crucible_replay_") as d:
        shutil.copy(candidate, Path(d) / "solution.py")
        shutil.copy(suite, Path(d) / "arena_test_suite.py")
        return run_python("arena_test_suite.py", Path(d), deterministic=deterministic)[0]


def judge(candidate: Path, suites: list[Path], entrypoint: str, deterministic: bool) -> str:
    ok, _ = CrucibleOrchestrator._audit_contract(candidate, entrypoint=entrypoint)
    if not ok:
        return "AST_REJECTED"
    for suite in suites:
        code = run_suite(candidate, suite, deterministic)
        if code != 0:
            return "TIMEOUT" if code == 124 else "FAIL"
    return "PASS"


def passes_acceptance(candidate: Path, cases: list[dict], entrypoint: str) -> bool:
    with tempfile.TemporaryDirectory(prefix="crucible_replay_acc_") as d:
        shutil.copy(candidate, Path(d) / "solution.py")
        (Path(d) / "acceptance_cases.json").write_text(json.dumps(cases), encoding="utf-8")
        (Path(d) / "acceptance_runner.py").write_text(ACCEPTANCE_RUNNER, encoding="utf-8")
        try:
            p = subprocess.run([sys.executable, "acceptance_runner.py", entrypoint], cwd=d, capture_output=True,
                               text=True, timeout=120, env=deterministic_env())
            return p.returncode == 0
        except subprocess.TimeoutExpired:
            return False


def judge_deterministic(candidate: Path, admitted: list[Path], cases: list[dict], entrypoint: str) -> str:
    """The deterministic policy, including fail-closed: no decisive check means no promotion."""
    ok, _ = CrucibleOrchestrator._audit_contract(candidate, entrypoint=entrypoint)
    if not ok:
        return "AST_REJECTED"
    if not cases and not admitted:
        return "UNVERIFIED"
    if cases and not passes_acceptance(candidate, cases, entrypoint):
        return "ACCEPTANCE_FAIL"
    return judge(candidate, admitted, entrypoint, deterministic=True)


def admit(suite: Path) -> dict:
    codes = [run_suite(REFERENCE, suite, deterministic=True) for _ in range(STABILITY_RUNS)]
    decision = "admitted" if all(c == 0 for c in codes) else "quarantined"
    return {"suite": suite.name, "decision": decision, "reference_exit_codes": codes}


def replay_run(run_dir: Path, counterfactual: bool) -> dict:
    telemetry = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    policy = telemetry["configuration"].get("verdict_policy", {}).get("name", "legacy")
    entrypoint = telemetry["configuration"].get("entrypoint", "process_telemetry")
    recorded = {it["iteration"]: {b["name"]: b["status"] for b in it["branches"]} for it in telemetry["iterations"]}
    rounds = recordings(run_dir)
    report = {"run": run_dir.name, "recorded_policy": policy, "rounds": [], "mismatches": 0}

    if policy != "legacy":
        report["note"] = "deterministic-policy runs are replayed with their saved admission decisions"
    suites_so_far = []
    for r, rec in rounds.items():
        if rec.get("suite"):
            suites_so_far.append(rec["suite"])
        if policy == "legacy":
            blocking = list(suites_so_far)
        else:
            blocking = [s for s in suites_so_far
                        if json.loads((s.parent / "admission.json").read_text(encoding="utf-8"))["decision"] == "admitted"]
        rows = []
        for name, cand in sorted(rec["branches"].items()):
            got = judge(cand, blocking, entrypoint, deterministic=(policy != "legacy"))
            want = recorded.get(r, {}).get(name)
            if got != want:
                report["mismatches"] += 1
            rows.append({"branch": name, "recorded": want, "replayed": got, "match": got == want})
        report["rounds"].append({"round": r, "suites_blocking": [s.name for s in blocking], "verdicts": rows})

    if counterfactual:
        admissions = {r: admit(rec["suite"]) if rec.get("suite") else None for r, rec in rounds.items()}
        report["counterfactual"] = {
            "reference_only": counterfactual_policy(rounds, admissions, [], entrypoint),
            "reference_and_hand_cases": counterfactual_policy(rounds, admissions, load_acceptance_cases(HAND_CASES), entrypoint),
            "note": "Variant 2 uses the author's 6 hand cases as acceptance cases; they are also 6 of the 39 hidden "
                    "cases, so its hidden grade is not fully independent.",
        }
    return report


def counterfactual_policy(rounds: dict, admissions: dict, cases: list[dict], entrypoint: str) -> dict:
    admitted_so_far, out = [], {"rounds": [], "promoted": None, "hidden_grader": "nothing promoted"}
    for r, rec in rounds.items():
        if admissions[r] and admissions[r]["decision"] == "admitted":
            admitted_so_far.append(rec["suite"])
        verdicts = {n: judge_deterministic(c, admitted_so_far, cases, entrypoint) for n, c in sorted(rec["branches"].items())}
        out["rounds"].append({"round": r, "admission": admissions[r], "verdicts": verdicts})
        winners = [n for n, v in verdicts.items() if v == "PASS"]
        if winners:
            g = grade.grade(rec["branches"][winners[0]])
            out["promoted"] = f"round{r}_{winners[0]}"
            out["hidden_grader"] = f"{g['passed']}/{g['total']}" + (" (strict pass)" if g["strict_pass"] else "")
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pilot")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--counterfactual", action="store_true")
    a = ap.parse_args()
    pilot = Path(a.pilot).resolve()
    runs = [p for p in sorted(pilot.iterdir()) if p.is_dir() and (p / "results.json").exists()]
    reports = [replay_run(p, a.counterfactual and not a.check) for p in runs]
    total = sum(len(v["verdicts"]) for rep in reports for v in rep["rounds"])
    bad = sum(rep["mismatches"] for rep in reports)
    for rep in reports:
        verdicts = [f"r{v['round']}:{row['branch']}={row['replayed']}{'' if row['match'] else ' (recorded ' + str(row['recorded']) + ')'}"
                    for v in rep["rounds"] for row in v["verdicts"]]
        print(f"{rep['run']} [{rep['recorded_policy']}]: {', '.join(verdicts)}")
        if "counterfactual" in rep:
            for label, cf in (("reference only", rep["counterfactual"]["reference_only"]),
                              ("reference + 6 hand cases", rep["counterfactual"]["reference_and_hand_cases"])):
                adm = ", ".join(f"r{x['round']} suite {x['admission']['decision']}" for x in cf["rounds"] if x["admission"])
                last = cf["rounds"][-1]["verdicts"] if cf["rounds"] else {}
                print(f"   counterfactual, {label}: {adm}; last verdicts {last}; promoted {cf['promoted']}; "
                      f"hidden grader {cf['hidden_grader']}")
    print(f"{pilot.name}: {total - bad}/{total} recorded verdicts reproduced" + ("" if not bad else f"; {bad} MISMATCH(ES)"))
    if not a.check:
        (pilot / "replay.json").write_text(json.dumps(reports, indent=2, default=str), encoding="utf-8")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
