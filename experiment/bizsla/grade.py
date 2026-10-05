"""Hidden grader for experiment/bizsla (Problem 5). Never shown to any model.

    python experiment/bizsla/grade.py path/to/solution.py [--out result.json]
    python experiment/bizsla/grade.py --self-test     # both oracles pass everything; every planted bug is caught
    add --unsafe-subprocess-sandbox to run without Docker (not recommended for model-written code)

Graded code runs in crucible.sandbox (Docker by default: no network, read-only, non-root, memory/pid limits, no
host environment). Non-stress cases run in one sandboxed process per solution (falls back to one process per case if
that process dies or times out). Each stress case runs alone; its compute time must stay within the spec's 10 s.
Scoring is all-or-nothing per case; strict pass = every hidden case.
"""
import argparse
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from crucible.sandbox import Sandbox, default_sandbox, docker_available  # noqa: E402
from generate_cases import stress_lines  # noqa: E402

MARKER = "@@BIZSLA@@"
KEYS = {"ticket_id", "priority", "used_minutes", "breached", "breached_at", "status"}
STRESS_LIMIT_S = 10.0
BATCH_TIMEOUT, CASE_TIMEOUT, STRESS_TIMEOUT = 300, 30, 90

CHILD = r'''
import hashlib, importlib.util, json, sys, time
marker, mode = sys.argv[1], sys.argv[2]
cases = json.loads(open("cases.json", encoding="utf-8").read())
try:
    spec = importlib.util.spec_from_file_location("solution", "solution.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
except BaseException as e:
    print(marker + json.dumps({"id": "*", "error": f"import failed: {type(e).__name__}: {e}"[:300]}), flush=True)
    sys.exit(0)
for case in cases:
    out = {"id": case["id"]}
    try:
        t0 = time.perf_counter()
        result = module.compute_sla(list(case["lines"]))
        out["seconds"] = round(time.perf_counter() - t0, 3)
        if type(result) is not list:
            out["error"] = f"returned {type(result).__name__}, spec requires a list"
        elif mode == "digest":
            out["digest"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            out["count"] = len(result)
            out["head"] = json.loads(json.dumps(result[:2], default=repr))
        else:
            out["result"] = json.loads(json.dumps(result, default=lambda o: {"__unserialisable__": repr(o)}))
    except BaseException as e:
        out["error"] = f"{type(e).__name__}: {e}"[:300]
    print(marker + json.dumps(out), flush=True)
'''


def load_cases():
    hidden = []
    for c in json.loads((HERE / "hand_cases.json").read_text(encoding="utf-8")):
        hidden.append({**c, "layer": "hand"})
    hidden += json.loads((HERE / "generated_cases.json").read_text(encoding="utf-8"))
    public = json.loads((HERE / "public_cases.json").read_text(encoding="utf-8"))
    stress = json.loads((HERE / "stress_cases.json").read_text(encoding="utf-8"))
    return public, hidden, stress


def check(expected, actual):
    """None if actual equals expected exactly (values and types), else a short reason."""
    for i, rec in enumerate(actual):
        if not isinstance(rec, dict) or set(rec) != KEYS:
            return f"record {i} has keys {sorted(rec) if isinstance(rec, dict) else type(rec).__name__}"
        ok = (type(rec["ticket_id"]) is str and rec["priority"] in ("P1", "P2", "P3", "P4")
              and type(rec["used_minutes"]) is int and type(rec["breached"]) is bool
              and (rec["breached_at"] is None or type(rec["breached_at"]) is int)
              and rec["status"] in ("running", "paused", "closed"))
        if not ok:
            return f"record {i} has wrong types: {rec}"
    if actual == expected:
        return None
    if len(actual) != len(expected):
        return f"returned {len(actual)} tickets, expected {len(expected)}"
    for exp, act in zip(expected, actual):
        if exp != act:
            return f"expected {exp}, got {act}"
    return "mismatch"


def _run(sandbox, solution_code, cases, mode, timeout):
    with tempfile.TemporaryDirectory(prefix="crucible_bizsla_") as d:
        (Path(d) / "solution.py").write_text(solution_code, encoding="utf-8")
        (Path(d) / "cases.json").write_text(json.dumps([{"id": c["id"], "lines": c["lines"]} for c in cases]),
                                            encoding="utf-8")
        (Path(d) / "child.py").write_text(CHILD, encoding="utf-8")
        code, out, err, secs = sandbox.run("child.py", Path(d), timeout=timeout, deterministic=False,
                                           args=[MARKER, mode])
    rows = {}
    for line in out.splitlines():
        if line.startswith(MARKER):
            rec = json.loads(line[len(MARKER):])
            rows[rec["id"]] = rec
    return code, rows, err


def _verdict(case, rec):
    if rec is None:
        return "no result (process died or timed out)"
    if "error" in rec:
        return rec["error"]
    if case["layer"] == "stress":
        if rec["seconds"] > STRESS_LIMIT_S:
            return f"too slow: {rec['seconds']}s > {STRESS_LIMIT_S}s"
        if rec["digest"] != case["expected_sha256"]:
            return f"wrong output (got {rec['count']} tickets, expected {case['expected_count']}); first: {rec['head']}"
        return None
    return check(case["expected"], rec["result"])


def grade(solution, sandbox=None, workers=4, include_public=True):
    sandbox = sandbox or default_sandbox()
    code_text = Path(solution).read_text(encoding="utf-8")
    public, hidden, stress = load_cases()
    small = (public if include_public else []) + hidden
    rc, rows, err = _run(sandbox, code_text, small, "full", BATCH_TIMEOUT)
    if "*" in rows:                                    # import failed: every case fails with that reason
        rows = {c["id"]: rows["*"] for c in small}
    elif len(rows) < len(small):                       # died part-way: isolate the remaining cases one by one
        missing = [c for c in small if c["id"] not in rows]
        with ThreadPoolExecutor(workers) as pool:
            for _, r, _ in pool.map(lambda c: _run(sandbox, code_text, [c], "full", CASE_TIMEOUT), missing):
                rows.update(r)
    for s in stress:
        s["lines"] = stress_lines(s)
    with ThreadPoolExecutor(min(workers, len(stress))) as pool:
        for _, r, _ in pool.map(lambda c: _run(sandbox, code_text, [c], "digest", STRESS_TIMEOUT), stress):
            rows.update(r)
    results = []
    for c in small + stress:
        reason = _verdict(c, rows.get(c["id"]))
        results.append({"id": c["id"], "layer": c["layer"], "title": c.get("title", ""), "pass": reason is None,
                        "reason": reason, "seconds": (rows.get(c["id"]) or {}).get("seconds")})
    by_layer = {}
    for r in results:
        s = by_layer.setdefault(r["layer"], [0, 0])
        s[0] += r["pass"]
        s[1] += 1
    scored = [r for r in results if r["layer"] != "public"]
    passed = sum(r["pass"] for r in scored)
    try:
        shown = Path(solution).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        shown = Path(solution).name
    return {"solution": shown, "sandbox": sandbox.backend, "strict_pass": passed == len(scored),
            "passed": passed, "total": len(scored),
            "public_pass": all(r["pass"] for r in results if r["layer"] == "public"),
            "by_layer": {k: f"{v[0]}/{v[1]}" for k, v in by_layer.items()}, "cases": results}


# Deliberate bugs planted in the trusted reference, written from the spec before any model saw it. Each is a
# plausible misreading. A hidden test set worth trusting must catch every one, and (except B21, a performance bug)
# with non-public cases.
MUTANTS = {
    "B01 breach at or over the limit": [("k.used > LIMITS[k.prio]", "k.used >= LIMITS[k.prio]"),
                                        ("k.used + gained > LIMITS[k.prio]", "k.used + gained >= LIMITS[k.prio]"),
                                        ("LIMITS[k.prio] - k.used + 1", "LIMITS[k.prio] - k.used")],
    "B02 17:00 counted as business": [("START, END = 540, 1020", "START, END = 540, 1021")],
    "B03 Saturday is a workday": [("WORKDAYS = 5", "WORKDAYS = 6")],
    "B04 holidays ignored": [("self.hol = sorted(d for d in set(holiday_days) if d % 7 < WORKDAYS)", "self.hol = []")],
    "B05 holiday lines move now": [("now = max(e[0] for e in events)", "now = max([e[0] for e in events] + holidays)")],
    "B06 now = last line to arrive": [("now = max(e[0] for e in events)", "now = events[-1][0]")],
    "B07 no sort (arrival order)": [("events.sort(key=lambda e: e[0])", "pass")],
    "B08 equal minutes processed latest-line-first": [("events.sort(key=lambda e: e[0])",
                                                       "events.reverse(); events.sort(key=lambda e: e[0])")],
    "B09 PRIORITY applies to closed tickets": [('elif event == "PRIORITY" and s in ("RUNNING", "PAUSED"):',
                                                'elif event == "PRIORITY" and s in ("RUNNING", "PAUSED", "CLOSED"):')],
    "B10 REOPEN resets used time": [('elif event == "REOPEN" and s == "CLOSED":\n        k.state = "RUNNING"',
                                     'elif event == "REOPEN" and s == "CLOSED":\n        k.state, k.used = "RUNNING", 0')],
    "B11 OPEN after CLOSE keeps the old breach": [
        ('k.state, k.prio, k.used, k.breached_at, k.opened = "RUNNING", arg, 0, None, True',
         'k.state, k.prio, k.used, k.opened = "RUNNING", arg, 0, True')],
    "B12 breach recomputed from the final priority": [('"breached": k.breached_at is not None',
                                                       '"breached": k.used > LIMITS[k.prio]')],
    "B13 breached_at is the 241st minute, not the minute after": [("        return hi\n", "        return hi - 1\n")],
    "B14 breach checked before that minute's events": [("            if t < m:", "            if t <= m:")],
    "B15 event names case-insensitive": [("minute, tid, event = fields[0], fields[1], fields[2]",
                                          "minute, tid, event = fields[0], fields[1], fields[2].upper()")],
    "B16 paused reported as running": [('"PAUSED": "paused"', '"PAUSED": "running"')],
    "B17 natural (numeric) ticket sort": [("for tid in sorted(tickets):",
                                           "for tid in sorted(tickets, key=lambda s: (s.rstrip('0123456789'), "
                                           "int(s[len(s.rstrip('0123456789')):] or 0))):")],
    "B18 extra fields accepted on 3-field events": [("        if len(fields) != 3:\n            return None\n"
                                                     "        arg = None", "        arg = None")],
    "B19 ticket '*' accepted for ticket events": [('if (event == "HOLIDAY") != (tid == "*"):',
                                                   'if event == "HOLIDAY" and tid != "*":')],
    "B20 P3 limit is two business days (960)": [('"P3": 1440', '"P3": 960')],
    "B21 counts minute by minute (too slow)": [("        return self.g(b) - self.g(a)\n",
                                                "        return sum(1 for x in range(a, b) if self.g(x + 1) > self.g(x))\n")],
    "B22 paused tickets keep counting": [('if k.state == "RUNNING" and m > k.last:',
                                          'if k.state in ("RUNNING", "PAUSED") and m > k.last:')],
}


def planted(name: str) -> str:
    src = (HERE / "reference.py").read_text(encoding="utf-8")
    for old, new in MUTANTS[name]:
        if old not in src:
            raise SystemExit(f"mutant {name}: target text not found: {old!r}")
        src = src.replace(old, new)
    return src


def self_test(sandbox=None) -> bool:
    sandbox = sandbox or default_sandbox()
    ok = True
    for oracle in ("reference.py", "brute_force.py"):
        g = grade(HERE / oracle, sandbox)
        expect_strict = oracle == "reference.py"       # brute force is correct but must FAIL the stress layer
        stress_fail = [r["id"] for r in g["cases"] if r["layer"] == "stress" and not r["pass"]]
        small_fail = [r["id"] for r in g["cases"] if r["layer"] != "stress" and not r["pass"]]
        good = not small_fail and (g["strict_pass"] if expect_strict else bool(stress_fail))
        ok &= good
        print(f"[{'pass' if good else 'FAIL'}] oracle {oracle:15} {g['passed']}/{g['total']} {g['by_layer']}"
              + ("" if expect_strict else f" (stress too slow, as intended: {stress_fail})"))
    with tempfile.TemporaryDirectory(prefix="crucible_bizsla_mut_") as tmp:
        for name in MUTANTS:
            path = Path(tmp) / f"{name.split()[0]}.py"
            path.write_text(planted(name), encoding="utf-8")
            g = grade(path, sandbox)
            hidden_killers = [r["id"] for r in g["cases"] if not r["pass"] and r["layer"] not in ("public", "stress")]
            stress_killers = [r["id"] for r in g["cases"] if not r["pass"] and r["layer"] == "stress"]
            caught = not g["strict_pass"]
            if name.startswith("B21"):
                caught = caught and bool(stress_killers)
            else:
                caught = caught and bool(hidden_killers)
            ok &= caught
            ks = hidden_killers or stress_killers
            print(f"{'CAUGHT' if caught else 'MISSED'}  {name:58} by {len(ks)}: {', '.join(ks[:6])}"
                  f"{' ...' if len(ks) > 6 else ''}")
    print("SELF-TEST PASSED" if ok else "SELF-TEST FAILED")
    return ok


def _sandbox(unsafe: bool) -> Sandbox:
    sb = Sandbox("subprocess-unsafe") if unsafe else default_sandbox()
    if sb.backend == "docker" and not docker_available()[0]:
        raise SystemExit(f"Docker unavailable ({docker_available()[1]}); refusing to grade model-written code "
                         "unisolated. Pass --unsafe-subprocess-sandbox to override.")
    return sb


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("solution", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--unsafe-subprocess-sandbox", action="store_true")
    a = ap.parse_args()
    sb = _sandbox(a.unsafe_subprocess_sandbox)
    if a.self_test:
        sys.exit(0 if self_test(sb) else 1)
    if not a.solution:
        ap.error("solution path required")
    result = grade(Path(a.solution).resolve(), sb)
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("strict_pass", "passed", "total", "public_pass", "by_layer")}))
