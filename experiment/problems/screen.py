"""Screening pass for the candidate problems in experiment/problems/: is each one hard enough for the cheap model?

    python experiment/problems/screen.py --plan-only --cap-usd 10                 worst-case cost; no model calls
    python experiment/problems/screen.py --cap-usd 10 --env-file "../Project Crucible/.env"
    python experiment/problems/screen.py --mock --unsafe-subprocess-sandbox       zero-cost plumbing check (never evidence)

Per problem: --a-runs single calls to the evaluated (cheap) role and --c-runs single calls to the competitor (strong)
role, through the same experiment/study/arm_study.py the study used (same system prompt; the only user text is the
problem's SPEC.md). No Crucible arm: screening asks how hard the problem is, not whether Crucible helps.

Spend cap: the same fail-closed reservation as experiment/study/run_study.py (Budget, worst_case_run, run_one are
imported from it, not copied). Each run reserves its enforced worst case before it starts.

KEEP RULE, fixed here before any live screening run (KEEP_RULE below):
    keep_candidate  =  A strict passes <= 25% of valid A runs   (the cheap model alone usually fails)
                   and C strict passes >= 1                      (the problem is solvable from the spec)
A problem flagged keep_candidate is only a candidate: every failure must still be read by hand and traced to the
spec (not to a bug in reference.py or in the cases) before it is kept. That review is recorded in BACKLOG.md.

Refuses to start if any problem's screen_cases.json differs from a fresh build (the reference or cases changed and
the expected outputs were not rebuilt).
"""
import argparse
import importlib.util
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ROOT = EXP.parent
STUDY = EXP / "study"
PROBLEMS = ["orderbook", "semver", "sheet", "promo", "payroll"]
CONCURRENCY = {"A": 3, "C": 3}
KEEP_RULE = {"a_max_pass_rate": 0.25, "c_min_passes": 1}


def _load(name: str, path: Path):
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod


common = _load("problems_common", HERE / "common.py")
rs = _load("study_run_study", STUDY / "run_study.py")


def stale_problems(problems) -> list:
    """Problems whose stored screen_cases.json is not what a fresh build produces."""
    bad = []
    for p in problems:
        path = common.problem_dir(p) / "screen_cases.json"
        if not path.exists() or json.loads(path.read_text(encoding="utf-8")) != common.build(p, write=False):
            bad.append(p)
    return bad


def plan(problems, a_runs, c_runs) -> list:
    """(problem, run name) pairs, interleaved so a cap stop truncates problems and arms evenly."""
    order = []
    for i in range(1, max(a_runs, c_runs) + 1):
        for p in problems:
            for arm, n in (("A", a_runs), ("C", c_runs)):
                if i <= n:
                    order.append((p, f"{arm}{i}"))
    return order


def keep_verdict(a: dict, c: dict) -> dict:
    if not a["valid"] or not c["valid"]:
        return {"keep_candidate": False, "why": "undefined: an arm has no valid runs"}
    a_rate = a["strict_passes"] / a["valid"]
    easy = a_rate > KEEP_RULE["a_max_pass_rate"]
    unsolved = c["strict_passes"] < KEEP_RULE["c_min_passes"]
    why = []
    if easy:
        why.append(f"cheap model passed {a['strict_passes']}/{a['valid']} (> {KEEP_RULE['a_max_pass_rate']:.0%})")
    if unsolved:
        why.append(f"strong model passed {c['strict_passes']}/{c['valid']} (needs >= {KEEP_RULE['c_min_passes']})")
    return {"keep_candidate": not (easy or unsolved),
            "why": "; ".join(why) or "cheap model usually fails and the strong model can solve it"}


def summarize(problems, rows) -> dict:
    out = {}
    for p in problems:
        arms = {}
        for a in "AC":
            mine = [r for r in rows if r["problem"] == p and r["arm"] == a]
            valid = [r for r in mine if not r["harness_error"]]
            arms[a] = {"runs": len(mine), "valid": len(valid), "harness_errors": len(mine) - len(valid),
                       "strict_passes": sum(r["strict_pass"] for r in valid),
                       "mean_case_fraction": round(sum(r["cases_passed"] / r["cases_total"] for r in valid
                                                       if r["cases_total"]) / len(valid), 3) if valid else None,
                       "cost_usd": round(sum(r["cost_usd"] or 0 for r in mine), 4)}
        out[p] = {"arms": arms, **keep_verdict(arms["A"], arms["C"])}
    return out


def render(summary) -> str:
    c = summary["config"]
    L = [f"# Problem screening{' (MOCK DRY RUN: NOT EVIDENCE)' if c['mock'] else ''}", "",
         f"Spend cap ${c['cap_usd']:.2f}; spent ${summary['spent_usd']:.4f}. Single oracle per problem "
         "(reference.py); a failure counts only after it is traced to the spec by hand.", "",
         f"Keep rule (fixed before running): A strict-pass rate <= {KEEP_RULE['a_max_pass_rate']:.0%} and "
         f"C strict passes >= {KEEP_RULE['c_min_passes']}.", "",
         "| Problem | A passes (valid) | A mean cases | C passes (valid) | C mean cases | Cost | Keep candidate |",
         "|---|---|---|---|---|---|---|"]
    for p, v in summary["problems"].items():
        A, C = v["arms"]["A"], v["arms"]["C"]
        L.append(f"| {p} | {A['strict_passes']}/{A['valid']} | {A['mean_case_fraction']} | "
                 f"{C['strict_passes']}/{C['valid']} | {C['mean_case_fraction']} | "
                 f"${A['cost_usd'] + C['cost_usd']:.2f} | {'yes' if v['keep_candidate'] else 'no'}: {v['why']} |")
    if summary["not_run"]:
        L.append(f"\nNot run (spend cap): {', '.join('/'.join(x) for x in summary['not_run'])}")
    if summary.get("budget_halted"):
        L.append(f"\nLaunches halted: {summary['budget_halted']}")
    L += ["", "## Runs", "", "| Problem | Run | Status | Cases | Strict | First failure |", "|---|---|---|---|---|---|"]
    for r in summary["runs"]:
        L.append(f"| {r['problem']} | {r['run']} | {r['status']}"
                 f"{' (' + str(r['error'])[:60] + ')' if r['error'] else ''} | "
                 f"{r['cases_passed']}/{r['cases_total'] or '-'} | {'PASS' if r['strict_pass'] else 'FAIL'} | "
                 f"{(r['first_failure'] or '')[:120]} |")
    return "\n".join(L) + "\n"


def execute(order, run_dir, roles, budget, child_env):
    sems = {a: threading.Semaphore(n) for a, n in CONCURRENCY.items()}
    results, skipped, lock = {}, [], threading.Lock()

    def task(item):
        problem, name = item
        arm = name[0]
        worst = rs.worst_case_run(arm, roles)
        with sems[arm]:
            if not budget.reserve(worst):
                with lock:
                    skipped.append(item)
                print(f"[{rs.stamp()}] {problem}/{name} not run (spend cap ${budget.cap:.2f})", flush=True)
                return
            env = {**child_env, "PILOT_SPEC": str(common.problem_dir(problem) / "SPEC.md"),
                   "CRUCIBLE_MOCK_SEED": f"{problem}/{name}"}
            print(f"[{rs.stamp()}] start {problem}/{name} (reserved ${worst:.4f})", flush=True)
            r = rs.run_one(name, run_dir / problem / name, env)
            cost = r["meta"].get("cost_usd")
            budget.settle(worst, cost)
            with lock:
                results[item] = r
            print(f"[{rs.stamp()}] end {problem}/{name}: {r['status']} cost={cost} spent=${budget.spent:.4f}",
                  flush=True)

    with ThreadPoolExecutor(sum(CONCURRENCY.values())) as pool:
        list(pool.map(task, order))
    return results, skipped


def grade_all(results, run_dir, sandbox) -> list:
    rows = []
    for (problem, name) in sorted(results):
        r = results[(problem, name)]
        meta, d = r["meta"], run_dir / problem / name
        sol = d / "solution.py"
        g = common.grade(problem, sol, sandbox) if sol.exists() else None
        if g:
            (d / "grade.json").write_text(json.dumps(g, indent=2), encoding="utf-8")
        rows.append({"problem": problem, "run": name, "arm": name[0], "status": r["status"],
                     "error": meta.get("error"), "harness_error": rs.is_harness_error(r),
                     "spec_seen": meta.get("spec"), "cost_usd": meta.get("cost_usd"), "seconds": r["seconds"],
                     "input_tokens": (meta.get("usage") or {}).get("input_tokens"),
                     "strict_pass": bool(g and g["strict_pass"]), "cases_passed": g["passed"] if g else 0,
                     "cases_total": g["total"] if g else None, "by_layer": g["by_layer"] if g else None,
                     "first_failure": g["first_failure"] if g else None})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--problems", nargs="+", default=PROBLEMS, choices=PROBLEMS)
    ap.add_argument("--a-runs", type=int, default=4)
    ap.add_argument("--c-runs", type=int, default=2)
    ap.add_argument("--cap-usd", type=float)
    ap.add_argument("--roles", help="roles file (default roles_study.json; with --mock, roles_mock.json)")
    ap.add_argument("--env-file")
    ap.add_argument("--mock", action="store_true", help="zero-cost dry run with roles_mock.json (never evidence)")
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--out-root", default=str(EXP / "runs"))
    ap.add_argument("--unsafe-subprocess-sandbox", action="store_true", help="mock runs only")
    a = ap.parse_args(argv)

    from crucible.sandbox import Sandbox, default_sandbox, docker_available
    default_roles = STUDY / ("roles_mock.json" if a.mock else "roles_study.json")
    roles_path = Path(a.roles).resolve() if a.roles else default_roles
    roles = json.loads(roles_path.read_text(encoding="utf-8"))
    live = any(r["provider"] != "mock" for r in roles.values())
    if a.mock and live:
        raise SystemExit("STOP: --mock with a non-mock roles file")
    if a.unsafe_subprocess_sandbox and live:
        raise SystemExit("STOP: live model output is only ever executed in the Docker sandbox")
    stale = stale_problems(a.problems)
    if stale:
        raise SystemExit(f"STOP: screen_cases.json is stale for {stale}; run `common.py build <name>` and re-check")
    order = plan(a.problems, a.a_runs, a.c_runs)
    worst = {arm: rs.worst_case_run(arm, roles) for arm in "AC"}
    total_worst = round(sum(worst[n[0]] for _, n in order), 2)
    print(f"{len(a.problems)} problems x ({a.a_runs} A + {a.c_runs} C) = {len(order)} runs; worst case per run "
          f"{worst}; all runs ${total_worst:.2f}")
    if a.cap_usd is None:
        raise SystemExit("STOP: --cap-usd is required (the hard spend cap)")
    print(f"Spend cap: ${a.cap_usd:.2f}" + ("" if total_worst <= a.cap_usd else
          " (below the all-runs worst case: later runs are skipped if actual costs run high)"))
    if a.plan_only:
        return None
    sandbox = Sandbox("subprocess-unsafe") if a.unsafe_subprocess_sandbox else default_sandbox()
    if sandbox.backend == "docker" and not docker_available()[0]:
        raise SystemExit(f"STOP: Docker unavailable ({docker_available()[1]})")

    child_env = dict(os.environ)
    if a.env_file:
        child_env.update(rs.load_env_file(Path(a.env_file)))     # values never printed
    child_env.update({"CRUCIBLE_ROLES": str(roles_path), "CRUCIBLE_SANDBOX": sandbox.backend,
                      "PYTHONIOENCODING": "utf-8"})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(a.out_root).resolve() / f"screen_{'mock_' if a.mock else ''}{stamp}"
    run_dir.mkdir(parents=True)
    config = {"started_utc": datetime.now(timezone.utc).isoformat(), "mock": a.mock, "problems": a.problems,
              "runs_per_problem": {"A": a.a_runs, "C": a.c_runs}, "cap_usd": a.cap_usd, "worst_case_per_run": worst,
              "roles_file": roles_path.name, "roles_sha256": rs.sha(roles_path), "sandbox": sandbox.describe(),
              "keep_rule": KEEP_RULE,
              "screen_cases_sha256": {p: rs.sha(common.problem_dir(p) / "screen_cases.json") for p in a.problems},
              "spec_sha256": {p: rs.sha(common.problem_dir(p) / "SPEC.md") for p in a.problems}}
    (run_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    budget = rs.Budget(a.cap_usd)
    results, not_run = execute(order, run_dir, roles, budget, child_env)
    print(f"[{rs.stamp()}] runs finished; grading in {sandbox.backend}", flush=True)
    rows = grade_all(results, run_dir, sandbox)
    summary = {"config": config, "spent_usd": round(budget.spent, 4), "budget_halted": budget.halted,
               "not_run": sorted(not_run), "problems": summarize(a.problems, rows), "runs": rows}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_dir / "SCREENING.md").write_text(render(summary), encoding="utf-8")
    print(render(summary))
    return run_dir


if __name__ == "__main__":
    main()
