"""
Mutation gate tests: does Crucible tell a weak AI-written suite from a strong one, and does it fail closed?

What each test refuses:
  * a tautological suite (`isinstance(result, list)`) being admitted;
  * a count-only suite (`len(result) >= 1`) being admitted. It kills most CODE mutants (crashes and count changes),
    so only the output-contract axis catches it. This is a measured regression: it was admitted at 67.6%;
  * a suite that fails the reference "killing" mutants (baseline precondition);
  * an unmutatable reference, or too few viable mutants, letting a suite through;
  * equivalent / stillborn mutants counting against or for a suite;
  * a narrow exact suite (checks values, but only on canonical input) being admitted. It kills 100% of code
    mutants and output probes, so only the input-domain axis catches it. Measured on the recorded SLA study:
    such a suite was admitted while catching 3/11 hand-written bugs;
  * non-determinism in the verdict.

Gate mechanics run on the subprocess backend for speed: the reference, mutants and suites here are fixtures
written by us, not untrusted model output. A separate test runs the same gate in Docker and checks that the
verdict is identical.
"""
import ast
import json
from pathlib import Path

import pytest

from crucible.mutation import (
    OUTPUT_PROBES,
    ArithmeticMutator,
    AugAssignMutator,
    BooleanFlipMutator,
    BoundaryConstantMutator,
    BoundaryMinusMutator,
    ConditionNegationMutator,
    LogicalMutator,
    MutationSlaughterGate,
    OPERATORS,
    RelationalMutator,
    ReturnNullifierMutator,
    StatementDeletionMutator,
    generate_mutants,
    generate_output_probes,
    generate_input_probes,
    INPUT_PROBES,
)
from crucible.sandbox import Sandbox, docker_available
from run_crucible import (
    CrucibleOrchestrator,
    MOCK_EQUIVALENCE_CORPUS,
    MOCK_SOLUTIONS,
    MOCK_STRONG_TEST_HARNESS,
    MOCK_TEST_HARNESS,
)

FAST = Sandbox("subprocess-unsafe")
REFERENCE = MOCK_SOLUTIONS["Streaming Finite-State Machine with a bounded ring buffer"]
ENTRY = "process_telemetry"
CORPUS = MOCK_EQUIVALENCE_CORPUS

TAUTOLOGICAL_SUITE = """
import sys, solution
res = solution.process_telemetry([(1000, "cpu0", 96.0), (1200, "cpu1", 91.0)])
assert isinstance(res, list)
assert len(res) >= 0
sys.exit(0)
"""

FAILS_REFERENCE_SUITE = """
import sys, solution
res = solution.process_telemetry([(1000, "cpu0", 96.0), (1200, "cpu1", 91.0)])
assert res == [], "deliberately wrong expectation"
"""


def _write(tmp: Path, name: str, text: str) -> Path:
    p = tmp / name
    p.write_text(text, encoding="utf-8")
    return p


def _gate(**kw) -> MutationSlaughterGate:
    kw.setdefault("threshold", 0.60)
    return MutationSlaughterGate(FAST.run, **kw)


# ── Operators ────────────────────────────────────────────────────────────
def _apply(op_cls, code: str, idx: int = 0) -> str:
    m = op_cls(target_index=idx)
    out = ast.unparse(ast.fix_missing_locations(m.visit(ast.parse(code))))
    assert m.applied_mutation, f"{op_cls.__name__} applied nothing to {code!r}"
    return out


@pytest.mark.parametrize("op_cls, code, expected", [
    (RelationalMutator, "ok = x >= 95.0", "ok = x > 95.0"),
    (RelationalMutator, "ok = a in b", "ok = a not in b"),
    (RelationalMutator, "ok = a is None", "ok = a is not None"),
    (BoundaryConstantMutator, "LIMIT = 500", "LIMIT = 501"),
    (BoundaryMinusMutator, "LIMIT = 500", "LIMIT = 499"),
    (ArithmeticMutator, "d = t2 - t1", "d = t2 + t1"),
    (AugAssignMutator, "i += 1", "i -= 1"),
    (LogicalMutator, "ok = a and b", "ok = a or b"),
    (ConditionNegationMutator, "if x:\n    y = 1", "if not x:\n    y = 1"),
    (BooleanFlipMutator, "active = True", "active = False"),
    (StatementDeletionMutator, "def f():\n    x = 1\n    return x", "def f():\n    pass\n    return x"),
    (ReturnNullifierMutator, "def f():\n    return [1, 2]", "def f():\n    return None"),
])
def test_each_operator_makes_exactly_the_documented_change(op_cls, code, expected):
    assert _apply(op_cls, code) == expected


def test_operator_targets_only_the_indexed_node():
    assert _apply(RelationalMutator, "a = x > 1\nb = y > 2", idx=1) == "a = x > 1\nb = y >= 2"


def test_generate_mutants_is_deterministic_deduplicated_and_compilable():
    a = generate_mutants(REFERENCE, max_mutants=40)
    b = generate_mutants(REFERENCE, max_mutants=40)
    assert [m.code for m in a] == [m.code for m in b]
    assert len({m.code for m in a}) == len(a), "duplicate mutants inflate the score"
    assert all(m.code != ast.unparse(ast.parse(REFERENCE)) for m in a)
    for m in a:
        compile(m.code, m.mutant_id, "exec")


def test_generate_mutants_round_robin_covers_many_operators_within_a_small_budget():
    ops = {m.operator for m in generate_mutants(REFERENCE, max_mutants=12)}
    assert len(ops) >= 7, f"a small budget must not be monopolised by one operator: {ops}"


def test_generate_mutants_on_unparseable_source_is_empty():
    assert generate_mutants("def broken(:\n") == []


def test_operator_registry_has_ten_distinct_operators():
    assert len({op.operator for op in OPERATORS}) == len(OPERATORS) == 10


# ── Output-contract probes ──────────────────────────────────────────────
def _exec_entry(code: str):
    ns: dict = {}
    exec(compile(code, "<probe>", "exec"), ns)  # our own fixture code, not model output
    return ns[ENTRY]


def test_every_output_probe_compiles_and_leaves_the_reference_logic_intact():
    probes = generate_output_probes(REFERENCE, ENTRY)
    assert {p.mutant_id for p in probes} == {f"probe_{n}" for n in OUTPUT_PROBES}
    for p in probes:
        assert p.code.startswith(REFERENCE), "the reference body must be untouched"


def test_output_probes_actually_corrupt_a_multi_record_result():
    stream = CORPUS[0]
    truth = _exec_entry(REFERENCE)(list(map(tuple, stream)))
    assert len(truth) == 2
    changed = {}
    for p in generate_output_probes(REFERENCE, ENTRY):
        changed[p.mutant_id] = _exec_entry(p.code)(list(map(tuple, stream))) != truth
    # Output has no booleans, so flip_bools is (correctly) a no-op; every other probe must corrupt the result.
    assert changed.pop("probe_flip_bools") is False
    assert all(changed.values()), changed


def test_output_probes_refuse_a_non_identifier_entrypoint():
    assert generate_output_probes(REFERENCE, "not valid; import os") == []


# ── Input-domain probes ─────────────────────────────────────────────────
PARSER = '''def parse(lines):
    out = []
    for line in lines:
        parts = line.split(",")
        if len(parts) != 2 or parts[0] != "ADD":
            continue
        try:
            n = int(parts[1])
        except ValueError:
            continue
        if n < 0:
            continue
        out.append(n * 2)
    return out
'''
PARSER_CORPUS = [["ADD,1", "add,3", "ADD,2.5", "ADD,7", "ADD,7", "ADD,-4", "SUB,9", "ADD,0"], [], ["ADD,9", "ADD,10"]]
# Exact assertions, every rejection rule touched, but only canonical spellings, no duplicates, already-sorted order.
NARROW_EXACT_SUITE = '''import sys, solution
assert solution.parse(["ADD,1", "ADD,5"]) == [2, 10]
assert solution.parse(["ADD,-1", "SUB,3", "ADD,0"]) == [0]
assert solution.parse(["ADD,x"]) == []
assert solution.parse(["ADD,1,2"]) == []
sys.exit(0)
'''
BROAD_EXACT_SUITE = NARROW_EXACT_SUITE.replace("sys.exit(0)", '''assert solution.parse(["add,3", "Add,4"]) == []
assert solution.parse(["ADD,2.5", "ADD,3"]) == [6]
assert solution.parse(["ADD,7", "ADD,7"]) == [14, 14]
assert solution.parse(["ADD,9", "ADD,10"]) == [18, 20]
sys.exit(0)
''')


def _exec(code: str, name: str):
    ns: dict = {}
    exec(compile(code, "<probe>", "exec"), ns)  # our own fixture code, not model output
    return ns[name]


def test_every_input_probe_compiles_and_leaves_the_reference_logic_intact():
    probes = generate_input_probes(PARSER, "parse")
    assert {p.mutant_id for p in probes} == {f"inprobe_{n}" for n in INPUT_PROBES}
    assert len(INPUT_PROBES) == 10
    for p in probes:
        assert p.code.startswith(PARSER), "the reference body must be untouched"


def test_input_probes_simulate_the_documented_careless_readers():
    truth = _exec(PARSER, "parse")
    probes = {p.mutant_id: _exec(p.code, "parse") for p in generate_input_probes(PARSER, "parse")}
    assert probes["inprobe_upper_strings"](["add,3"]) == [6] != truth(["add,3"])            # case-insensitive
    assert probes["inprobe_truncate_decimals"](["ADD,2.5"]) == [4] != truth(["ADD,2.5"])   # lenient numbers
    assert probes["inprobe_dedupe_items"](["ADD,7", "ADD,7"]) == [14]                       # drops repeats
    assert probes["inprobe_reverse_items"](["ADD,1", "ADD,2"]) == [4, 2]                    # arrival order
    assert probes["inprobe_drop_first_item"](["ADD,1", "ADD,2"]) == [4]
    assert probes["inprobe_drop_last_item"](["ADD,1", "ADD,2"]) == [2]
    # The reference really runs: the wrapper only transforms the first argument.
    assert probes["inprobe_lower_strings"](["ADD,1"]) == [] and truth(["ADD,1"]) == [2]


def test_input_probes_refuse_a_non_identifier_entrypoint():
    assert generate_input_probes(PARSER, "parse(); import os") == []


def test_narrow_exact_suite_is_perfect_on_code_and_output_axes_but_quarantined_by_input_probes(tmp_path):
    """Regression for the measured hole that motivated this axis (see experiment/gate_validation/REPORT.md)."""
    suite = _write(tmp_path, "suite.py", NARROW_EXACT_SUITE)
    r = _gate(min_viable=1).evaluate_suite(suite, PARSER, equivalence_corpus=PARSER_CORPUS, entrypoint="parse")
    assert r.code_axis_passed is True and r.slaughter_rate == 1.0, r.reason      # two-axis gate: admitted
    assert r.output_axis_passed is True and r.output_rate == 1.0, r.reason
    assert r.input_axis_passed is False and r.input_rate < 0.60, r.reason
    assert r.passed_gate is False
    assert "Input-domain probes" in r.reason and "FAILED" in r.reason
    survivors = " ".join(r.summary()["input_survivors"])
    for missed in ("upper-case", "truncate decimal", "repeated identical"):
        assert missed in survivors, survivors


def test_broad_exact_suite_is_admitted_on_all_three_axes(tmp_path):
    suite = _write(tmp_path, "suite.py", BROAD_EXACT_SUITE)
    r = _gate(min_viable=1).evaluate_suite(suite, PARSER, equivalence_corpus=PARSER_CORPUS, entrypoint="parse")
    assert r.passed_gate is True, r.reason
    assert r.input_axis_passed is True and r.input_rate == 1.0, r.summary()["input_survivors"]


def test_input_probes_that_change_nothing_on_the_corpus_are_excluded_not_counted(tmp_path):
    suite = _write(tmp_path, "suite.py", BROAD_EXACT_SUITE)
    r = _gate(min_viable=1).evaluate_suite(suite, PARSER, equivalence_corpus=PARSER_CORPUS, entrypoint="parse")
    st = {d["mutant_id"]: d["status"] for d in r.input_details}
    # int() already strips whitespace and the input holds no bare numbers: both probes are no-ops here.
    assert st["inprobe_squash_whitespace"] == "EQUIVALENT" and st["inprobe_shift_numbers"] == "EQUIVALENT", st
    assert r.input_total == sum(1 for s in st.values() if s in ("KILLED", "SURVIVED"))


def test_input_axis_can_be_disabled_and_the_report_says_so(tmp_path):
    suite = _write(tmp_path, "suite.py", NARROW_EXACT_SUITE)
    r = _gate(min_viable=1, input_probes=False).evaluate_suite(suite, PARSER, equivalence_corpus=PARSER_CORPUS,
                                                               entrypoint="parse")
    assert r.passed_gate is True and r.input_axis_passed is None
    assert "Input-domain probes DISABLED" in r.reason


# ── Gate verdicts ───────────────────────────────────────────────────────
def test_tautological_suite_is_quarantined(tmp_path):
    suite = _write(tmp_path, "suite.py", TAUTOLOGICAL_SUITE)
    r = _gate().evaluate_suite(suite, REFERENCE, equivalence_corpus=CORPUS, entrypoint=ENTRY)
    assert r.baseline_passed is True
    assert r.passed_gate is False
    assert r.code_axis_passed is False and r.slaughter_rate < 0.60
    assert r.output_axis_passed is False


def test_count_only_suite_passes_code_axis_but_is_quarantined_by_output_probes(tmp_path):
    """Regression for the measured hole: the mock round-1 suite killed 25/37 code mutants (67.6%)."""
    suite = _write(tmp_path, "suite.py", MOCK_TEST_HARNESS)
    r = _gate().evaluate_suite(suite, REFERENCE, equivalence_corpus=CORPUS, entrypoint=ENTRY)
    assert r.code_axis_passed is True, r.reason       # the old single-axis gate would have admitted it
    assert r.output_probes_checked is True
    assert r.output_rate is not None and r.output_rate < 0.60, r.reason
    assert r.passed_gate is False
    assert "does not check output values" in r.reason
    survivors = r.summary()["output_survivors"]
    assert any("rename" in s for s in survivors) and any("numeric" in s for s in survivors), survivors


def test_exact_output_suite_is_admitted_on_both_axes(tmp_path):
    suite = _write(tmp_path, "suite.py", MOCK_STRONG_TEST_HARNESS)
    r = _gate().evaluate_suite(suite, REFERENCE, equivalence_corpus=CORPUS, entrypoint=ENTRY)
    assert r.passed_gate is True, r.reason
    assert r.slaughter_rate >= 0.60 and r.total_mutants >= 5
    assert r.output_rate == 1.0, r.summary()["output_survivors"]
    assert r.kills_by_kind["assertion"] > 0  # it detects bugs by checking values, not only by crashing


def test_suite_that_fails_the_reference_fails_closed_without_counting_kills(tmp_path):
    suite = _write(tmp_path, "suite.py", FAILS_REFERENCE_SUITE)
    r = _gate().evaluate_suite(suite, REFERENCE, equivalence_corpus=CORPUS, entrypoint=ENTRY)
    assert r.passed_gate is False and r.baseline_passed is False
    assert r.killed_mutants == 0 and r.total_mutants == 0
    assert "fails the unmutated reference" in r.reason


def test_unmutatable_reference_fails_closed(tmp_path):
    ref = "def process_telemetry(stream):\n    pass\n"
    suite = _write(tmp_path, "suite.py", "import solution\nsolution.process_telemetry([])\n")
    r = _gate().evaluate_suite(suite, ref, equivalence_corpus=[[]], entrypoint=ENTRY)
    assert r.passed_gate is False and r.generated_mutants == 0
    assert "no mutants could be generated" in r.reason


def test_too_few_viable_mutants_fails_closed_even_with_a_perfect_score(tmp_path):
    suite = _write(tmp_path, "suite.py", MOCK_STRONG_TEST_HARNESS)
    r = _gate(min_viable=500).evaluate_suite(suite, REFERENCE, equivalence_corpus=CORPUS, entrypoint=ENTRY)
    assert r.passed_gate is False and "too few to demonstrate strength" in r.reason


def test_equivalent_and_stillborn_mutants_are_excluded_from_the_denominator(tmp_path):
    ref = (
        "LIMIT = 10\n"
        "assert LIMIT == 10\n"                       # boundary mutants of LIMIT cannot import: stillborn
        "def process_telemetry(xs):\n"
        "    unused = False\n"                       # boolean flip here changes nothing: equivalent
        "    return [x for x in xs if x > LIMIT]\n"
    )
    suite = _write(tmp_path, "suite.py",
                   "import sys, solution\n"
                   "ok = solution.process_telemetry([5, 10, 11, 20]) == [11, 20]\n"
                   "sys.exit(0 if ok else 1)\n")
    r = _gate(min_viable=1).evaluate_suite(suite, ref, equivalence_corpus=[[5, 10, 11, 20], [], [10]],
                                           entrypoint=ENTRY)
    statuses = {d["description"]: d["status"] for d in r.details}
    assert r.equivalence_checked is True
    assert r.stillborn_mutants >= 1 and r.equivalent_mutants >= 1, statuses
    assert r.total_mutants == r.generated_mutants - r.stillborn_mutants - r.equivalent_mutants
    assert any(s == "EQUIVALENT" and "Boolean flip" in d for d, s in statuses.items()), statuses


def test_without_a_corpus_the_report_says_the_score_is_a_lower_bound(tmp_path):
    suite = _write(tmp_path, "suite.py", MOCK_STRONG_TEST_HARNESS)
    r = _gate().evaluate_suite(suite, REFERENCE)
    assert r.equivalence_checked is False and r.output_probes_checked is False
    assert "lower bound" in r.reason and "Output-contract probes NOT run" in r.reason


def test_infinite_loop_mutant_is_killed_by_timeout_not_by_stalling_the_gate(tmp_path):
    ref = ("def process_telemetry(n):\n"
           "    i = 0\n"
           "    while i < n:\n"
           "        i += 1\n"
           "    return i\n")
    suite = _write(tmp_path, "suite.py", "import sys, solution\nsys.exit(0 if solution.process_telemetry(3) == 3 else 1)\n")
    r = _gate(min_viable=1, timeout=3).evaluate_suite(suite, ref, equivalence_corpus=[3, 0], entrypoint=ENTRY)
    timeouts = [d for d in r.details if d["killed_by"] == "timeout"]
    assert timeouts, [(d["description"], d["status"], d["killed_by"]) for d in r.details]
    assert all(d["exit_code"] == 124 for d in timeouts)


def test_gate_verdict_is_deterministic(tmp_path):
    suite = _write(tmp_path, "suite.py", MOCK_TEST_HARNESS)
    g = _gate()
    a = g.evaluate_suite(suite, REFERENCE, equivalence_corpus=CORPUS, entrypoint=ENTRY).summary()
    b = g.evaluate_suite(suite, REFERENCE, equivalence_corpus=CORPUS, entrypoint=ENTRY).summary()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


@pytest.mark.parametrize("kw", [{"threshold": 0}, {"threshold": 1.5}, {"output_threshold": 0},
                                {"input_threshold": 0}, {"input_threshold": 1.5}])
def test_invalid_thresholds_are_refused(kw):
    with pytest.raises(ValueError):
        MutationSlaughterGate(FAST.run, **kw)


@pytest.mark.skipif(not docker_available()[0], reason="Docker not available")
def test_gate_verdict_is_identical_inside_the_docker_sandbox(tmp_path):
    suite = _write(tmp_path, "suite.py", MOCK_TEST_HARNESS)
    fast = _gate().evaluate_suite(suite, REFERENCE, equivalence_corpus=CORPUS, entrypoint=ENTRY)
    dock = MutationSlaughterGate(Sandbox("docker").run, threshold=0.60).evaluate_suite(
        suite, REFERENCE, equivalence_corpus=CORPUS, entrypoint=ENTRY)
    assert (dock.passed_gate, dock.killed_mutants, dock.total_mutants, dock.output_killed, dock.output_total,
            dock.input_killed, dock.input_total) == \
           (fast.passed_gate, fast.killed_mutants, fast.total_mutants, fast.output_killed, fast.output_total,
            fast.input_killed, fast.input_total)


# ── Orchestrator integration ────────────────────────────────────────────
def _orch(tmp_path: Path, ref: Path, **kw) -> CrucibleOrchestrator:
    return CrucibleOrchestrator(problem_statement="mutation gate", paradigms=["P1"], mock_mode=True,
                                workspace_dir=str(tmp_path / ".workspace"), output_dir=str(tmp_path / "out"),
                                reference_solution=str(ref), sandbox=FAST, **kw)


def test_orchestrator_quarantines_count_only_suite_and_records_both_axes(tmp_path):
    ref = _write(tmp_path, "ref.py", REFERENCE)
    adm = _orch(tmp_path, ref)._admit_suite(_write(tmp_path, "suite.py", MOCK_TEST_HARNESS))
    assert adm["decision"] == "quarantined"
    assert "QUARANTINED (TAUTOLOGICAL)" in adm["reason"]
    ms = adm["mutation_slaughter"]
    assert ms["passed"] is False and ms["code_axis_passed"] is True and ms["output_axis_passed"] is False
    assert ms["input_axis_passed"] is False and ms["input_total"] > 0, ms["input_survivors"]


def test_orchestrator_admits_exact_output_suite(tmp_path):
    ref = _write(tmp_path, "ref.py", REFERENCE)
    adm = _orch(tmp_path, ref)._admit_suite(_write(tmp_path, "suite.py", MOCK_STRONG_TEST_HARNESS))
    assert adm["decision"] == "admitted", adm["reason"]
    assert adm["mutation_slaughter"]["passed"] is True


def test_orchestrator_gate_disabled_admits_on_reference_alone_and_says_so(tmp_path):
    ref = _write(tmp_path, "ref.py", REFERENCE)
    adm = _orch(tmp_path, ref, mutation_gate=False)._admit_suite(_write(tmp_path, "suite.py", MOCK_TEST_HARNESS))
    assert adm["decision"] == "admitted" and "mutation gate disabled" in adm["reason"]


def test_orchestrator_refuses_forced_gate_without_reference(tmp_path):
    with pytest.raises(ValueError, match="mutation gate"):
        CrucibleOrchestrator(problem_statement="x", paradigms=["P1"], mock_mode=False, mutation_gate=True,
                             allow_advisory_only=True, workspace_dir=str(tmp_path / "w"),
                             output_dir=str(tmp_path / "o"), sandbox=FAST)
