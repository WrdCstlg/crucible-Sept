"""Hidden grader for the SLA pilot. Never shown to any model.

Usage:
  python experiment/grade.py path/to/solution.py [--out result.json]
  python experiment/grade.py --self-test      # oracles must score 38/38; every mutant must be caught

Each case runs in its own subprocess (untrusted code) with a timeout. The candidate receives the
case lines as a plain list (the spec promises only "an iterable of strings") and must return a list
of dicts with exactly the spec's keys and types. Scoring is all-or-nothing: strict pass = every case.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from crucible.sandbox import scrubbed_env  # noqa: E402  (allowlisted env: graded code never sees API keys)

CASE_FILES = [HERE / "sla" / "hand_cases.json", HERE / "sla" / "generated_cases.json"]
MARKER = "@@CRUCIBLE_GRADER_RESULT@@"
KEYS = {"ticket_id", "used_ms", "breached", "status"}
TIMEOUT_SMALL, TIMEOUT_STRESS = 20, 60

CHILD = r'''
import importlib.util, json, sys, traceback
solution_path, case_file, case_id, marker = sys.argv[1:5]
case = next(c for c in json.loads(open(case_file, encoding="utf-8").read()) if c["id"] == case_id)
try:
    spec = importlib.util.spec_from_file_location("solution", solution_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.compute_sla(list(case["lines"]))
    if type(result) is not list:
        out = {"error": f"returned {type(result).__name__}, spec requires a list"}
    else:
        out = {"result": json.loads(json.dumps(result))}
except Exception as e:
    out = {"error": f"{type(e).__name__}: {e}"[:300]}
print(marker + json.dumps(out))
'''


def load_cases():
    cases = []
    for f in CASE_FILES:
        for c in json.loads(f.read_text(encoding="utf-8")):
            c["layer"] = c.get("layer", "hand")
            c["_file"] = str(f)
            cases.append(c)
    return cases


def check(expected, actual):
    """Returns None if actual matches expected exactly (values and types), else a short reason."""
    for i, rec in enumerate(actual):
        if not isinstance(rec, dict) or set(rec) != KEYS:
            return f"record {i} has keys {sorted(rec) if isinstance(rec, dict) else type(rec).__name__}, expected {sorted(KEYS)}"
        if type(rec["ticket_id"]) is not str or type(rec["used_ms"]) is not int or type(rec["breached"]) is not bool \
                or rec["status"] not in ("open", "closed"):
            return f"record {i} has wrong types: {rec}"
    if actual == expected:
        return None
    if len(actual) != len(expected):
        return f"returned {len(actual)} tickets, expected {len(expected)}"
    for exp, act in zip(expected, actual):
        if exp != act:
            return f"expected {exp}, got {act}"
    return "mismatch"


def run_case(solution, case):
    timeout = TIMEOUT_STRESS if case["layer"] == "stress" else TIMEOUT_SMALL
    with tempfile.TemporaryDirectory(prefix="crucible_grade_") as cwd:
        try:
            proc = subprocess.run([sys.executable, "-c", CHILD, str(solution), case["_file"], case["id"], MARKER],
                                  cwd=cwd, capture_output=True, text=True, timeout=timeout,
                                  env=scrubbed_env(deterministic=False))
        except subprocess.TimeoutExpired:
            return f"timeout after {timeout}s"
    lines = [l for l in proc.stdout.splitlines() if l.startswith(MARKER)]
    if not lines:
        tail = (proc.stderr.strip().splitlines() or ["no output"])[-1]
        return f"crashed: {tail[:200]}"
    out = json.loads(lines[-1][len(MARKER):])
    if "error" in out:
        return out["error"]
    return check(case["expected"], out["result"])


def grade(solution, workers=8):
    cases = load_cases()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        reasons = list(pool.map(lambda c: run_case(solution, c), cases))
    rows = [{"id": c["id"], "layer": c["layer"], "title": c.get("title", ""), "pass": r is None, "reason": r}
            for c, r in zip(cases, reasons)]
    by_layer = {}
    for r in rows:
        stats = by_layer.setdefault(r["layer"], [0, 0])
        stats[0] += r["pass"]
        stats[1] += 1
    passed = sum(r["pass"] for r in rows)
    try:
        shown = Path(solution).resolve().relative_to(HERE.parent).as_posix()  # repo-relative: no local paths in results
    except ValueError:
        shown = Path(solution).name
    return {"solution": shown, "strict_pass": passed == len(rows), "passed": passed, "total": len(rows),
            "by_layer": {k: f"{v[0]}/{v[1]}" for k, v in by_layer.items()}, "cases": rows}


# Deliberate bugs injected into a trusted solution. A good test set must catch every one.
MUTANTS = {
    "M01 breach at or over the limit": [('"breached": used > LIMIT_MS', '"breached": used >= LIMIT_MS')],
    "M02 now = last line to arrive": [("now = max(e[0] for e in events)", "now = events[-1][0]")],
    "M03 no sort (arrival order)": [("events.sort(key=lambda e: (e[0], e[1]))", "pass")],
    "M04 RESUME revives a closed ticket": [('elif event == "RESUME" and state == "PAUSED":',
                                           'elif event == "RESUME" and state in ("PAUSED", "CLOSED"):')],
    "M05 OPEN on closed continues like REOPEN": [
        ('if event == "OPEN" and state in ("NOT_OPENED", "CLOSED"):', 'if event == "OPEN" and state == "NOT_OPENED":'),
        ('elif event == "REOPEN" and state == "CLOSED":', 'elif event in ("REOPEN", "OPEN") and state == "CLOSED":')],
    "M06 event names case-insensitive": [("ts, ticket_id, event = (f.strip() for f in fields)",
                                          "ts, ticket_id, event = (f.strip() for f in fields)\n    event = event.upper()")],
    "M07 natural (numeric) ticket sort": [("for ticket_id in sorted(tickets):",
                                           "for ticket_id in sorted(tickets, key=lambda s: (s.rstrip('0123456789'), int(s[len(s.rstrip('0123456789')):] or 0))):")],
    "M08 returns an iterator, not a list": [("    return result\n", "    return iter(result)\n")],
    "M09 decimal timestamps accepted": [('re.compile(r"[0-9]+")', 're.compile(r"[0-9]+(\\.[0-9]+)?")'),
                                        ("return int(ts), ticket_id, event", "return int(float(ts)), ticket_id, event")],
    "M10 paused tickets keep counting to now": [('        if state == "RUNNING":\n            used += now - running_since',
                                                 '        if state in ("RUNNING", "PAUSED"):\n            used += now - running_since')],
    "M11 REOPEN resets the total": [('elif event == "REOPEN" and state == "CLOSED":\n            t[0], t[2] = "RUNNING", ts',
                                     'elif event == "REOPEN" and state == "CLOSED":\n            t[0], t[1], t[2] = "RUNNING", 0, ts')],
}


def self_test():
    ok = True
    for oracle in ["reference.py", "reference_intervals.py"]:
        g = grade(HERE / "sla" / oracle)
        print(f"oracle {oracle:24} {g['passed']}/{g['total']}")
        ok &= g["strict_pass"]
    source = (HERE / "sla" / "reference.py").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="crucible_mutants_") as tmp:
        for name, edits in MUTANTS.items():
            mutated = source
            for old, new in edits:
                if old not in mutated:
                    raise SystemExit(f"mutant {name}: target text not found: {old!r}")
                mutated = mutated.replace(old, new)
            path = Path(tmp) / f"mutant_{name.split()[0]}.py"
            path.write_text(mutated, encoding="utf-8")
            g = grade(path)
            killers = [r["id"] for r in g["cases"] if not r["pass"]]
            caught = not g["strict_pass"]
            ok &= caught
            print(f"{'CAUGHT' if caught else 'MISSED'}  {name:45} failed {len(killers)}/{g['total']} cases: {', '.join(killers[:8])}{' ...' if len(killers) > 8 else ''}")
    print("SELF-TEST PASSED" if ok else "SELF-TEST FAILED")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("solution", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(0 if self_test() else 1)
    result = grade(Path(a.solution).resolve())
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("strict_pass", "passed", "total", "by_layer")}))
