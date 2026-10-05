"""Validates the mutation gate on real AI-written suites against an independent yardstick.

    python experiment/validate_mutation_gate.py            # Docker sandbox (the suites are model-written code)
    python experiment/validate_mutation_gate.py --unsafe-subprocess-sandbox

Question: when the gate admits or quarantines a suite, is it right?

The gate's own evidence (auto-generated code mutants + output probes of the reference) cannot answer that by
itself, so every suite is ALSO scored on the 11 hand-written bugs in experiment/grade.py (MUTANTS). Those bugs were
written by a human from the spec before any of these suites existed, and the gate never sees them. A suite is
"independently strong" if it passes the reference and catches >= 60% of them.

Subjects:
  * every Crucible-written suite recorded under experiment/runs/ (7 suites, 3 pilots);
  * 4 controls with known strength: a tautology and a count-only suite (should be quarantined), and two
    exact-output suites built from the human-written expected values (should be admitted).

Writes experiment/gate_validation/report.json and REPORT.md. Recorded runs are read, never modified.

Calibration, not validation (stated, not hidden): the input-domain axis was added AFTER the two-axis gate admitted
`control_exact_hand` here (false security). Both verdicts are reported. The three-axis figure is therefore an
in-sample result on the set that motivated the change; the out-of-sample check is pre-registered on a new problem.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP.parent))
sys.path.insert(0, str(EXP))

from crucible.mutation import MutationSlaughterGate  # noqa: E402
from crucible.sandbox import Sandbox, default_sandbox, docker_available  # noqa: E402
from grade import MUTANTS  # noqa: E402

REFERENCE = EXP / "sla" / "reference.py"
ENTRY = "compute_sla"
OUT = EXP / "gate_validation"
THRESHOLD = 0.60


def hidden_cases():
    hand = json.loads((EXP / "sla" / "hand_cases.json").read_text(encoding="utf-8"))
    gen = json.loads((EXP / "sla" / "generated_cases.json").read_text(encoding="utf-8"))
    return hand, [c for c in gen if c.get("layer") != "stress"]


def _exact_suite(cases, label):
    payload = json.dumps([{"id": c["id"], "lines": c["lines"], "expected": c["expected"]} for c in cases])
    return (f"# CONTROL ({label}): exact equality against human-reviewed expected outputs.\n"
            "import json, sys, solution\n"
            f"CASES = json.loads({payload!r})\n"
            "bad = [c['id'] for c in CASES if solution.compute_sla(list(c['lines'])) != c['expected']]\n"
            "print('FAIL', bad) if bad else print('PASS')\n"
            "sys.exit(1 if bad else 0)\n")


def controls(hand, edge):
    lines = json.dumps([c["lines"] for c in hand])
    counts = json.dumps([[c["lines"], len(c["expected"])] for c in hand])
    return {
        "control_tautology": ("weak", "# CONTROL: tautology.\nimport json, solution\n"
                              f"for lines in json.loads({lines!r}):\n"
                              "    assert isinstance(solution.compute_sla(list(lines)), list)\n"),
        "control_count_only": ("weak", "# CONTROL: checks only how many tickets come back.\nimport json, solution\n"
                               f"for lines, n in json.loads({counts!r}):\n"
                               "    assert len(solution.compute_sla(list(lines))) == n\n"),
        "control_exact_hand": ("strong", _exact_suite(hand, "6 hand cases")),
        "control_exact_hand_edge": ("strong", _exact_suite(hand + edge, "hand + 24 edge cases")),
    }


def human_bug_kills(run, suite_code: str) -> dict:
    """Runs the suite against each hand-written bug from grade.MUTANTS (independent of the gate)."""
    source = REFERENCE.read_text(encoding="utf-8")
    killed, names = 0, []
    for name, edits in MUTANTS.items():
        mutated = source
        for old, new in edits:
            mutated = mutated.replace(old, new)
        with tempfile.TemporaryDirectory(prefix="crucible_hbug_") as d:
            (Path(d) / "solution.py").write_text(mutated, encoding="utf-8")
            (Path(d) / "arena_test.py").write_text(suite_code, encoding="utf-8")
            code = run("arena_test.py", Path(d), timeout=120)[0]
        if code != 0:
            killed += 1
        else:
            names.append(name)
    return {"killed": killed, "total": len(MUTANTS), "rate": round(killed / len(MUTANTS), 3), "missed": names}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unsafe-subprocess-sandbox", action="store_true",
                    help="run model-written suites WITHOUT isolation (not recommended)")
    a = ap.parse_args()
    sandbox = Sandbox("subprocess-unsafe") if a.unsafe_subprocess_sandbox else default_sandbox()
    if sandbox.backend == "docker" and not docker_available()[0]:
        raise SystemExit(f"Docker unavailable ({docker_available()[1]}); refusing to run model-written suites "
                         "unisolated. Pass --unsafe-subprocess-sandbox to override.")
    run = sandbox.run
    hand, edge = hidden_cases()
    corpus = [c["lines"] for c in hand + edge]
    gate = MutationSlaughterGate(run, threshold=THRESHOLD, max_mutants=40)

    subjects = []
    for p in sorted((EXP / "runs").glob("*/B*/candidates/round*_crucible_tests.py")):
        subjects.append((p.relative_to(EXP).as_posix(), "recorded AI suite", p.read_text(encoding="utf-8")))
    for name, (kind, code) in controls(hand, edge).items():
        subjects.append((name, f"control ({kind})", code))

    rows = []
    for name, kind, code in subjects:
        print(f"[gate] {name} ...", flush=True)
        with tempfile.TemporaryDirectory(prefix="crucible_val_") as d:
            suite = Path(d) / "suite.py"
            suite.write_text(code, encoding="utf-8")
            r = gate.evaluate_suite(suite, REFERENCE, equivalence_corpus=corpus, entrypoint=ENTRY)
        hb = human_bug_kills(run, code) if r.baseline_passed else None
        strong = bool(r.baseline_passed) and hb is not None and hb["rate"] >= THRESHOLD
        two_axis = bool(r.code_axis_passed) and r.output_axis_passed is not False
        rows.append({
            "suite": name, "kind": kind, "baseline_passes_reference": r.baseline_passed,
            "gate_admits": r.passed_gate, "two_axis_gate_admits": two_axis,
            "code_axis": {"killed": r.killed_mutants, "viable": r.total_mutants,
                          "rate": r.slaughter_rate, "passed": r.code_axis_passed},
            "output_axis": {"killed": r.output_killed, "viable": r.output_total, "rate": r.output_rate,
                            "passed": r.output_axis_passed},
            "input_axis": {"killed": r.input_killed, "viable": r.input_total, "rate": r.input_rate,
                           "passed": r.input_axis_passed,
                           "survivors": [x["description"] for x in r.input_details if x["status"] == "SURVIVED"]},
            "equivalent_excluded": r.equivalent_mutants, "stillborn_excluded": r.stillborn_mutants,
            "human_bugs": hb, "independently_strong": strong,
            "agree": r.passed_gate == strong, "two_axis_agree": two_axis == strong, "gate_reason": r.reason,
        })
        print(f"       admits={r.passed_gate} (two-axis {two_axis}) strong={strong} "
              f"human_bugs={hb and hb['rate']}", flush=True)

    def confusion(key):
        return {"admitted_and_strong": sum(r[key] and r["independently_strong"] for r in rows),
                "quarantined_and_weak": sum(not r[key] and not r["independently_strong"] for r in rows),
                "admitted_but_weak (false security)": sum(r[key] and not r["independently_strong"] for r in rows),
                "quarantined_but_strong (lost signal)": sum(not r[key] and r["independently_strong"] for r in rows)}

    c3, c2 = confusion("gate_admits"), confusion("two_axis_gate_admits")
    tp, tn = c3["admitted_and_strong"], c3["quarantined_and_weak"]
    fp, fn = c3["admitted_but_weak (false security)"], c3["quarantined_but_strong (lost signal)"]
    agree2 = c2["admitted_and_strong"] + c2["quarantined_and_weak"]
    report = {"reference": "experiment/sla/reference.py", "threshold": THRESHOLD, "sandbox": sandbox.describe(),
              "corpus_inputs": len(corpus), "independent_yardstick": f"{len(MUTANTS)} hand-written bugs (grade.MUTANTS)",
              "confusion": c3, "agreement": f"{tp + tn}/{len(rows)}",
              "two_axis_confusion": c2, "two_axis_agreement": f"{agree2}/{len(rows)}",
              "calibration_note": "input axis added after the two-axis gate admitted control_exact_hand on this set; "
                                  "three-axis figure is in-sample",
              "rows": rows}
    OUT.mkdir(exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    md = ["# Mutation gate validation (generated by `experiment/validate_mutation_gate.py`)", "",
          f"Reference: `experiment/sla/reference.py`. Threshold {THRESHOLD:.0%} on every axis. "
          f"Sandbox: `{sandbox.backend}`. Equivalence corpus: {len(corpus)} hidden-case inputs.", "",
          f"Independent yardstick: the {len(MUTANTS)} hand-written bugs in `experiment/grade.py`, which the gate "
          "never sees. *Strong* = passes the reference and catches at least 60% of them.", "",
          "| Suite | Kind | Passes ref | Code | Output | Input | 2-axis gate | 3-axis gate | Human bugs | Strong "
          "| Agree |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        ca, oa, ia, hb = r["code_axis"], r["output_axis"], r["input_axis"], r["human_bugs"]
        md.append(f"| `{r['suite']}` | {r['kind']} | {r['baseline_passes_reference']} | "
                  f"{ca['killed']}/{ca['viable']} | {oa['killed']}/{oa['viable']} | {ia['killed']}/{ia['viable']} | "
                  f"{'ADMIT' if r['two_axis_gate_admits'] else 'quarantine'} | "
                  f"{'ADMIT' if r['gate_admits'] else 'quarantine'} | "
                  f"{(str(hb['killed']) + '/' + str(hb['total'])) if hb else 'n/a'} | {r['independently_strong']} | "
                  f"{'yes' if r['agree'] else '**NO**'} |")
    md += ["", f"Two-axis gate (code + output): agreement **{agree2}/{len(rows)}**, false security "
           f"**{c2['admitted_but_weak (false security)']}**, lost signal "
           f"**{c2['quarantined_but_strong (lost signal)']}**.", "",
           f"Three-axis gate (code + output + input): agreement **{tp + tn}/{len(rows)}**, false security **{fp}**, "
           f"lost signal **{fn}**.", "",
           "Calibration, not validation: the input-domain axis was designed after the two-axis gate admitted "
           "`control_exact_hand` on this set. The three-axis figure is in-sample. The out-of-sample check is "
           "pre-registered on a different problem (`experiment/PREREGISTRATION.md`).", "",
           "Limits: 11 suites from one problem is a small sample. The yardstick is itself finite (11 bugs). "
           "A suite that shares the reference's misreading of the spec passes both checks; only independent "
           "ground truth (human cases, a second oracle) can catch that."]
    (OUT / "REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[-9:]))
    print(f"Wrote {OUT / 'report.json'} and REPORT.md")
    return 0 if fp == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
