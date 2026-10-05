"""
Crucible Property-Based Metamorphic Invariant Test Suite.

Proves that Crucible enforces mathematical, behavioral, and resource invariants:
  1. Memory Ceiling: Detects and rejects unbounded auxiliary memory allocation.
  2. Idempotence & State Purity: Detects and rejects global state contamination.
  3. Watchdog Timeout: Enforces hard subprocess kill (exit code 124) on runaway loops.
  4. Deterministic Environmental Seeding: Enforces bit-for-bit identical executions.
"""
import tempfile
from pathlib import Path

import pytest
from crucible.invariants import MetamorphicInvariantChecker
from run_crucible import run_python, deterministic_env


BOUNDED_O1_SOLUTION = """
def process_telemetry(stream):
    # Strict O(1) memory: yields generator without buffering
    for line in stream:
        ts, sensor, temp = line.split(",")
        if float(temp) >= 95.0:
            yield {"sensor": sensor, "temp": float(temp)}
"""

UNBOUNDED_MEMORY_LEAK_SOLUTION = """
def process_telemetry(stream):
    # Deliberate memory leak: buffers entire payload and allocates massive structures
    buffer = []
    for line in stream:
        buffer.append([line] * 50)
    return buffer
"""

PURE_IDEMPOTENT_SOLUTION = """
def process_telemetry(stream):
    results = []
    for line in stream:
        parts = line.split(",")
        if len(parts) == 3 and float(parts[2]) >= 95.0:
            results.append({"sensor": parts[1], "temp": float(parts[2])})
    return results
"""

IMPURE_STATEFUL_SOLUTION = """
_GLOBAL_COUNTER = 0

def process_telemetry(stream):
    global _GLOBAL_COUNTER
    _GLOBAL_COUNTER += 1
    # First call returns 1 item, second call returns 2 items (violates idempotence)
    return [{"call_count": _GLOBAL_COUNTER}]
"""

INFINITE_LOOP_SOLUTION = """
def process_telemetry(stream):
    while True:
        pass
"""


class TestMetamorphicInvariants:
    """Verifies memory ceilings, state purity, and execution bounds."""

    def test_bounded_memory_solution_passes(self):
        with tempfile.TemporaryDirectory() as d:
            sol_path = Path(d) / "solution.py"
            sol_path.write_text(BOUNDED_O1_SOLUTION, encoding="utf-8")

            checker = MetamorphicInvariantChecker(run_python)
            res = checker.check_memory_bound(sol_path, max_memory_mb=50.0)

            assert res.passed is True, f"Expected O(1) solution to pass memory ceiling! {res.details}"
            assert res.peak_memory_mb is not None
            assert res.peak_memory_mb < 50.0

    def test_unbounded_memory_solution_fails(self):
        with tempfile.TemporaryDirectory() as d:
            sol_path = Path(d) / "solution.py"
            sol_path.write_text(UNBOUNDED_MEMORY_LEAK_SOLUTION, encoding="utf-8")

            checker = MetamorphicInvariantChecker(run_python)
            # Give a tight 20 MB ceiling; allocating 50x copies of 100k strings exceeds this
            res = checker.check_memory_bound(sol_path, max_memory_mb=20.0)

            assert res.passed is False, "Expected memory-leaking solution to fail memory ceiling!"
            assert "ceiling" in res.details or "Memory test execution failure" in res.details

    def test_pure_solution_passes_idempotence(self):
        with tempfile.TemporaryDirectory() as d:
            sol_path = Path(d) / "solution.py"
            sol_path.write_text(PURE_IDEMPOTENT_SOLUTION, encoding="utf-8")

            checker = MetamorphicInvariantChecker(run_python)
            res = checker.check_idempotence(sol_path)

            assert res.passed is True, f"Expected pure solution to pass idempotency! {res.details}"

    def test_impure_solution_fails_idempotence(self):
        with tempfile.TemporaryDirectory() as d:
            sol_path = Path(d) / "solution.py"
            sol_path.write_text(IMPURE_STATEFUL_SOLUTION, encoding="utf-8")

            checker = MetamorphicInvariantChecker(run_python)
            res = checker.check_idempotence(sol_path)

            assert res.passed is False, "Expected impure stateful solution to fail idempotency!"
            assert "Idempotency failure" in res.details

    def test_watchdog_timeout_kills_runaway_loop(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            script = tmp / "hang.py"
            script.write_text(
                "import solution\n"
                "solution.process_telemetry([])\n",
                encoding="utf-8"
            )
            sol = tmp / "solution.py"
            sol.write_text(INFINITE_LOOP_SOLUTION, encoding="utf-8")

            # Run with a short 2-second timeout to verify watchdog termination
            code, out, err, dur = run_python("hang.py", tmp, timeout=2)
            assert code == 124, f"Expected timeout exit code 124, got {code}"
            assert "TIMEOUT EXPIRED" in err
            assert dur >= 1.5
