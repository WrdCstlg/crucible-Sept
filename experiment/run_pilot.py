"""Runs the SLA pilot and grades it.

  python experiment/run_pilot.py [--minutes 50] [--a-runs 5] [--b-runs 2] [--c-runs 5]

1. Verifies the frozen test set (FROZEN.json hashes) before anything runs.
2. Launches arm B runs in parallel, arm A runs one after another (Gemini concurrency stays at 3),
   and arm C runs in parallel. Anything still running at the deadline is stopped and recorded.
3. Grades every arm's solution.py and every arm-B candidate with the hidden grader.
4. Writes summary.json and summary.md into experiment/runs/pilot_<UTC time>/.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import grade  # noqa: E402

ARMS_SCRIPT = HERE / "arms.py"  # replaced by rig/arm.py when --rig is given
LABELS = {"A": "A: Gemini Flash, 1 call", "B": "B: Gemini Flash in Crucible", "C": "C: Claude Opus 5.5, 1 call"}


def verify_freeze():
    frozen = json.loads((HERE / "sla" / "FROZEN.json").read_text(encoding="utf-8"))
    for name, expected in frozen["sha256"].items():
        if hashlib.sha256((HERE / "sla" / name).read_bytes()).hexdigest() != expected:
            sys.exit(f"STOP: {name} changed after the freeze; refusing to run")
    return frozen


class Run:
    def __init__(self, arm, n, pilot_dir):
        self.arm, self.name = arm, f"{arm}{n}"
        self.out = pilot_dir / self.name
        self.proc = self.log = None
        self.started = self.ended = None
        self.status = "pending"

    def start(self):
        self.out.mkdir(parents=True, exist_ok=True)
        self.log = open(self.out / "log.txt", "w", encoding="utf-8")
        self.proc = subprocess.Popen([sys.executable, "-u", str(ARMS_SCRIPT), self.arm, "--out", str(self.out)],
                                     cwd=str(ROOT), stdout=self.log, stderr=subprocess.STDOUT)
        self.started, self.status = time.time(), "running"
        print(f"[{stamp()}] started {self.name}", flush=True)

    def poll(self):
        if self.status == "running" and self.proc.poll() is not None:
            self.ended, self.status = time.time(), "done" if self.proc.returncode == 0 else "error"
            self.log.close()
            print(f"[{stamp()}] {self.name} finished ({self.status}) in {self.ended - self.started:.0f}s", flush=True)

    def stop(self):
        if self.status == "running":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True)
            self.proc.wait()
            self.log.close()
            self.ended, self.status = time.time(), "stopped at deadline"
            meta = self.out / "meta.json"
            if not meta.exists():
                meta.write_text(json.dumps({"arm": self.arm, "error": "stopped at deadline"}), encoding="utf-8")
            print(f"[{stamp()}] {self.name} stopped at deadline", flush=True)


def stamp():
    return datetime.now().strftime("%H:%M:%S")


def execute(args, pilot_dir):
    deadline = time.time() + args.minutes * 60
    b_runs = [Run("B", i, pilot_dir) for i in range(1, args.b_runs + 1)]
    c_runs = [Run("C", i, pilot_dir) for i in range(1, args.c_runs + 1)]
    a_queue = [Run("A", i, pilot_dir) for i in range(1, args.a_runs + 1)]
    for r in b_runs + c_runs:
        r.start()
    a_current = None
    a_done = []
    while True:
        for r in b_runs + c_runs + ([a_current] if a_current else []):
            r.poll()
        if a_current and a_current.status != "running":
            a_done.append(a_current)
            a_current = None
        if a_current is None and a_queue and deadline - time.time() > 6 * 60:
            a_current = a_queue.pop(0)
            a_current.start()
        running = [r for r in b_runs + c_runs + ([a_current] if a_current else []) if r.status == "running"]
        if not running and (not a_queue or deadline - time.time() <= 6 * 60):
            break
        if time.time() > deadline:
            for r in running:
                r.stop()
            if a_current:
                a_done.append(a_current)
            break
        time.sleep(5)
    skipped = [r.name for r in a_queue]
    return b_runs + c_runs + a_done, skipped


def summarize(runs, skipped, pilot_dir, config):
    rows, b_candidates = [], []
    for r in sorted(runs, key=lambda r: r.name):
        meta_path = r.out / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {"error": "no meta"}
        sol = r.out / "solution.py"
        g = grade.grade(sol) if sol.exists() else None
        if g:
            (r.out / "grade.json").write_text(json.dumps(g, indent=2), encoding="utf-8")
        # An exception inside arms.py (our bug, SDK crash, network) is not a model outcome: excluded from pass rates.
        # A refusal, a deadline stop, or Crucible shipping nothing IS an outcome and counts as a failure.
        harness_error = bool(meta.get("traceback")) or meta.get("error") == "no meta"
        rows.append({"run": r.name, "arm": r.arm, "status": r.status, "seconds": meta.get("seconds"),
                     "error": meta.get("error"), "harness_error": harness_error, "cost_usd": meta.get("cost_usd"),
                     "tokens": token_total(meta), "agent_calls": meta.get("agent_calls"),
                     "graded": g is not None, "strict_pass": bool(g and g["strict_pass"]),
                     "cases_passed": g["passed"] if g else 0, "cases_total": g["total"] if g else None,
                     "by_layer": g["by_layer"] if g else None,
                     "failed_cases": [c["id"] for c in g["cases"] if not c["pass"]] if g else None,
                     "first_failure": next((f"{c['id']}: {c['reason']}" for c in g["cases"] if not c["pass"]), None) if g else None,
                     "crucible_status": meta.get("crucible_status"), "rounds_run": meta.get("rounds_run")})
        if r.arm == "B":
            verdicts = meta.get("crucible_verdicts", {})
            for cand in sorted((r.out / "candidates").glob("round*_branch_*.py")):
                cg = grade.grade(cand)
                b_candidates.append({"run": r.name, "candidate": cand.stem, "crucible_verdict": verdicts.get(cand.stem),
                                     "hidden_pass": cg["strict_pass"], "cases_passed": cg["passed"], "cases_total": cg["total"]})

    arms = {}
    for arm in ("A", "B", "C"):
        everything = [x for x in rows if x["arm"] == arm]
        rs = [x for x in everything if not x["harness_error"]]
        passes = sum(x["strict_pass"] for x in rs)
        fails = Counter(cid for x in rs for cid in (x["failed_cases"] or []))
        arms[arm] = {"runs": len(everything), "valid_runs": len(rs), "harness_errors": len(everything) - len(rs),
                     "strict_passes": passes, "pass_rate": round(passes / len(rs), 3) if rs else None,
                     "mean_cases_passed": round(sum(x["cases_passed"] for x in rs) / len(rs), 1) if rs else None,
                     "mean_seconds": round(sum(x["seconds"] or 0 for x in rs) / len(rs), 1) if rs else None,
                     "total_tokens": sum(x["tokens"] or 0 for x in rs),
                     "cost_usd": round(sum(x["cost_usd"] or 0 for x in everything), 4),
                     "most_failed_cases": fails.most_common(8)}
    a, b, c = (arms[k]["pass_rate"] for k in "ABC")
    gap = round((b - a) / (c - a), 3) if None not in (a, b, c) and c != a else None
    confusion = Counter((x["crucible_verdict"] == "PASS", x["hidden_pass"])
                        for x in b_candidates if x["crucible_verdict"] is not None)
    h3 = {"crucible_pass_hidden_pass": confusion[(True, True)], "false_pass": confusion[(True, False)],
          "false_fail": confusion[(False, True)], "crucible_fail_hidden_fail": confusion[(False, False)]}
    summary = {"config": config, "skipped_runs": skipped, "arms": arms, "h1_gap_closed": gap,
               "h3_crucible_vs_hidden": h3, "runs": rows, "b_candidates": b_candidates}
    (pilot_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (pilot_dir / "summary.md").write_text(render(summary), encoding="utf-8")
    return summary


def token_total(meta):
    def one(u):
        if not isinstance(u, dict):
            return 0
        return u.get("total_token_count") or ((u.get("input_tokens") or 0) + (u.get("output_tokens") or 0))
    if isinstance(meta.get("usage"), dict):
        return one(meta["usage"]) or None
    if "calls" in meta:
        return sum(one(c.get("usage")) for c in meta["calls"]) or None
    return None


def render(s):
    labels = s["config"].get("labels", LABELS)
    out = [f"# SLA pilot results\n", f"Spec given to all arms: `{s['config'].get('spec', 'SPEC.md')}`. "
           f"Test set frozen at {s['config']['frozen_at']}; {s['config']['cases']} hidden cases, all-or-nothing scoring.\n",
           "| Arm | Valid runs (harness errors) | Strict passes | Mean cases passed | Mean time (s) | Tokens | Claude cost |",
           "|---|---|---|---|---|---|---|"]
    for k, v in s["arms"].items():
        out.append(f"| {labels[k]} | {v['valid_runs']} ({v['harness_errors']}) | {v['strict_passes']} | {v['mean_cases_passed']} | "
                   f"{v['mean_seconds']} | {v['total_tokens'] or '-'} | {'$%.2f' % v['cost_usd'] if k == 'C' else '-'} |")
    out.append(f"\nH1 gap closed (B-A)/(C-A): {s['h1_gap_closed'] if s['h1_gap_closed'] is not None else 'undefined (an arm has no valid runs, or A and C tie)'}")
    out.append(f"\nH3 Crucible verdict vs hidden grader (all arm-B candidates): {s['h3_crucible_vs_hidden']}")
    if s["skipped_runs"]:
        out.append(f"\nSkipped for time: {', '.join(s['skipped_runs'])}")
    out.append("\n## Runs\n\n| Run | Status | Cases | Strict | First failure |\n|---|---|---|---|---|")
    for r in s["runs"]:
        out.append(f"| {r['run']} | {r['status']}{' (' + r['error'] + ')' if r['error'] else ''} | "
                   f"{r['cases_passed']}/{r['cases_total'] or '-'} | {'PASS' if r['strict_pass'] else 'FAIL'} | {r['first_failure'] or ''} |")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=50)
    ap.add_argument("--a-runs", type=int, default=5)
    ap.add_argument("--b-runs", type=int, default=2)
    ap.add_argument("--c-runs", type=int, default=5)
    ap.add_argument("--spec", default=str(HERE / "sla" / "SPEC.md"), help="spec text given to every arm")
    ap.add_argument("--label", default="", help="suffix for the run folder, e.g. ablation_v0")
    ap.add_argument("--rig", action="store_true", help="run arms through experiment/rig (provider-agnostic roles.json)")
    args = ap.parse_args()
    global ARMS_SCRIPT
    frozen = verify_freeze()
    rig = None
    if args.rig:
        ARMS_SCRIPT = HERE / "rig" / "arm.py"
        roles_file = HERE / "rig" / "roles.json"
        roles = json.loads(roles_file.read_text(encoding="utf-8"))
        rig = {"roles": roles, "roles_sha256": hashlib.sha256(roles_file.read_bytes()).hexdigest()}
        LABELS.update({"A": f"A: {roles['evaluated']['model']}, 1 call",
                       "B": f"B: {roles['evaluated']['model']} in Crucible",
                       "C": f"C: {roles['competitor']['model']}, 1 call"})
    spec_path = Path(args.spec).resolve()
    os.environ["PILOT_SPEC"] = str(spec_path)  # inherited by every arm process
    label = f"{args.label}_" if args.label else ""
    pilot_dir = HERE / "runs" / f"pilot_{label}{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    pilot_dir.mkdir(parents=True)
    cases = len(grade.load_cases())
    config = {"started_utc": datetime.now(timezone.utc).isoformat(), "frozen_at": frozen["frozen_at"], "cases": cases,
              "freeze_sha256": frozen["sha256"], "minutes": args.minutes,
              "spec": spec_path.name, "spec_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(),
              "runs": {"A": args.a_runs, "B": args.b_runs, "C": args.c_runs},
              "runner": "rig" if rig else "antigravity", "rig": rig, "labels": dict(LABELS)}
    print(f"[{stamp()}] pilot dir: {pilot_dir}", flush=True)
    runs, skipped = execute(args, pilot_dir)
    print(f"[{stamp()}] all runs finished; grading", flush=True)
    s = summarize(runs, skipped, pilot_dir, config)
    print(render(s), flush=True)


if __name__ == "__main__":
    main()
