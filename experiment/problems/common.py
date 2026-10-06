"""Shared machinery for the candidate problems in experiment/problems/<name>/.

    python experiment/problems/common.py build <name>        compute expected outputs -> screen_cases.json
    python experiment/problems/common.py grade <name> SOL    grade a solution in the sandbox
    python experiment/problems/common.py self-test <name>    reference passes everything; every planted bug is caught

Each problem folder holds:
    problem.json   {"entry": "<function name>", "title": "...", "stress_limit_s": 10}
    SPEC.md        the only text any model sees
    reference.py   trusted implementation (stdlib only)
    cases.py       public() / hidden() / stress() case lists, and stress_args(case) (stdlib only: it is copied into
                   the sandbox so large stress inputs are generated there instead of being stored)
    mutants.py     MUTANTS = {name: [(old, new), ...]}: plausible misreadings planted in reference.py

Strict comparison: a result must contain only dict (str keys), list, str, int, float, bool and None. It is compared as
canonical JSON (sorted keys), so 1 and 1.0 differ, True and 1 differ, a tuple or generator is rejected, and dict key
order does not matter. Untrusted code runs only in crucible.sandbox (Docker by default).

These are SCREENING artifacts: one oracle (reference.py), checked against hand-written expected outputs for the
public examples and against planted bugs. A problem kept after screening gets a second oracle, hand cases and a
freeze before any study uses it.
"""
import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
from crucible.sandbox import default_sandbox  # noqa: E402

MARKER = "@@PROBLEM@@"
BATCH_TIMEOUT, CASE_TIMEOUT, STRESS_TIMEOUT = 300, 30, 120

CANON = r'''
import json, math
ALLOWED = (str, int, float, bool, type(None))
def _check(x, path):
    t = type(x)
    if t is dict:
        for k, v in x.items():
            if type(k) is not str:
                raise TypeError(f"{path}: dict key {k!r} is {type(k).__name__}, must be str")
            _check(v, f"{path}.{k}")
    elif t is list:
        for i, v in enumerate(x):
            _check(v, f"{path}[{i}]")
    elif t is float:
        if not math.isfinite(x):
            raise TypeError(f"{path}: non-finite float {x!r}")
    elif t not in ALLOWED:
        raise TypeError(f"{path}: {t.__name__} is not allowed (use dict, list, str, int, float, bool or None)")
def canon(x):
    _check(x, "result")
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
'''

CHILD = CANON + r'''
import copy, hashlib, importlib.util, sys, time
marker, mode, entry = sys.argv[1], sys.argv[2], sys.argv[3]
cases = json.loads(open("cases.json", encoding="utf-8").read())
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
try:
    module = load("solution", "solution.py")
    fn = getattr(module, entry)
except BaseException as e:
    print(marker + json.dumps({"id": "*", "error": f"import failed: {type(e).__name__}: {e}"[:300]}), flush=True)
    sys.exit(0)
gen = load("casegen", "casegen.py") if mode == "stress" else None
for case in cases:
    out = {"id": case["id"]}
    try:
        args = gen.stress_args(case) if gen else case["args"]
        t0 = time.perf_counter()
        result = fn(*args)
        out["seconds"] = round(time.perf_counter() - t0, 3)
        text = canon(result)
        if mode == "stress":
            out["digest"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
            out["head"] = text[:200]
        else:
            out["canon"] = text
    except BaseException as e:
        out["error"] = f"{type(e).__name__}: {e}"[:300]
    print(marker + json.dumps(out), flush=True)
'''

_ns = {}
exec(CANON, _ns)
canon = _ns["canon"]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def problem_dir(name: str) -> Path:
    d = HERE / name
    if not (d / "problem.json").exists():
        raise SystemExit(f"no problem named {name!r} in {HERE}")
    return d


def config(name: str) -> dict:
    return json.loads((problem_dir(name) / "problem.json").read_text(encoding="utf-8"))


def first_difference(exp, act, path="result"):
    if type(exp) is not type(act):
        return f"{path}: expected {type(exp).__name__} {json.dumps(exp)[:80]}, got {type(act).__name__} " \
               f"{json.dumps(act)[:80]}"
    if isinstance(exp, dict):
        if set(exp) != set(act):
            return f"{path}: keys {sorted(act)} != expected {sorted(exp)}"
        for k in sorted(exp):
            d = first_difference(exp[k], act[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(exp, list):
        for i, (e, a) in enumerate(zip(exp, act)):
            d = first_difference(e, a, f"{path}[{i}]")
            if d:
                return d
        if len(exp) != len(act):
            return f"{path}: length {len(act)} != expected {len(exp)}"
        return None
    return None if exp == act else f"{path}: expected {json.dumps(exp)[:120]}, got {json.dumps(act)[:120]}"


# ── Building expected outputs (trusted code, in-process) ────────────────────
def build(name: str, write: bool = True) -> dict:
    d = problem_dir(name)
    cfg = config(name)
    ref = load(f"{name}_reference", d / "reference.py")
    cases = load(f"{name}_cases", d / "cases.py")
    fn = getattr(ref, cfg["entry"])
    out = {"problem": name, "entry": cfg["entry"], "public": [], "hidden": [], "stress": []}
    seen = set()
    for layer in ("public", "hidden"):
        for c in getattr(cases, layer)():
            if c["id"] in seen:
                raise SystemExit(f"{name}: duplicate case id {c['id']}")
            seen.add(c["id"])
            result = canon(fn(*copy.deepcopy(c["args"])))
            if "spec_expected" in c and result != canon(c["spec_expected"]):
                raise SystemExit(f"{name}: reference disagrees with the hand-written expected output of {c['id']}: "
                                 f"{first_difference(c['spec_expected'], json.loads(result))}")
            out[layer].append({"id": c["id"], "title": c.get("title", ""), "args": c["args"],
                               "expected": json.loads(result)})
    for c in cases.stress():
        result = canon(fn(*cases.stress_args(c)))
        meta = {k: v for k, v in c.items()}
        meta.update(expected_sha256=hashlib.sha256(result.encode("utf-8")).hexdigest(), expected_head=result[:200])
        out["stress"].append(meta)
    if write:
        (d / "screen_cases.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def load_cases(name: str) -> dict:
    return json.loads((problem_dir(name) / "screen_cases.json").read_text(encoding="utf-8"))


# ── Grading untrusted code (sandboxed) ──────────────────────────────────────
def _run(sandbox, name, code_text, cases, mode, timeout):
    d0 = problem_dir(name)
    with tempfile.TemporaryDirectory(prefix=f"crucible_{name}_") as d:
        (Path(d) / "solution.py").write_text(code_text, encoding="utf-8")
        payload = cases if mode == "stress" else [{"id": c["id"], "args": c["args"]} for c in cases]
        (Path(d) / "cases.json").write_text(json.dumps(payload), encoding="utf-8")
        (Path(d) / "child.py").write_text(CHILD, encoding="utf-8")
        (Path(d) / "casegen.py").write_text((d0 / "cases.py").read_text(encoding="utf-8"), encoding="utf-8")
        code, out, err, secs = sandbox.run("child.py", Path(d), timeout=timeout, deterministic=False,
                                           args=[MARKER, mode, config(name)["entry"]])
    rows = {}
    for line in out.splitlines():
        if line.startswith(MARKER):
            rec = json.loads(line[len(MARKER):])
            rows[rec["id"]] = rec
    return rows


def _verdict(case, layer, rec, limit):
    if rec is None:
        return "no result (process died or timed out)"
    if "error" in rec:
        return rec["error"]
    if layer == "stress":
        if rec["seconds"] > limit:
            return f"too slow: {rec['seconds']}s > {limit}s"
        return None if rec["digest"] == case["expected_sha256"] else f"wrong output; starts {rec['head'][:120]}"
    if rec["canon"] == canon(case["expected"]):
        return None
    return first_difference(case["expected"], json.loads(rec["canon"])) or "mismatch"


def grade(name: str, solution, sandbox=None, workers=4) -> dict:
    sandbox = sandbox or default_sandbox()
    cfg, cs = config(name), load_cases(name)
    code_text = Path(solution).read_text(encoding="utf-8")
    small = [(c, "public") for c in cs["public"]] + [(c, "hidden") for c in cs["hidden"]]
    rows = _run(sandbox, name, code_text, [c for c, _ in small], "full", BATCH_TIMEOUT)
    if "*" in rows:
        rows = {c["id"]: rows["*"] for c, _ in small}
    elif len(rows) < len(small):
        missing = [c for c, _ in small if c["id"] not in rows]
        with ThreadPoolExecutor(workers) as pool:
            for r in pool.map(lambda c: _run(sandbox, name, code_text, [c], "full", CASE_TIMEOUT), missing):
                rows.update(r)
    if cs["stress"] and "*" not in rows:
        with ThreadPoolExecutor(min(workers, len(cs["stress"]))) as pool:
            for r in pool.map(lambda c: _run(sandbox, name, code_text, [c], "stress", STRESS_TIMEOUT), cs["stress"]):
                rows.update(r)
    elif cs["stress"]:
        rows.update({c["id"]: rows["*"] for c in cs["stress"]})
    results = []
    for c, layer in small + [(c, "stress") for c in cs["stress"]]:
        reason = _verdict(c, layer, rows.get(c["id"]), cfg.get("stress_limit_s", 10))
        results.append({"id": c["id"], "layer": layer, "title": c.get("title", ""), "pass": reason is None,
                        "reason": reason})
    scored = [r for r in results if r["layer"] != "public"]
    by_layer = {}
    for r in results:
        s = by_layer.setdefault(r["layer"], [0, 0])
        s[0] += r["pass"]
        s[1] += 1
    passed = sum(r["pass"] for r in scored)
    return {"problem": name, "sandbox": sandbox.backend, "strict_pass": passed == len(scored), "passed": passed,
            "total": len(scored), "public_pass": all(r["pass"] for r in results if r["layer"] == "public"),
            "by_layer": {k: f"{v[0]}/{v[1]}" for k, v in by_layer.items()},
            "first_failure": next((f"{r['id']}: {r['reason']}" for r in results if not r["pass"]), None),
            "cases": results}


def planted(name: str, mutant: str) -> str:
    d = problem_dir(name)
    src = (d / "reference.py").read_text(encoding="utf-8")
    for old, new in load(f"{name}_mutants", d / "mutants.py").MUTANTS[mutant]:
        if src.count(old) != 1:
            raise SystemExit(f"{name} mutant {mutant}: target text found {src.count(old)} times (need exactly 1): "
                             f"{old!r}")
        src = src.replace(old, new)
    return src


def self_test(name: str, sandbox=None) -> bool:
    sandbox = sandbox or default_sandbox()
    d = problem_dir(name)
    g = grade(name, d / "reference.py", sandbox)
    ok = g["strict_pass"] and g["public_pass"]
    print(f"[{'pass' if ok else 'FAIL'}] {name}: reference {g['passed']}/{g['total']} {g['by_layer']}"
          + ("" if ok else f" first failure: {g['first_failure']}"))
    mutants = load(f"{name}_mutants", d / "mutants.py").MUTANTS
    with tempfile.TemporaryDirectory(prefix=f"crucible_{name}_mut_") as tmp:
        for m in mutants:
            path = Path(tmp) / f"{m.split()[0]}.py"
            path.write_text(planted(name, m), encoding="utf-8")
            gm = grade(name, path, sandbox)
            killers = [r["id"] for r in gm["cases"] if not r["pass"] and r["layer"] != "public"]
            caught = bool(killers)
            ok &= caught
            print(f"  {'CAUGHT' if caught else 'MISSED'}  {m:60} by {len(killers)}: {', '.join(killers[:5])}"
                  f"{' ...' if len(killers) > 5 else ''}")
    print(f"{name}: SELF-TEST {'PASSED' if ok else 'FAILED'}")
    return ok


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["build", "grade", "self-test"])
    ap.add_argument("problem")
    ap.add_argument("solution", nargs="?")
    a = ap.parse_args()
    if a.command == "build":
        out = build(a.problem)
        print(f"{a.problem}: {len(out['public'])} public, {len(out['hidden'])} hidden, {len(out['stress'])} stress")
    elif a.command == "grade":
        g = grade(a.problem, Path(a.solution).resolve())
        print(json.dumps({k: g[k] for k in ("strict_pass", "passed", "total", "public_pass", "by_layer",
                                            "first_failure")}, indent=1))
    else:
        sys.exit(0 if self_test(a.problem) else 1)
