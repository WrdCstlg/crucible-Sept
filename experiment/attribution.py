"""Attribution check for a spec ablation run.

  python experiment/attribution.py experiment/runs/<pilot_folder>

Regrades every solution in the run against an alternative answer key in which one decision that is absent
from the original spec (OPEN on a closed ticket resets the clock) is replaced by the most natural reading
of the original spec (OPEN on a closed ticket is ignored). Failures that disappear are explained by that
single missing decision; failures that remain come from other gaps.
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grade  # noqa: E402


def main(pilot: Path):
    src = (HERE / "sla" / "reference.py").read_text(encoding="utf-8")
    old = 'if event == "OPEN" and state in ("NOT_OPENED", "CLOSED"):'
    assert old in src, "reference.py changed; update this script"
    ns = {}
    exec(compile(src.replace(old, 'if event == "OPEN" and state == "NOT_OPENED":'), "variant", "exec"), ns)
    variant = ns["compute_sla"]

    cases = grade.load_cases()
    changed, rewritten = [], []
    for c in cases:
        expected = variant(list(c["lines"]))
        if expected != c["expected"]:
            changed.append(c["id"])
        rewritten.append({k: v for k, v in c.items() if k != "_file"} | {"expected": expected})
    print("cases whose answer depends on the OPEN-reset decision:", ", ".join(changed))

    with tempfile.TemporaryDirectory(prefix="attribution_") as tmp:
        alt = Path(tmp) / "alternative_key.json"
        alt.write_text(json.dumps(rewritten), encoding="utf-8")
        grade.CASE_FILES = [alt]
        for sol in sorted(pilot.glob("[ABC][0-9]/solution.py")):
            g = grade.grade(sol)
            left = [r["id"] for r in g["cases"] if not r["pass"]]
            print(f"{sol.parent.name}: {g['passed']}/{g['total']} on the alternative key; remaining failures: {', '.join(left) or 'none'}")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
