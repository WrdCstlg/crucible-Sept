"""
Crucible behavioural invariants: checks that example-based tests usually miss.

  1. IDEMPOTENCE & PURITY (wired into the pipeline with --invariants): calling the entrypoint twice with the same
     input must return the same result, and the entrypoint must not mutate its input. Refuses solutions that
     carry hidden state between calls (module-level caches, global accumulators).
  2. MEMORY CEILING (library only): peak traced allocation under a 100,000-record stream must stay below a limit.
     The built-in stream is telemetry-shaped, so this check is not wired into the generic pipeline.

Both run the candidate in the caller's sandbox via `run_python_fn`.
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

# Script template to verify idempotence and purity. Inputs come from inputs.json when present (any problem),
# otherwise from a built-in telemetry-style stream.
IDEMPOTENCE_RUNNER = r'''
import copy
import json
import os
import sys
import solution

entrypoint_name = sys.argv[1]
entry = getattr(solution, entrypoint_name)

if os.path.exists("inputs.json"):
    inputs = json.load(open("inputs.json", encoding="utf-8"))
else:
    inputs = [[f"{i*50},sensor_{i%3},{75.0 + (i%25)}" for i in range(200)]]

def canon(v):
    if not isinstance(v, (list, dict, str, int, float, bool, type(None), tuple)):
        v = list(v)
    return json.dumps(v, sort_keys=True, default=repr)

for n, item in enumerate(inputs):
    original = copy.deepcopy(item)
    first = canon(entry(copy.deepcopy(item)))
    second = canon(entry(copy.deepcopy(item)))
    if first != second:
        sys.stderr.write(f"Idempotence violation on input #{n}: a second call with the same input returned a "
                         f"different result (hidden state carried between calls).\n")
        sys.exit(1)
    probe = copy.deepcopy(item)
    entry(probe)
    if probe != original:
        sys.stderr.write(f"Purity violation on input #{n}: the entrypoint mutated its input.\n")
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

    def check_idempotence(self, solution_path: Path, entrypoint: str = "process_telemetry",
                          inputs: Optional[list] = None) -> InvariantCheckResult:
        """
        Verifies that repeated calls with identical input return identical output (no state leaking between calls)
        and that the entrypoint does not mutate its input. `inputs`: a list of entrypoint arguments (JSON values).
        """
        with tempfile.TemporaryDirectory(prefix="crucible_idemp_") as tmp_d:
            tmp_dir = Path(tmp_d)
            (tmp_dir / "solution.py").write_text(solution_path.read_text(encoding="utf-8"), encoding="utf-8")
            (tmp_dir / "idemp_runner.py").write_text(IDEMPOTENCE_RUNNER, encoding="utf-8")
            if inputs is not None:
                (tmp_dir / "inputs.json").write_text(json.dumps(inputs), encoding="utf-8")

            code, out, err, dur = self.run_python_fn(
                "idemp_runner.py", tmp_dir, timeout=60, args=[entrypoint]
            )

            passed = (code == 0)
            details = "Idempotency verified across independent executions." if passed else f"Idempotency failure: {err or out}"

            return InvariantCheckResult(
                check_name="idempotence_and_purity",
                passed=passed,
                details=details,
                duration_seconds=dur,
            )
