"""
Crucible Adversarial Mutation Gate Test Suite.

Proves that Crucible detects and destroys the "Ouroboros of Mediocrity" by:
  1. Ruthlessly rejecting and quarantining tautological or trivial AI test suites.
  2. Admitting only rigorous test suites that actively slaughter synthetic mutants.
  3. Verifying AST mutation operators (relational, boundary, arithmetic, boolean, return nullification).
  4. Testing configurable slaughter thresholds in pipeline admission.
"""
import ast
import tempfile
from pathlib import Path

import pytest
from crucible.mutation import (
    ASTMutator,
    RelationalMutator,
    BoundaryConstantMutator,
    ArithmeticMutator,
    BooleanFlipMutator,
    ReturnNullifierMutator,
    generate_mutants,
    MutationSlaughterGate,
)
from run_crucible import run_python, CrucibleOrchestrator


SAMPLE_REFERENCE_CODE = """
def process_telemetry(stream):
    TRIGGER = 95.0
    CASCADE = 90.0
    WINDOW = 500
    triggers = []
    cascades = []
    for ts, sensor, temp in stream:
        if temp >= TRIGGER:
            triggers.append((ts, sensor, temp))
        if temp >= CASCADE:
            for trig_ts, trig_sensor, trig_temp in triggers:
                if ts - trig_ts <= WINDOW and sensor != trig_sensor:
                    cascades.append({
                        "trigger_sensor": trig_sensor,
                        "trigger_ts": trig_ts,
                        "cascade_sensor": sensor,
                        "cascade_ts": ts,
                    })
        triggers = [(t, s, v) for t, s, v in triggers if ts - t <= WINDOW]
    return cascades
"""

TAUTOLOGICAL_TEST_SUITE = """
import sys
import solution

# A weak, trivial test suite that asserts nothing about detection logic:
def test_trivial():
    stream = [(1000, "cpu0", 96.0), (1200, "cpu1", 91.0)]
    res = solution.process_telemetry(stream)
    # Tautological checks that almost any mutant will pass
    assert isinstance(res, list), "Expected list"
    assert len(res) >= 0, "Length should be non-negative"

if __name__ == "__main__":
    test_trivial()
    sys.exit(0)
"""

RIGOROUS_TEST_SUITE = """
import sys
import solution

def test_exact_boundary_cascade():
    # 1. Exact boundary values: 95.0C trigger, 90.0C cascade, exactly 500ms window
    stream = [(1000, "cpu0", 95.0), (1500, "cpu1", 90.0)]
    res = solution.process_telemetry(stream)
    assert len(res) == 1, f"Expected 1 cascade at exact boundary, got {len(res)}"
    assert res[0]["trigger_sensor"] == "cpu0"
    assert res[0]["cascade_sensor"] == "cpu1"

def test_below_boundary_trigger():
    # Below boundary: 94.9C must not trigger
    stream = [(1000, "cpu0", 94.9), (1200, "cpu1", 91.0)]
    res = solution.process_telemetry(stream)
    assert len(res) == 0, f"Expected 0 cascades below trigger, got {len(res)}"

def test_below_cascade_boundary():
    # Below cascade: 89.9C must not cascade
    stream = [(1000, "cpu0", 96.0), (1200, "cpu1", 89.9)]
    res = solution.process_telemetry(stream)
    assert len(res) == 0, f"Expected 0 cascades below cascade threshold, got {len(res)}"

def test_window_boundary_501ms():
    # Window is 500ms; 501ms must expire
    stream = [(1000, "cpu0", 96.0), (1501, "cpu1", 91.0)]
    res = solution.process_telemetry(stream)
    assert len(res) == 0, f"Expected 0 cascades at 501ms, got {len(res)}"

def test_same_sensor_not_cascade():
    # Same sensor cannot cascade to itself
    stream = [(1000, "cpu0", 96.0), (1200, "cpu0", 91.0)]
    res = solution.process_telemetry(stream)
    assert len(res) == 0, f"Expected 0 cascades for same sensor, got {len(res)}"

if __name__ == "__main__":
    test_exact_boundary_cascade()
    test_below_boundary_trigger()
    test_below_cascade_boundary()
    test_window_boundary_501ms()
    test_same_sensor_not_cascade()
    sys.exit(0)
"""


class TestASTMutators:
    """Tests each individual AST mutation operator."""

    def test_relational_mutator_inverts_operators(self):
        code = "if x >= 95.0 and y == 10:\n    pass\n"
        tree = ast.parse(code)
        mutator = RelationalMutator(mutation_type="relational", target_index=0)
        mutated_tree = mutator.visit(tree)
        mutated_code = ast.unparse(mutated_tree)
        assert "x > 95.0" in mutated_code

    def test_boundary_constant_mutator_shifts_constants(self):
        code = "LIMIT = 500\n"
        tree = ast.parse(code)
        mutator = BoundaryConstantMutator(mutation_type="boundary", target_index=0)
        mutated_tree = mutator.visit(tree)
        mutated_code = ast.unparse(mutated_tree)
        assert "LIMIT = 501" in mutated_code

    def test_boolean_flip_mutator(self):
        code = "active = True\n"
        tree = ast.parse(code)
        mutator = BooleanFlipMutator(mutation_type="boolean", target_index=0)
        mutated_tree = mutator.visit(tree)
        mutated_code = ast.unparse(mutated_tree)
        assert "active = False" in mutated_code

    def test_arithmetic_mutator_swaps_operators(self):
        code = "delta = t2 - t1\n"
        tree = ast.parse(code)
        mutator = ArithmeticMutator(mutation_type="arithmetic", target_index=0)
        mutated_tree = mutator.visit(tree)
        mutated_code = ast.unparse(mutated_tree)
        assert "t2 + t1" in mutated_code

    def test_return_nullifier_alters_return_statement(self):
        code = "def f():\n    return [1, 2, 3]\n"
        tree = ast.parse(code)
        mutator = ReturnNullifierMutator(mutation_type="return_null", target_index=0)
        mutated_tree = mutator.visit(tree)
        mutated_code = ast.unparse(mutated_tree)
        assert "return []" in mutated_code

    def test_generate_mutants_produces_diverse_pool(self):
        mutants = generate_mutants(SAMPLE_REFERENCE_CODE, max_mutants=10)
        assert len(mutants) >= 5
        mutant_ids = [m.mutant_id for m in mutants]
        # Should contain multiple categories
        assert any("relational" in mid for mid in mutant_ids)
        assert any("boundary" in mid for mid in mutant_ids)


class TestMutationSlaughterGate:
    """Tests the gatekeeper evaluating test suites against reference mutants."""

    def test_tautological_test_suite_is_rejected(self):
        """
        Critical invariant: A test suite with trivial assertions must fail to kill
        the mutants and be marked passed_gate = False (QUARANTINED).
        """
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            ref_path = tmp / "ref.py"
            ref_path.write_text(SAMPLE_REFERENCE_CODE, encoding="utf-8")
            suite_path = tmp / "tautological_suite.py"
            suite_path.write_text(TAUTOLOGICAL_TEST_SUITE, encoding="utf-8")

            gate = MutationSlaughterGate(run_python, threshold=0.50, max_mutants=6)
            result = gate.evaluate_suite(suite_path, ref_path)

            assert result.passed_gate is False, (
                f"Expected tautological test suite to be rejected! "
                f"Slaughter rate was {result.slaughter_rate}"
            )
            assert result.slaughter_rate < 0.50
            assert "FAILED threshold" in result.reason
            assert result.survived_mutants > 0

    def test_rigorous_test_suite_is_admitted(self):
        """
        A rigorous test suite checking exact values and boundaries kills all or most
        mutants and passes the gate.
        """
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            ref_path = tmp / "ref.py"
            ref_path.write_text(SAMPLE_REFERENCE_CODE, encoding="utf-8")
            suite_path = tmp / "rigorous_suite.py"
            suite_path.write_text(RIGOROUS_TEST_SUITE, encoding="utf-8")

            gate = MutationSlaughterGate(run_python, threshold=0.60, max_mutants=6)
            result = gate.evaluate_suite(suite_path, ref_path)

            assert result.passed_gate is True, (
                f"Expected rigorous test suite to be admitted! "
                f"Slaughter rate: {result.slaughter_rate}, reason: {result.reason}"
            )
            assert result.slaughter_rate >= 0.60
            assert result.killed_mutants > 0

    def test_orchestrator_quarantines_tautological_suite_in_admit_suite(self):
        """
        Integration test: When mutation_gate=True is enabled in CrucibleOrchestrator,
        a test suite that passes the reference but fails mutation slaughter is quarantined.
        """
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            ref_path = tmp / "ref.py"
            ref_path.write_text(SAMPLE_REFERENCE_CODE, encoding="utf-8")
            tautological_suite = tmp / "tautological_suite.py"
            tautological_suite.write_text(TAUTOLOGICAL_TEST_SUITE, encoding="utf-8")

            orch = CrucibleOrchestrator(
                problem_statement="Test mutation gate",
                paradigms=["P1"],
                mock_mode=True,
                workspace_dir=str(tmp / ".workspace"),
                output_dir=str(tmp / "out"),
                reference_solution=str(ref_path),
                mutation_gate=True,
                mutation_threshold=0.60,
            )

            admission = orch._admit_suite(tautological_suite)
            assert admission["decision"] == "quarantined"
            assert "QUARANTINED (TAUTOLOGICAL)" in admission["reason"]
            assert "mutation_slaughter" in admission
            assert admission["mutation_slaughter"]["passed"] is False
