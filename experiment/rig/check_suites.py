"""Tests the tester: runs every Crucible-written test suite in a pilot against the trusted reference implementation.

  python experiment/rig/check_suites.py experiment/runs/<pilot folder>

A suite that fails the reference implementation contains at least one wrong expectation: under the reviewed spec,
the reference is correct by construction (it passes the hand cases, agrees with an independent second implementation
and catches every deliberate bug). Writes suite_check.json into the pilot folder; it never edits audited files.
Suites are AI-written code, so each is screened first: any import outside a small allowlist means it is not run.
For pilots that used a different spec (the ablation), a failure may reflect the spec difference, not a test bug.
"""
import ast
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXP.parent))
from crucible.sandbox import scrubbed_env  # noqa: E402  (AI-written suites never see API keys)

REFERENCE = EXP / "sla" / "reference.py"
ALLOWED = {"solution", "sys", "json", "time", "math", "random", "collections", "itertools", "traceback", "typing",
           "dataclasses", "re", "gc", "tracemalloc", "io", "functools", "string", "copy", "unittest", "textwrap",
           "statistics", "datetime", "heapq", "bisect", "__future__"}


def screen(path: Path) -> list[str]:
    bad = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            bad |= {a.name.split(".")[0] for a in node.names} - ALLOWED
        elif isinstance(node, ast.ImportFrom) and node.module:
            bad |= {node.module.split(".")[0]} - ALLOWED
    return sorted(bad)


def run_suite(suite: Path) -> dict:
    blocked = screen(suite)
    if blocked:
        return {"suite": suite.name, "ran": False, "reason": f"imports outside allowlist: {blocked}"}
    with tempfile.TemporaryDirectory(prefix="suite_check_") as d:
        shutil.copy(suite, Path(d) / "arena_test.py")
        shutil.copy(REFERENCE, Path(d) / "solution.py")
        try:
            p = subprocess.run([sys.executable, "arena_test.py"], cwd=d, capture_output=True, text=True, timeout=120,
                               env=scrubbed_env(deterministic=False))
            code, output = p.returncode, p.stdout + p.stderr
        except subprocess.TimeoutExpired:
            code, output = "timeout", ""
    failures = [l.strip()[:200] for l in output.splitlines() if "FAIL" in l or "AssertionError" in l][:5]
    return {"suite": suite.name, "ran": True, "reference_passes": code == 0, "exit_code": code, "failures": failures}


def main(pilot: Path):
    spec = json.loads((pilot / "summary.json").read_text(encoding="utf-8"))["config"].get("spec", "SPEC.md")
    results = {}
    for run in sorted(p for p in pilot.iterdir() if p.is_dir() and p.name.startswith("B")):
        results[run.name] = [run_suite(s) for s in sorted((run / "candidates").glob("round*_crucible_tests.py"))]
        for r in results[run.name]:
            status = ("reference passes: suite consistent" if r.get("reference_passes") else
                      "REFERENCE FAILS: suite has a wrong expectation") if r["ran"] else f"not run ({r['reason']})"
            print(f"{run.name}/{r['suite']}: {status}")
            for f in r.get("failures", [])[:2]:
                print(f"      {f}")
    out = {"pilot": pilot.name, "spec": spec,
           "note": "Under SPEC.md the reference is correct by construction; under another spec a failure may be a spec difference.",
           "runs": results}
    (pilot / "suite_check.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
