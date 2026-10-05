"""Runs the pre-registered study (experiment/PREREGISTRATION.md) on Problem 5 (experiment/bizsla).

    python experiment/study/run_study.py --plan-only --cap-usd 60          # worst-case cost; no model calls
    python experiment/study/run_study.py --cap-usd 60 --env-file "../Project Crucible/.env"
    python experiment/study/run_study.py --mock                             # zero-cost dry run (never evidence)

Refuses to start unless: the bizsla test set matches FROZEN.json; PREREGISTRATION.md exists and (live runs) is
committed with no local edits; every role used has a price; and a spend cap is given.

Spend cap (hard, fail-closed): before launching a run, its worst case (calls x (max input x input price +
max output x output price)) is reserved. A run starts only if actual spend + outstanding reservations + its worst
case fit under the cap. arm_study.py ENFORCES both bounds (it refuses an extra call or an oversized prompt), so the
worst case is a real ceiling, not an estimate. When a run ends its reservation becomes its reported cost; a run that
reports no cost is charged its full worst case. If a provider ever bills more than the worst case (e.g. output beyond
max_tokens), launches stop at once; overshoot is then bounded by the runs already in flight. Runs are interleaved
A, C, B so a cap hit does not starve one arm; runs never started are recorded as "not run (spend cap)" and excluded
from rates.

API keys are read from --env-file into the child processes' environment only; values are never printed or logged.
"""
import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

STUDY = Path(__file__).resolve().parent
EXP = STUDY.parent
ROOT = EXP.parent
BIZ = EXP / "bizsla"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(EXP))
sys.path.insert(0, str(BIZ))
import stats  # noqa: E402


def load_bizgrade():
    """experiment/bizsla/grade.py, loaded by path under a unique name. A bare `import grade` could silently resolve to
    experiment/grade.py (the pilots' grader, same module name) if that was imported first in this process."""
    import importlib.util
    mod = sys.modules.get("bizsla_grade")
    if mod is None:
        spec = importlib.util.spec_from_file_location("bizsla_grade", BIZ / "grade.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["bizsla_grade"] = mod
        spec.loader.exec_module(mod)
    assert Path(mod.__file__).resolve() == (BIZ / "grade.py").resolve()
    return mod

PREREG = EXP / "PREREGISTRATION.md"
CALLS_PER_RUN = {"A": 1, "C": 1, "B": 10}      # B: 2 rounds x (2 generators + 1 QA + 1 synthesis) = 8, bounded at 10
ROLE_OF = {"A": "evaluated", "B": "evaluated", "C": "competitor"}
CONCURRENCY = {"A": 3, "B": 2, "C": 3}
RUN_TIMEOUT_S = 45 * 60
GATE_THRESHOLD = 0.60                            # pre-registered; identical to the calibration set; not tuned


# ── Pre-flight ─────────────────────────────────────────────────────────────
def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def prereg_status(require_committed: bool) -> dict:
    if not PREREG.exists():
        raise SystemExit("STOP: experiment/PREREGISTRATION.md is missing; the analysis must be fixed before any run")
    info = {"sha256": sha(PREREG)}
    if require_committed:
        rel = PREREG.relative_to(ROOT).as_posix()
        log = subprocess.run(["git", "log", "-1", "--format=%H %cI", "--", rel], cwd=ROOT, capture_output=True,
                             text=True)
        dirty = subprocess.run(["git", "status", "--porcelain", "--", rel], cwd=ROOT, capture_output=True, text=True)
        if not log.stdout.strip() or dirty.stdout.strip():
            raise SystemExit("STOP: PREREGISTRATION.md must be committed (and unmodified) before a live run")
        info["commit"], info["committed_at"] = log.stdout.strip().split(" ", 1)
    return info


def worst_case_run(arm: str, roles: dict) -> float:
    cfg = roles[ROLE_OF[arm]]
    price = cfg.get("price_per_mtok")
    if not price:
        raise SystemExit(f"STOP: role '{ROLE_OF[arm]}' ({cfg['model']}) has no price_per_mtok; the spend cap cannot "
                         "be enforced without it. Fill it in the roles file (and confirm it) first.")
    per_call = (cfg.get("max_input_tokens_per_call", 60000) * price["input"]
                + cfg["settings"]["max_tokens"] * price["output"]) / 1e6
    return round(CALLS_PER_RUN[arm] * per_call, 4)


def schedule(n: dict) -> list:
    """Interleaved A, C, B order: a spend-cap stop truncates every arm roughly equally."""
    order, i = [], 1
    while any(i <= n[a] for a in "ACB"):
        for a in "ACB":
            if i <= n[a]:
                order.append(f"{a}{i}")
        i += 1
    return order


def load_env_file(path: Path) -> dict:
    """KEY=VALUE lines -> dict. Values are never printed."""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


class Budget:
    def __init__(self, cap: float):
        self.cap, self.spent, self.reserved, self.halted = cap, 0.0, 0.0, None
        self.lock = threading.Lock()

    def reserve(self, worst: float) -> bool:
        with self.lock:
            if self.halted or self.spent + self.reserved + worst > self.cap + 1e-9:
                return False
            self.reserved += worst
            return True

    def settle(self, worst: float, actual):
        with self.lock:
            self.reserved -= worst
            if actual is None:
                self.spent += worst                      # unknown cost: charge the ceiling
            else:
                self.spent += actual
                if actual > worst + 1e-9:
                    self.halted = f"a run cost ${actual:.4f}, above its reserved worst case ${worst:.4f}"


# ── Execution ──────────────────────────────────────────────────────────────
def run_one(name: str, out: Path, env: dict) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with open(out / "log.txt", "w", encoding="utf-8") as log:
        kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        p = subprocess.Popen([sys.executable, "-u", str(STUDY / "arm_study.py"), name[0], "--out", str(out)],
                             cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT, env=env, **kw)
        try:
            p.wait(timeout=RUN_TIMEOUT_S)
            status = "done" if p.returncode == 0 else "error"
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
            else:
                os.killpg(p.pid, signal.SIGKILL)
            p.wait()
            status = "timeout"
    meta_path = out / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {"error": "no meta"}
    if status == "timeout":
        meta.setdefault("error", f"stopped after {RUN_TIMEOUT_S}s")
    return {"run": name, "arm": name[0], "status": status, "seconds": round(time.time() - t0, 1), "meta": meta}


def execute(order, run_dir, roles, budget, child_env):
    sems = {a: threading.Semaphore(CONCURRENCY[a]) for a in "ABC"}
    results, skipped, lock = {}, [], threading.Lock()

    def task(name):
        arm = name[0]
        worst = worst_case_run(arm, roles)
        with sems[arm]:
            if not budget.reserve(worst):
                with lock:
                    skipped.append(name)
                print(f"[{stamp()}] {name} not run (spend cap ${budget.cap:.2f}; spent ${budget.spent:.4f})",
                      flush=True)
                return
            env = {**child_env, "CRUCIBLE_MOCK_SEED": name}
            print(f"[{stamp()}] start {name} (reserved ${worst:.4f})", flush=True)
            r = run_one(name, run_dir / name, env)
            cost = r["meta"].get("cost_usd")
            budget.settle(worst, cost)
            with lock:
                results[name] = r
            print(f"[{stamp()}] end {name}: {r['status']} cost={cost} spent=${budget.spent:.4f}", flush=True)

    with ThreadPoolExecutor(sum(CONCURRENCY.values())) as pool:
        list(pool.map(task, order))
    return results, skipped


def stamp():
    return datetime.now().strftime("%H:%M:%S")


# ── Grading and the out-of-sample gate check ───────────────────────────────
def is_harness_error(r: dict) -> bool:
    """Pre-registered exclusion rule. Excluded (not counted): the harness itself crashed (exception traceback, or no
    meta.json). Counted as FAILURES: timeouts, refusals, truncated output, unparseable code, and BudgetGuard stops
    (model_attributable). Harness errors are reported per arm; they are never silently dropped."""
    meta = r["meta"]
    if r["status"] == "timeout" or meta.get("model_attributable"):
        return False
    return bool(meta.get("traceback")) or meta.get("error") == "no meta"


def grade_all(results, sandbox):
    bizgrade = load_bizgrade()
    rows, b_candidates = [], []
    for name in sorted(results):
        r = results[name]
        meta = r["meta"]
        sol = r["dir"] / "solution.py"
        g = bizgrade.grade(sol, sandbox) if sol.exists() else None
        if g:
            (r["dir"] / "grade.json").write_text(json.dumps(g, indent=2), encoding="utf-8")
        harness_error = is_harness_error(r)
        rows.append({"run": name, "arm": r["arm"], "status": r["status"], "error": meta.get("error"),
                     "harness_error": harness_error, "cost_usd": meta.get("cost_usd"), "seconds": r["seconds"],
                     "strict_pass": bool(g and g["strict_pass"]), "cases_passed": g["passed"] if g else 0,
                     "cases_total": g["total"] if g else None, "by_layer": g["by_layer"] if g else None,
                     "first_failure": next((f"{c['id']}: {c['reason']}" for c in g["cases"] if not c["pass"]), None)
                     if g else None})
        if r["arm"] == "B":
            verdicts = meta.get("crucible_verdicts", {})
            for cand in sorted((r["dir"] / "candidates").glob("round*_branch_*.py")):
                cg = bizgrade.grade(cand, sandbox)
                b_candidates.append({"run": name, "candidate": cand.stem, "crucible_verdict": verdicts.get(cand.stem),
                                     "hidden_pass": cg["strict_pass"], "cases_passed": cg["passed"]})
    return rows, b_candidates


def gate_out_of_sample(results, sandbox):
    """Pre-registered H4: every arm-B AI-written suite through the mutation gate (thresholds 0.60, unchanged from the
    calibration set) vs the independent yardstick: the planted bugs in experiment/bizsla/grade.py (minus B21, a
    performance bug no functional suite is expected to catch)."""
    from crucible.mutation import MutationSlaughterGate
    bizgrade = load_bizgrade()
    hidden = [c for c in json.loads((BIZ / "hand_cases.json").read_text(encoding="utf-8"))]
    hidden += json.loads((BIZ / "generated_cases.json").read_text(encoding="utf-8"))
    corpus = [c["lines"] for c in hidden if c.get("layer") != "medium"]
    gate = MutationSlaughterGate(sandbox.run, threshold=GATE_THRESHOLD, max_mutants=40)
    bugs = [n for n in bizgrade.MUTANTS if not n.startswith("B21")]
    rows = []
    for name in sorted(results):
        if results[name]["arm"] != "B":
            continue
        for suite in sorted((results[name]["dir"] / "candidates").glob("round*_crucible_tests.py")):
            print(f"[{stamp()}] H4 gate: {name}/{suite.stem}", flush=True)
            r = gate.evaluate_suite(suite, BIZ / "reference.py", equivalence_corpus=corpus, entrypoint="compute_sla")
            caught = 0
            if r.baseline_passed:
                for b in bugs:
                    with tempfile.TemporaryDirectory(prefix="crucible_h4_") as d:
                        (Path(d) / "solution.py").write_text(bizgrade.planted(b), encoding="utf-8")
                        (Path(d) / "arena_test.py").write_text(suite.read_text(encoding="utf-8"), encoding="utf-8")
                        caught += sandbox.run("arena_test.py", Path(d), timeout=120)[0] != 0
            strong = bool(r.baseline_passed) and caught / len(bugs) >= GATE_THRESHOLD
            rows.append({"suite": f"{name}/{suite.stem}", "baseline_passes_reference": r.baseline_passed,
                         "gate_admits": r.passed_gate, "code": [r.killed_mutants, r.total_mutants],
                         "output": [r.output_killed, r.output_total], "input": [r.input_killed, r.input_total],
                         "planted_bugs_caught": [caught, len(bugs)], "independently_strong": strong,
                         "agree": r.passed_gate == strong})
    return rows


# ── Pre-registered analysis ────────────────────────────────────────────────
def analyze(rows, b_candidates, gate_rows, n_planned):
    arms = {}
    for a in "ABC":
        valid = [r for r in rows if r["arm"] == a and not r["harness_error"]]
        k = sum(r["strict_pass"] for r in valid)
        arms[a] = {"planned": n_planned[a], "valid": len(valid),
                   "harness_errors": sum(1 for r in rows if r["arm"] == a and r["harness_error"]),
                   "strict_passes": k, "rate": round(k / len(valid), 3) if valid else None,
                   "wilson95": [round(x, 3) for x in stats.wilson(k, len(valid))] if valid else None,
                   "mean_cases_passed": round(sum(r["cases_passed"] for r in valid) / len(valid), 1) if valid else None,
                   "cost_usd": round(sum(r["cost_usd"] or 0 for r in rows if r["arm"] == a), 4)}

    def compare(x, y):
        X, Y = arms[x], arms[y]
        if not X["valid"] or not Y["valid"]:
            return {"p_two_sided": None, "verdict": "undefined (an arm has no valid runs)"}
        p = stats.fisher_exact(X["strict_passes"], X["valid"] - X["strict_passes"],
                               Y["strict_passes"], Y["valid"] - Y["strict_passes"])
        gap = stats.min_detectable_gap(max(min(Y["rate"], 0.95), 0.05), X["valid"], Y["valid"])
        if p < 0.05:
            verdict = f"{x} {'higher' if X['rate'] > Y['rate'] else 'lower'} than {y} (p = {p:.4f})"
        else:
            verdict = (f"no detectable difference (p = {p:.3f}); with these n, gaps under ~{gap:.0%} could not be "
                       "detected at 80% power")
        return {"p_two_sided": round(p, 5), "rate_difference": round(X["rate"] - Y["rate"], 3),
                "min_detectable_gap_80pct": gap, "verdict": verdict}

    promoted = [c for c in b_candidates if c["crucible_verdict"] == "PASS"]
    h3 = {"candidates": len(b_candidates), "promoted": len(promoted),
          "promoted_but_fail_hidden": sum(1 for c in promoted if not c["hidden_pass"]),
          "rejected_but_pass_hidden": sum(1 for c in b_candidates
                                          if c["crucible_verdict"] not in (None, "PASS") and c["hidden_pass"])}
    if promoted:
        h3["false_promotion_wilson95"] = [round(x, 3) for x in stats.wilson(h3["promoted_but_fail_hidden"],
                                                                             len(promoted))]
    adm = [g for g in gate_rows if g["gate_admits"]]
    agree = sum(g["agree"] for g in gate_rows)
    h4 = {"suites": len(gate_rows), "admitted": len(adm),
          "false_security": sum(1 for g in adm if not g["independently_strong"]),
          "lost_signal": sum(1 for g in gate_rows if not g["gate_admits"] and g["independently_strong"]),
          "agreement": f"{agree}/{len(gate_rows)}",
          "agreement_wilson95": [round(x, 3) for x in stats.wilson(agree, len(gate_rows))] if gate_rows else None}
    h4["criterion_met"] = bool(gate_rows) and h4["false_security"] == 0 and agree / len(gate_rows) >= 0.8
    compromised = [a for a in "ABC" if n_planned[a] and arms[a]["harness_errors"] > 0.10 * n_planned[a]]
    return {"arms": arms, "H1_B_vs_C": compare("B", "C"), "H2_B_vs_A": compare("B", "A"),
            "H3_crucible_vs_hidden": h3, "H4_gate_out_of_sample": h4,
            "integrity": {"harness_error_limit": "10% of planned runs per arm", "arms_over_limit": compromised,
                          "compromised": bool(compromised)}}


def render(summary) -> str:
    c = summary["config"]
    L = [f"# Study results{' (MOCK DRY RUN: NOT EVIDENCE)' if c['mock'] else ''}", "",
         f"Pre-registration sha256 `{c['prereg']['sha256'][:12]}`"
         + (f", commit `{c['prereg'].get('commit', '')[:10]}`" if c["prereg"].get("commit") else "")
         + f". Problem: `experiment/bizsla` ({c['hidden_cases']} hidden cases, all-or-nothing). "
           f"Spend cap ${c['cap_usd']:.2f}; spent ${summary['spent_usd']:.4f}.", "",
         "| Arm | Planned | Valid (harness errors) | Strict passes | Rate (95% Wilson) | Mean cases | Cost |",
         "|---|---|---|---|---|---|---|"]
    for a, v in summary["analysis"]["arms"].items():
        ci = f"{v['rate']:.0%} ({v['wilson95'][0]:.0%}-{v['wilson95'][1]:.0%})" if v["rate"] is not None else "-"
        L.append(f"| {c['labels'][a]} | {v['planned']} | {v['valid']} ({v['harness_errors']}) | {v['strict_passes']} "
                 f"| {ci} | {v['mean_cases_passed']} | ${v['cost_usd']:.2f} |")
    an = summary["analysis"]
    if an["integrity"]["compromised"]:
        L += ["", f"> **COMPROMISED:** harness errors exceed 10% of planned runs in arm(s) "
                  f"{', '.join(an['integrity']['arms_over_limit'])}; H1/H2 are reported but must not be relied on."]
    L += ["", f"**H1 (primary) B vs C:** {an['H1_B_vs_C']['verdict']}",
          f"**H2 B vs A:** {an['H2_B_vs_A']['verdict']}",
          f"**H3 Crucible verdict vs hidden grader:** {an['H3_crucible_vs_hidden']}",
          f"**H4 mutation gate out of sample:** {an['H4_gate_out_of_sample']}"]
    if summary["not_run"]:
        L.append(f"\nNot run (spend cap): {', '.join(summary['not_run'])}")
    if summary.get("budget_halted"):
        L.append(f"\nLaunches halted: {summary['budget_halted']}")
    L += ["", "## Runs", "", "| Run | Status | Cases | Strict | First failure |", "|---|---|---|---|---|"]
    for r in summary["runs"]:
        L.append(f"| {r['run']} | {r['status']}{' (' + str(r['error'])[:60] + ')' if r['error'] else ''} | "
                 f"{r['cases_passed']}/{r['cases_total'] or '-'} | {'PASS' if r['strict_pass'] else 'FAIL'} | "
                 f"{(r['first_failure'] or '')[:120]} |")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a-runs", type=int, default=30)
    ap.add_argument("--b-runs", type=int, default=20)
    ap.add_argument("--c-runs", type=int, default=30)
    ap.add_argument("--cap-usd", type=float)
    ap.add_argument("--roles", default=str(STUDY / "roles_study.json"))
    ap.add_argument("--env-file")
    ap.add_argument("--mock", action="store_true", help="zero-cost dry run with roles_mock.json (never evidence)")
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--label", default="")
    ap.add_argument("--out-root", default=str(EXP / "runs"), help="where the study_* folder is created")
    ap.add_argument("--unsafe-subprocess-sandbox", action="store_true", help="mock runs only")
    a = ap.parse_args()

    from crucible.sandbox import Sandbox, default_sandbox, docker_available
    import generate_cases
    if not generate_cases.check():
        raise SystemExit("STOP: the bizsla test set changed after the freeze; refusing to run")
    roles_path = STUDY / "roles_mock.json" if a.mock else Path(a.roles).resolve()
    roles = json.loads(roles_path.read_text(encoding="utf-8"))
    live = any(r["provider"] != "mock" for r in roles.values())
    if a.mock and live:
        raise SystemExit("STOP: --mock with a non-mock roles file")
    if a.unsafe_subprocess_sandbox and live:
        raise SystemExit("STOP: live model output is only ever executed in the Docker sandbox")
    prereg = prereg_status(require_committed=live)
    n = {"A": a.a_runs, "B": a.b_runs, "C": a.c_runs}
    order = schedule(n)
    worst = {arm: worst_case_run(arm, roles) for arm in "ABC" if n[arm]}
    total_worst = round(sum(worst[x[0]] for x in order), 2)
    print(f"Worst case per run: {worst}; all {len(order)} runs: ${total_worst:.2f}")
    if a.cap_usd is None:
        raise SystemExit("STOP: --cap-usd is required (the hard spend cap)")
    print(f"Spend cap: ${a.cap_usd:.2f}" + ("" if total_worst <= a.cap_usd else
          " (below the all-runs worst case: later runs will be skipped if actual costs run high)"))
    if a.plan_only:
        return
    sandbox = Sandbox("subprocess-unsafe") if a.unsafe_subprocess_sandbox else default_sandbox()
    if sandbox.backend == "docker" and not docker_available()[0]:
        raise SystemExit(f"STOP: Docker unavailable ({docker_available()[1]})")

    child_env = {k: v for k, v in os.environ.items()}
    if a.env_file:
        child_env.update(load_env_file(Path(a.env_file)))     # values never printed
    child_env.update({"PILOT_SPEC": str(BIZ / "SPEC.md"), "CRUCIBLE_ROLES": str(roles_path),
                      "CRUCIBLE_SANDBOX": sandbox.backend, "PYTHONIOENCODING": "utf-8"})
    label = ("mock_" if a.mock else "") + (f"{a.label}_" if a.label else "")
    run_dir = Path(a.out_root).resolve() / f"study_{label}{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir.mkdir(parents=True)
    bizgrade = load_bizgrade()
    public, hidden, stress = bizgrade.load_cases()
    labels = {"A": f"A: {roles['evaluated']['model']}, 1 call", "B": f"B: {roles['evaluated']['model']} in Crucible",
              "C": f"C: {roles['competitor']['model']}, 1 call"}
    config = {"started_utc": datetime.now(timezone.utc).isoformat(), "mock": a.mock, "prereg": prereg,
              "roles_file": (roles_path.relative_to(ROOT).as_posix() if roles_path.is_relative_to(ROOT)
                             else str(roles_path)), "roles_sha256": sha(roles_path),
              "freeze_sha256": json.loads((BIZ / "FROZEN.json").read_text(encoding="utf-8"))["sha256"],
              "runs_planned": n, "cap_usd": a.cap_usd, "worst_case_per_run": worst, "sandbox": sandbox.describe(),
              "hidden_cases": len(hidden) + len(stress), "labels": labels, "gate_threshold": GATE_THRESHOLD}
    (run_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    budget = Budget(a.cap_usd)
    results, not_run = execute(order, run_dir, roles, budget, child_env)
    for name, r in results.items():
        r["dir"] = run_dir / name
    print(f"[{stamp()}] runs finished; grading in {sandbox.backend}", flush=True)
    rows, b_candidates = grade_all(results, sandbox)
    gate_rows = gate_out_of_sample(results, sandbox)
    analysis = analyze(rows, b_candidates, gate_rows, n)
    summary = {"config": config, "spent_usd": round(budget.spent, 4), "budget_halted": budget.halted,
               "not_run": sorted(not_run), "analysis": analysis, "runs": rows, "b_candidates": b_candidates,
               "gate_out_of_sample": gate_rows}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_dir / "RESULTS.md").write_text(render(summary), encoding="utf-8")
    print(render(summary))


if __name__ == "__main__":
    main()
