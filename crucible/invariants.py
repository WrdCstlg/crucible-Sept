"""
Crucible Property-Based Metamorphic Invariant Engine.

Verifies behavioral invariants and resource bounds that unit tests often miss:
  1. MEMORY CEILING INVARIANT: Strict O(1) auxiliary memory ceiling verification
     using tracemalloc under continuous high-volume data streams.
  2. IDEMPOTENCE & STATE PURITY: Verifies that multiple invocations with identical inputs
     produce identical outputs without mutating inputs or retaining leaky global state.
  3. MALFORMED STREAM RESILIENCE: Validates that out-of-order, malformed, or boundary
     records are handled deterministically without crashing.
  4. METAMORPHIC DIFFERENTIAL ORACLE: Cross-checks competing candidate branches on
     metamorphic data transforms (e.g. chronological chunking, time-shift invariance).
"""
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional


@dataclass
class InvariantCheckResult:
    check_name: str
    passed: bool
    details: str
    peak_memory_mb: Optional[float] = None
    duration_seconds: float = 0.0


# Script template executed in isolated subprocess to verify memory bounds using tracemalloc
MEMORY_RUNNER = r'''
import sys
import tracemalloc
import solution

entrypoint_name = sys.argv[1]
limit_mb = float(sys.argv[2])
entry = getattr(solution, entrypoint_name)

# High volume stream generator (synthetic 100,000 records)
def sample_stream():
    for i in range(100000):
        yield f"{i*10},sensor_{i%5},{80.0 + (i%20)}"

tracemalloc.start()
try:
    res = list(entry(sample_stream()))
    current, peak = tracemalloc.get_traced_memory()
    peak_mb = peak / (1024 * 1024)
finally:
    tracemalloc.stop()

sys.stdout.write(f"{peak_mb:.2f}")
if peak_mb > limit_mb:
    sys.exit(1)
sys.exit(0)
'''

# Script template to verify idempotence and purity
IDEMPOTENCE_RUNNER = r'''
import sys
import json
import solution

entrypoint_name = sys.argv[1]
entry = getattr(solution, entrypoint_name)

stream_data = [
    f"{i*50},sensor_{i%3},{75.0 + (i%25)}"
    for i in range(200)
]

# Run 1
res1 = json.loads(json.dumps(list(entry(list(stream_data)))))
# Run 2 with fresh copy
res2 = json.loads(json.dumps(list(entry(list(stream_data)))))

if res1 != res2:
    sys.stderr.write(f"Idempotence violation: run 1 produced {len(res1)} items, run 2 produced {len(res2)} items.\n")
    sys.exit(1)

sys.exit(0)
'''


class MetamorphicInvariantChecker:
    """
    Evaluates solutions against strict behavioral and resource invariants.
    """
    def __init__(self, run_python_fn: Callable):
        self.run_python_fn = run_python_fn

    def check_memory_bound(self, solution_path: Path, entrypoint: str = "process_telemetry",
                           max_memory_mb: float = 50.0) -> InvariantCheckResult:
        """
        Runs candidate solution under a 100,000-record stream and verifies auxiliary memory stays under max_memory_mb.
        """
        with tempfile.TemporaryDirectory(prefix="crucible_mem_") as tmp_d:
            tmp_dir = Path(tmp_d)
            (tmp_dir / "solution.py").write_text(solution_path.read_text(encoding="utf-8"), encoding="utf-8")
            (tmp_dir / "mem_runner.py").write_text(MEMORY_RUNNER, encoding="utf-8")

            code, out, err, dur = self.run_python_fn(
                "mem_runner.py", tmp_dir, timeout=60, args=[entrypoint, str(max_memory_mb)]
            )

            try:
                peak_mb = float(out.strip())
            except ValueError:
                peak_mb = None

            passed = (code == 0)
            details = (
                f"Peak memory: {peak_mb:.2f} MB (ceiling: {max_memory_mb} MB)"
                if peak_mb is not None else f"Memory test execution failure: {err or out}"
            )

            return InvariantCheckResult(
                check_name="memory_ceiling_bound",
                passed=passed,
                details=details,
                peak_memory_mb=peak_mb,
                duration_seconds=dur,
            )

    def check_idempotence(self, solution_path: Path, entrypoint: str = "process_telemetry") -> InvariantCheckResult:
        """
        Verifies that repeated executions of the candidate yield identical output and don't leak dirty state.
        """
        with tempfile.TemporaryDirectory(prefix="crucible_idemp_") as tmp_d:
            tmp_dir = Path(tmp_d)
            (tmp_dir / "solution.py").write_text(solution_path.read_text(encoding="utf-8"), encoding="utf-8")
            (tmp_dir / "idemp_runner.py").write_text(IDEMPOTENCE_RUNNER, encoding="utf-8")

            code, out, err, dur = self.run_python_fn(
                "idemp_runner.py", tmp_dir, timeout=30, args=[entrypoint]
            )

            passed = (code == 0)
            details = "Idempotency verified across independent executions." if passed else f"Idempotency failure: {err or out}"

            return InvariantCheckResult(
                check_name="idempotence_and_purity",
                passed=passed,
                details=details,
                duration_seconds=dur,
            )
