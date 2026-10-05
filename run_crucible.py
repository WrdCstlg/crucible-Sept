import argparse
import sys
import os
import asyncio
import shutil
import subprocess
import re
import time
import json
import ast
import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field
from google.antigravity import Agent, LocalAgentConfig

try:
    from google.antigravity.hooks import policy
    HAS_POLICY = True
except ImportError:
    policy = None
    HAS_POLICY = False

from crucible.contract import audit_contract, BLOCKED_MODULES
from crucible.mutation import MutationSlaughterGate
from crucible.invariants import MetamorphicInvariantChecker
from crucible.sandbox import Sandbox, SandboxUnavailable, default_sandbox, deterministic_env, docker_available  # noqa: F401

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

@dataclass
class BranchResult:
    name: str
    paradigm: str
    exit_code: int
    status: str
    duration_seconds: float
    stdout: str
    stderr: str
    solution_size_bytes: int = 0
    advisory: list = field(default_factory=list)  # outcomes of non-blocking suites; never affect the verdict

def extract_code(text: str) -> str:
    match = re.search(r'```(?:python)?\s*(.*?)```', text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text.strip()


# ── Deterministic, isolated execution ──────────────────────────────────
# Every child process that can influence a verdict (acceptance cases, arena suites, suite admission, mutation gate)
# runs through crucible.sandbox: by default a fresh, digest-pinned Docker container with no network, a read-only
# filesystem, no host secrets and resource limits, seeded with PYTHONHASHSEED=0 and random.seed(0). What an
# environment cannot fix is code that depends on wall-clock time or machine speed; suite admission guards against
# that by requiring identical outcomes across repeated runs against the reference solution.
def run_python(script: str, cwd: Path, timeout: int = 120, deterministic: bool = True, args: list | None = None,
               sandbox: Sandbox | None = None) -> tuple[int, str, str, float]:
    """Runs `python <script> [*args]` in cwd inside the (default) sandbox. Exit code 124 means timeout."""
    return (sandbox or default_sandbox()).run(script, cwd, timeout=timeout, deterministic=deterministic, args=args)



def load_acceptance_cases(path: str) -> list[dict]:
    """Loads human-written acceptance cases: a JSON list of {"id", "input" (or "lines"), "expected"}."""
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    normalized = []
    for i, c in enumerate(cases, 1):
        if "expected" not in c or ("input" not in c and "lines" not in c):
            raise ValueError(f"acceptance case #{i} needs 'input' (or 'lines') and 'expected'")
        normalized.append({"id": str(c.get("id", f"case_{i}")), "input": c.get("input", c.get("lines")),
                           "expected": c["expected"]})
    return normalized


# The synthesis agent explains; it never decides. Pass/fail and promotion come only from deterministic checks.
SYNTHESIS_SYSTEM = (
    "You review test results for competing implementations. Pass/fail and promotion were already decided by "
    "deterministic checks and are final: do not accept, reject, rank or recommend discarding any candidate, and do "
    "not declare winners. Explain, citing the logs, why each failing candidate failed and what it should change, so "
    "the next round can fix it."
)

# Runs inside a candidate's folder. Results are compared as canonical JSON, so types count: true is not 1, 1 is not 1.0.
ACCEPTANCE_RUNNER = r'''
import json, sys
import solution
entry = getattr(solution, sys.argv[1])
cases = json.load(open("acceptance_cases.json", encoding="utf-8"))
canon = lambda v: json.dumps(v, sort_keys=True)
failed = []
for c in cases:
    try:
        got = json.loads(json.dumps(entry(c["input"])))
    except Exception as e:
        failed.append({"id": c["id"], "error": f"{type(e).__name__}: {e}"[:300]})
        continue
    if canon(got) != canon(c["expected"]):
        failed.append({"id": c["id"], "expected": c["expected"], "got": got})
print(json.dumps({"cases": len(cases), "failed": failed})[:4000])
sys.exit(1 if failed else 0)
'''


def _create_locked_down_agent_config(system_instructions: str, temp_dir: str) -> LocalAgentConfig:
    """
    Creates an agent configuration with strict sandboxing:
      1. Isolated ephemeral workspace (empty temp directory).
      2. Empty tool list (no tools provided).
      3. policy.deny_all() to deny any implicit file read/write, bash, or subagent tools.
    
    Fails closed if the SDK security policy module is unavailable.
    """
    if not HAS_POLICY or policy is None or not hasattr(policy, "deny_all"):
        raise RuntimeError(
            "Security lockdown failure: google.antigravity.hooks.policy.deny_all is required "
            "to enforce agent lockdown, but could not be loaded. Refusing to run agent with unverified security posture."
        )
    return LocalAgentConfig(
        system_instructions=system_instructions,
        workspaces=[temp_dir],
        tools=[],
        policies=[policy.deny_all()],
    )


# Mock mode: synthetic LLM responses for offline pipeline validation
MOCK_SOLUTIONS = {
    "Micro-batching with dictionary state aggregation": """
import collections

def process_telemetry(stream):
    batch_size = 1000
    state = collections.defaultdict(list)
    cascades = []
    batch = []
    for record in stream:
        batch.append(record)
        if len(batch) >= batch_size:
            for ts, sensor, temp in batch:
                state[sensor].append((ts, temp))
            batch = []
    for ts, sensor, temp in batch:
        state[sensor].append((ts, temp))
    for sensor, readings in state.items():
        for i, (ts, temp) in enumerate(readings):
            if temp >= 95.0:
                for j in range(i + 1, len(readings)):
                    t2, temp2 = readings[j]
                    if t2 - ts > 500:
                        break
                    if temp2 >= 90.0:
                        cascades.append({"trigger": sensor, "ts": ts, "cascade_ts": t2})
    return cascades
""",
    "Zero-copy memory-mapped file processing": """
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
""",
    "Streaming Finite-State Machine with a bounded ring buffer": """
import collections

def process_telemetry(stream):
    TRIGGER_THRESHOLD = 95.0
    CASCADE_THRESHOLD = 90.0
    CASCADE_WINDOW_MS = 500
    active_triggers = collections.deque(maxlen=1024)
    cascades = []
    for timestamp_ms, sensor_id, temperature_c in stream:
        while active_triggers and (timestamp_ms - active_triggers[0][0]) > CASCADE_WINDOW_MS:
            active_triggers.popleft()
        if temperature_c >= CASCADE_THRESHOLD and active_triggers:
            for trigger_ts, trigger_sensor, trigger_temp in active_triggers:
                if sensor_id != trigger_sensor:
                    cascades.append({
                        "trigger_timestamp_ms": trigger_ts,
                        "trigger_sensor": trigger_sensor,
                        "trigger_temp_c": trigger_temp,
                        "cascade_timestamp_ms": timestamp_ms,
                        "cascade_sensor": sensor_id,
                        "cascade_temp_c": temperature_c,
                        "latency_ms": timestamp_ms - trigger_ts,
                    })
        if temperature_c >= TRIGGER_THRESHOLD:
            active_triggers.append((timestamp_ms, sensor_id, temperature_c))
    return cascades
""",
}

MOCK_TEST_HARNESS = """
import sys
import solution

def test_basic():
    stream = [
        (1000, "cpu0", 96.0),
        (1200, "cpu1", 91.0),
        (1600, "cpu2", 70.0),
        (5000, "gpu0", 97.0),
        (5400, "gpu1", 92.0),
    ]
    result = solution.process_telemetry(stream)
    assert isinstance(result, list), f"Expected list, got {type(result)}"
    assert len(result) >= 1, f"Expected at least 1 cascade, got {len(result)}"
    print(f"Test 1 (Basic Cascade): PASS - {len(result)} cascade(s) detected")

def test_no_cascade():
    stream = [
        (1000, "cpu0", 80.0),
        (2000, "cpu1", 85.0),
    ]
    result = solution.process_telemetry(stream)
    assert isinstance(result, list), f"Expected list, got {type(result)}"
    assert len(result) == 0, f"Expected 0 cascades in cold stream, got {len(result)}"
    print("Test 2 (No Cascade): PASS")

def test_window_expiry():
    stream = [
        (1000, "cpu0", 96.0),
        (2000, "cpu1", 91.0),
    ]
    result = solution.process_telemetry(stream)
    assert isinstance(result, list), f"Expected list, got {type(result)}"
    assert len(result) == 0, f"Expected 0 cascades (outside 500ms window), got {len(result)}"
    print("Test 3 (Window Expiry): PASS")

if __name__ == "__main__":
    test_basic()
    test_no_cascade()
    test_window_expiry()
    print("ALL TESTS PASSED. EXIT CODE 0.")
    sys.exit(0)
"""

# Round 2 of mock mode: an exact-output suite. It pins every field of every cascade on boundary streams (95.0/90.0
# thresholds, 500 vs 501 ms window, same-sensor, fan-in, expiry), so the mutation gate admits it.
MOCK_STRONG_TEST_HARNESS = """
import sys
import solution

K = ("trigger_timestamp_ms", "trigger_sensor", "trigger_temp_c", "cascade_timestamp_ms", "cascade_sensor",
     "cascade_temp_c", "latency_ms")
CASES = {
    "mixed": ([(1000, "cpu0", 96.0), (1200, "cpu1", 91.0), (1600, "cpu2", 70.0), (5000, "gpu0", 97.0), (5400, "gpu1", 92.0)],
              [(1000, "cpu0", 96.0, 1200, "cpu1", 91.0, 200), (5000, "gpu0", 97.0, 5400, "gpu1", 92.0, 400)]),
    "exact_boundaries": ([(1000, "cpu0", 95.0), (1500, "cpu1", 90.0)], [(1000, "cpu0", 95.0, 1500, "cpu1", 90.0, 500)]),
    "window_plus_one": ([(1000, "cpu0", 95.0), (1501, "cpu1", 90.0)], []),
    "below_trigger": ([(1000, "cpu0", 94.9), (1100, "cpu1", 99.0)], []),
    "below_cascade": ([(1000, "cpu0", 96.0), (1100, "cpu1", 89.9)], []),
    "same_sensor": ([(1000, "cpu0", 96.0), (1200, "cpu0", 91.0)], []),
    "fan_in": ([(1000, "a", 96.0), (1100, "b", 97.0), (1300, "c", 91.0)],
               [(1000, "a", 96.0, 1100, "b", 97.0, 100), (1000, "a", 96.0, 1300, "c", 91.0, 300),
                (1100, "b", 97.0, 1300, "c", 91.0, 200)]),
    "empty": ([], []),
    "expiry": ([(0, "a", 96.0), (400, "b", 96.0), (800, "c", 91.0)],
               [(0, "a", 96.0, 400, "b", 96.0, 400), (400, "b", 96.0, 800, "c", 91.0, 400)]),
}
failed = 0
for name, (stream, rows) in CASES.items():
    expected = [dict(zip(K, r)) for r in rows]
    got = list(solution.process_telemetry(list(stream)))
    if got != expected:
        failed += 1
        print(f"FAIL {name}: expected {expected}, got {got}")
    else:
        print(f"PASS {name}")
sys.exit(1 if failed else 0)
"""

# Mock round schedule: round 1 is the weak suite, every later round the strong one.
MOCK_HARNESS_BY_ROUND = {1: MOCK_TEST_HARNESS}

# Inputs only (no expected values): used by the mutation gate to discard equivalent mutants in mock mode.
MOCK_EQUIVALENCE_CORPUS = [
    [[1000, "cpu0", 96.0], [1200, "cpu1", 91.0], [1600, "cpu2", 70.0], [5000, "gpu0", 97.0], [5400, "gpu1", 92.0]],
    [[1000, "cpu0", 95.0], [1500, "cpu1", 90.0]], [[1000, "cpu0", 95.0], [1501, "cpu1", 90.0]],
    [[1000, "cpu0", 94.9], [1100, "cpu1", 99.0]], [[1000, "cpu0", 96.0], [1100, "cpu1", 89.9]],
    [[1000, "cpu0", 96.0], [1200, "cpu0", 91.0]], [[1000, "a", 96.0], [1100, "b", 97.0], [1300, "c", 91.0]], [],
    [[0, "a", 96.0], [400, "b", 96.0], [800, "c", 91.0]],
    [[t * 37, f"s{t % 4}", 85.0 + (t * 7) % 15] for t in range(200)],
]

MOCK_SYNTHESIS = (
    "MOCK SYNTHESIS: This is a synthetic synthesis report generated in mock mode. "
    "In live mode, a Lead Systems Architect LLM agent reviews the raw stdout/stderr logs "
    "from each branch execution, identifies the root cause of each failure, and provides "
    "actionable architectural feedback for the next tournament iteration."
)


class CrucibleOrchestrator:
    DEFAULT_ENTRYPOINT = "process_telemetry"
    REQUIRED_ENTRYPOINT = "process_telemetry"

    VERDICT_POLICIES = ("deterministic", "legacy")

    def __init__(self, problem_statement: str, paradigms: list[str], workspace_dir: str = ".crucible_workspace", mock_mode: bool = False, entrypoint: str = "process_telemetry", output_dir: str | None = None, force_iterations: int = 1,
                 verdict_policy: str = "deterministic", acceptance_cases: list[dict] | None = None,
                 reference_solution: str | None = None, stability_runs: int = 3, allow_advisory_only: bool = False,
                 mutation_gate: bool | None = None, mutation_threshold: float = 0.60,
                 equivalence_corpus: list | None = None, invariants: bool = False, sandbox: Sandbox | None = None):
        """
        Verdict policies:
          deterministic  Human-written acceptance cases always decide. An AI-written test suite may also decide, but only
                         once (1) the trusted reference solution passes it in every one of `stability_runs` runs and
                         (2) it kills at least `mutation_threshold` of the viable mutants of that reference (the mutation
                         gate, on by default whenever a reference exists). Otherwise it is quarantined (it rejects the
                         reference, its outcome varies, or it is too weak to tell broken code from correct code) or
                         advisory (no reference to check it against). Advisory and quarantined suites are still run and
                         reported; they never block.
          legacy         Every AI-written suite blocks (the behaviour before 2026-09-29). Kept to reproduce recorded runs.

        Sandbox: every verdict-bearing process runs in `sandbox` (default: crucible.sandbox.default_sandbox(), i.e.
        Docker). If that backend is unavailable the constructor raises SandboxUnavailable; it never degrades silently.
        """
        if verdict_policy not in self.VERDICT_POLICIES:
            raise ValueError(f"verdict_policy must be one of {self.VERDICT_POLICIES}")
        if (verdict_policy == "deterministic" and not mock_mode and not acceptance_cases and not reference_solution
                and not allow_advisory_only):
            raise ValueError(
                "Deterministic verdicts need ground truth: pass human-written acceptance cases (--acceptance-cases) "
                "and/or a trusted reference solution (--reference). To run anyway with AI-written tests as advisory "
                "only, pass --advisory-only (then only the AST gate can reject a candidate).")
        has_reference = bool(reference_solution) or mock_mode
        if mutation_gate is None:
            mutation_gate = verdict_policy == "deterministic" and has_reference
        if mutation_gate and verdict_policy == "deterministic" and not has_reference:
            raise ValueError("The mutation gate mutates the trusted reference: pass --reference, or --no-mutation-gate.")
        if not 0.0 < mutation_threshold <= 1.0:
            raise ValueError("mutation_threshold must be in (0, 1]")
        self.sandbox = sandbox or default_sandbox()
        if self.sandbox.backend == "docker":
            ok, detail = docker_available()
            if not ok:
                raise SandboxUnavailable(
                    f"Docker sandbox unavailable ({detail}). Refusing to run untrusted code without isolation. "
                    f"Start Docker, or opt in explicitly with --unsafe-subprocess-sandbox.")
        self.problem_statement = problem_statement
        self.paradigms = paradigms
        self.mock_mode = mock_mode
        self.entrypoint = entrypoint
        self.force_iterations = force_iterations
        self.verdict_policy = verdict_policy
        self.acceptance_cases = acceptance_cases or []
        self.reference_solution = str(Path(reference_solution).resolve()) if reference_solution else None
        self.stability_runs = max(1, stability_runs)
        self.mutation_gate = bool(mutation_gate) and verdict_policy == "deterministic"
        self.mutation_threshold = mutation_threshold
        # Inputs for discarding equivalent mutants: explicit corpus, plus every acceptance case's input.
        corpus = list(equivalence_corpus or []) + [c["input"] for c in self.acceptance_cases]
        if not corpus and mock_mode:
            corpus = MOCK_EQUIVALENCE_CORPUS
        self.equivalence_corpus = corpus
        self.invariants = invariants
        self.suite_admission: list[dict] = []
        self.workspace = Path(workspace_dir).resolve()
        self.project_root = self.workspace.parent if self.workspace.name == ".crucible_workspace" else Path.cwd().resolve()
        
        # Isolate mock output into .crucible_mock to prevent polluting repo audit trail
        if output_dir:
            self.output_dir = Path(output_dir).resolve()
        elif self.mock_mode:
            self.output_dir = self.project_root / ".crucible_mock"
        else:
            self.output_dir = self.project_root

        self.deployments_dir = self.output_dir / "deployments"
        self.artifacts_dir = self.output_dir / "artifacts"
        self.results_path = self.output_dir / "results.json"
        self.branches = []
        self.test_suites: list[Path] = []
        self.deployments_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        self.run_id = f"crucible-{int(time.time())}"
        self.telemetry = {
            "schema_version": "1.3.0",
            "run_id": self.run_id,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "end_time": None,
            "total_duration_seconds": None,
            "problem_statement": self.problem_statement,
            "paradigms": self.paradigms,
            "configuration": {
                "mode": "mock" if self.mock_mode else "live",
                "entrypoint": self.entrypoint,
                "force_iterations": self.force_iterations,
                "timeout_seconds": 120,
                "sandbox_engine": self.sandbox.backend,
                "sandbox": self.sandbox.describe(),
                "verifiers": [
                    "deterministic_exit_code_zero",
                    "120s_watchdog_kill",
                    "ast_entrypoint_contract",
                    "ast_import_guard",
                    "cumulative_regression_gate"
                ] + (["human_acceptance_cases", "suite_admission_vs_reference", "deterministic_environment"]
                     if verdict_policy == "deterministic" else [])
                  + (["adversarial_mutation_slaughter_gate"] if self.mutation_gate else [])
                  + (["idempotence_invariant"] if invariants else []),
                "verdict_policy": {
                    "name": verdict_policy,
                    "acceptance_cases": len(self.acceptance_cases),
                    "reference_solution_sha256": (hashlib.sha256(Path(self.reference_solution).read_bytes()).hexdigest()
                                                  if self.reference_solution else ("mock reference" if mock_mode else None)),
                    "stability_runs": self.stability_runs,
                    "mutation_gate": self.mutation_gate,
                    "mutation_threshold": self.mutation_threshold if self.mutation_gate else None,
                    "equivalence_corpus_inputs": len(self.equivalence_corpus) if self.mutation_gate else None,
                    "environment": "PYTHONHASHSEED=0 and random.seed(0) in every verdict-bearing process"
                                   if verdict_policy == "deterministic" else "unseeded (legacy)",
                }
            },
            "summary": {
                "status": "INITIALIZED",
                "survived": False,
                "total_iterations_run": 0,
                "total_evaluations": 0,
                "passed_evaluations": 0,
                "failed_evaluations": 0,
                "timeout_evaluations": 0,
                "winning_branches": [],
                "deployed_artifacts": []
            },
            "iterations": []
        }

    def _sanitize_paths(self, text: str) -> str:
        """Sanitizes host-specific absolute paths into relative POSIX paths."""
        if not text:
            return ""
        root_str = str(self.project_root.resolve())
        text = text.replace(root_str, ".")
        text = text.replace(root_str.replace("\\", "/"), ".")
        text = text.replace(".\\.crucible_workspace", "./.crucible_workspace")
        text = text.replace(".\\deployments", "./deployments")
        # Sanitize file:/// URL paths (encoded and decoded)
        text = re.sub(r'file:///[A-Za-z]:/[^"\'<>\s)]*?(?:\.crucible_workspace)', r'./.crucible_workspace', text)
        text = re.sub(r'file:///[A-Za-z]:/[^"\'<>\s)]*?Project%20Crucible/?', r'', text)
        text = re.sub(r'file:///[A-Za-z]:/[^"\'<>\s)]*?Project Crucible/?', r'', text)
        # Sanitize Windows drive-letter paths (single and double-escaped backslashes, forward slashes)
        text = re.sub(r'[A-Za-z]:(?:\\\\|\\|/)[^"\'\n\r]*?\.crucible_workspace', r'./.crucible_workspace', text)
        text = re.sub(r'[A-Za-z]:(?:\\\\|\\|/)[^"\'\n\r]*?Project Crucible', r'.', text)
        return text

    async def run(self, max_iterations=3):
        self._prepare_workspace()
        if self.mock_mode and self.verdict_policy == "deterministic" and not self.reference_solution:
            # Mock mode's trusted reference: the streaming FSM mock solution, adapted to the configured entrypoint.
            ref = self.workspace / "_mock_reference.py"
            fsm = MOCK_SOLUTIONS["Streaming Finite-State Machine with a bounded ring buffer"]
            ref.write_text(fsm.replace("def process_telemetry(", f"def {self.entrypoint}("), encoding="utf-8")
            self.reference_solution = str(ref)
        feedback = ""
        start_wall_time = time.time()
        overall_status = "FAILED"
        survived = False
        winning_branch_names = []
        deployed_artifacts = []
        
        try:
            for iteration in range(1, max_iterations + 1):
                print(f"\n[TOURNAMENT ITERATION {iteration}/{max_iterations}]")
                print(">> Phase 1: Generating Combatants (Decoupled Generators, Zero Tool Permissions)")
                
                # Wipe previous branches for the new round
                self.branches = []
                
                for i, paradigm in enumerate(self.paradigms, 1):
                    await self._generate_branch(i, paradigm, feedback)
                    if not self.mock_mode:
                        await asyncio.sleep(2)
                    
                print(f"\n>> Phase 2: Generating Arena Test Harness (Iteration {iteration})")
                current_test_script = await self._generate_test_harness(iteration)
                self.test_suites.append(current_test_script)
                test_size = current_test_script.stat().st_size if current_test_script.exists() else 0
                admission = self._admit_suite(current_test_script)
                self.suite_admission.append(admission)
                print(f"   Suite admission: {admission['decision'].upper()} ({admission['reason']})")
                blocking = [s for s, a in zip(self.test_suites, self.suite_admission) if a["decision"] == "admitted"]
                advisory = [s for s, a in zip(self.test_suites, self.suite_admission) if a["decision"] != "admitted"]

                print(f"\n>> Phase 3: The Arena ({len(self.acceptance_cases)} acceptance case(s), "
                      f"{len(blocking)} blocking suite(s), {len(advisory)} advisory suite(s))")
                results = await self._execute_arena(blocking, advisory)
                self._save_round(iteration, current_test_script, admission)
                
                print("\n>> Phase 4: Ruthless Synthesis")
                synthesis_report = await self._synthesize_results(results)
                print(synthesis_report)
                
                # Record iteration telemetry
                iter_data = {
                    "iteration": iteration,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "test_harness": {
                        "path": f"arena_test_iter_{iteration}.py",
                        "size_bytes": test_size,
                        "cumulative_suites_enforced": len(blocking),
                        "admission": admission,
                        "blocking_suites": [s.name for s in blocking],
                        "advisory_suites": [s.name for s in advisory],
                    },
                    "branches": [
                        {
                            "name": r.name,
                            "paradigm": r.paradigm,
                            "exit_code": r.exit_code,
                            "status": r.status,
                            "duration_seconds": r.duration_seconds,
                            "solution_size_bytes": r.solution_size_bytes,
                            "stdout": self._sanitize_paths(r.stdout),
                            "stderr": self._sanitize_paths(r.stderr),
                            "advisory": r.advisory,
                        }
                        for r in results
                    ],
                    "synthesis_report": self._sanitize_paths(synthesis_report)
                }
                self.telemetry["iterations"].append(iter_data)
                
                # Check if any branch survived all cumulative suites
                winners = [r for r in results if r.exit_code == 0]
                if winners and iteration >= self.force_iterations:
                    overall_status = "PASSED"
                    survived = True
                    winning_branch_names = [w.name for w in winners]
                    print(f"\nCRUCIBLE SURVIVED in Iteration {iteration}! {len(winners)} branch(es) passed all {len(self.test_suites)} cumulative suites.")
                    timestamp = int(time.time())
                    for winner in winners:
                        src_solution = self.workspace / winner.name / "solution.py"
                        dest_filename = f"winner_{winner.name}_{timestamp}.py"
                        dest_path = self.deployments_dir / dest_filename
                        shutil.copy(src_solution, dest_path)
                        try:
                            rel_path = dest_path.resolve().relative_to(self.project_root.resolve()).as_posix()
                        except ValueError:
                            rel_path = dest_path.name
                        deployed_artifacts.append(rel_path)
                        print("\n" + "=" * 80)
                        print("PRODUCTION ARTIFACT PERSISTED")
                        print(f"   Branch:      {winner.name}")
                        print(f"   Source:      {self._sanitize_paths(str(src_solution))}")
                        print(f"   Destination: {self._sanitize_paths(str(dest_path.resolve()))}")
                        print("=" * 80 + "\n")
                    break
                elif winners:
                    print(f"\n[Iteration {iteration} Survivor Notice] {len(winners)} branch(es) passed, but --force-iterations={self.force_iterations} mandates proceeding to Iteration {iteration+1} for cumulative adversarial hardening.")
                    feedback = (
                        f"ITERATION {iteration} CUMULATIVE SURVIVOR NOTICE:\n"
                        f"{len(winners)} branch(es) passed current suites, but the Crucible is forcing multi-round adversarial verification.\n"
                        f"HERE IS THE RUTHLESS SYNTHESIS REPORT:\n{synthesis_report}\n\n"
                        f"Refine your implementation to guarantee survival against subsequent, more aggressive adversarial test harnesses."
                    )
                else:
                    print("\nAll branches failed. Feeding Synthesis report back to the agents for the next round...")
                    feedback = (
                        f"PREVIOUS ARENA ATTEMPT FAILED ENTIRELY. HERE IS THE RUTHLESS SYNTHESIS REPORT:\n{synthesis_report}\n\n"
                        f"You MUST read this report, identify why your previous code failed the test suite, and FIX THE BUGS. "
                        f"Output the complete, corrected Python code."
                    )
                    
                    if iteration == max_iterations:
                        print("\nMaximum iterations reached. The agents failed to solve the problem.")
                        overall_status = "FAILED"
        finally:
            total_duration = round(time.time() - start_wall_time, 3)
            self._persist_telemetry(
                status=overall_status,
                survived=survived,
                winners=winning_branch_names,
                deployed_artifacts=deployed_artifacts,
                total_duration=total_duration
            )

    def _persist_telemetry(self, status: str, survived: bool, winners: list[str], deployed_artifacts: list[str], total_duration: float):
        all_evals = [b for iter_entry in self.telemetry["iterations"] for b in iter_entry["branches"]]
        total_evals = len(all_evals)
        passed_evals = sum(1 for b in all_evals if b["exit_code"] == 0)
        timeout_evals = sum(1 for b in all_evals if b["exit_code"] == 124)
        unverified_evals = sum(1 for b in all_evals if b["status"] == "UNVERIFIED")
        failed_evals = total_evals - passed_evals
        
        self.telemetry["end_time"] = datetime.now(timezone.utc).isoformat()
        self.telemetry["total_duration_seconds"] = total_duration
        self.telemetry["summary"].update({
            "status": status,
            "survived": survived,
            "total_iterations_run": len(self.telemetry["iterations"]),
            "total_evaluations": total_evals,
            "passed_evaluations": passed_evals,
            "failed_evaluations": failed_evals,
            "timeout_evaluations": timeout_evals,
            "unverified_evaluations": unverified_evals,
            "winning_branches": winners,
            "deployed_artifacts": deployed_artifacts
        })
        
        # Write to results.json
        with open(self.results_path, "w", encoding="utf-8") as f:
            json.dump(self.telemetry, f, indent=2)
            
        # Write to timestamped audit log in artifacts/
        timestamp = int(time.time())
        audit_log_path = self.artifacts_dir / f"results_{timestamp}.json"
        with open(audit_log_path, "w", encoding="utf-8") as f:
            json.dump(self.telemetry, f, indent=2)
            
        print("\n" + "=" * 80)
        print("OBSERVABILITY TELEMETRY PERSISTED")
        print(f"   Dashboard Log: {self._sanitize_paths(str(self.results_path.resolve()))}")
        print(f"   Audit Archive: {self._sanitize_paths(str(audit_log_path.resolve()))}")
        print(f"   Run ID:        {self.run_id}")
        print(f"   Verdict:       {status} (Survived: {survived})")
        print(f"   Evaluations:   {total_evals} total | {passed_evals} passed | {failed_evals} failed | {timeout_evals} timeouts")
        print(f"   Total Runtime: {total_duration}s")
        print("=" * 80 + "\n")

    def _run(self, script: str, cwd: Path, *args: str, timeout: int = 120) -> tuple[int, str, str, float]:
        """Runs a verdict-bearing script in this run's sandbox; seeded unless the legacy policy is in force."""
        return self.sandbox.run(script, cwd, timeout=timeout, deterministic=self.verdict_policy == "deterministic",
                                args=list(args))

    def _admit_suite(self, suite_path: Path) -> dict:
        """Decides whether an AI-written suite may block candidates. Deterministic given the suite and the reference."""
        if self.verdict_policy == "legacy":
            return {"suite": suite_path.name, "decision": "admitted", "reason": "legacy policy: every AI-written suite blocks"}
        if not self.reference_solution:
            return {"suite": suite_path.name, "decision": "advisory",
                    "reason": "no trusted reference to validate it against; reported, never blocking"}
        codes, tails = [], []
        for _ in range(self.stability_runs):
            with tempfile.TemporaryDirectory(prefix="crucible_admit_") as d:
                shutil.copy(suite_path, Path(d) / "arena_test.py")
                shutil.copy(self.reference_solution, Path(d) / "solution.py")
                code, out, err, _ = self._run("arena_test.py", Path(d))
                codes.append(code)
                tails.append(self._sanitize_paths(((err or out).strip().splitlines() or [""])[-1])[:200])
        if all(c == 0 for c in codes):
            if self.mutation_gate:
                gate = MutationSlaughterGate(lambda *a, **k: self.sandbox.run(*a, **k), threshold=self.mutation_threshold)
                mut_res = gate.evaluate_suite(suite_path, Path(self.reference_solution),
                                              equivalence_corpus=self.equivalence_corpus or None,
                                              entrypoint=self.entrypoint)
                record = {"suite": suite_path.name, "reference_exit_codes": codes,
                          "mutation_slaughter": {**mut_res.summary(), "passed": mut_res.passed_gate,
                                                 "killed": mut_res.killed_mutants, "total": mut_res.total_mutants}}
                if not mut_res.passed_gate:
                    return {**record, "decision": "quarantined", "reason": f"QUARANTINED (TAUTOLOGICAL): {mut_res.reason}"}
                return {**record, "decision": "admitted",
                        "reason": f"the trusted reference passes it in all {len(codes)} runs; {mut_res.reason}"}
            return {"suite": suite_path.name, "decision": "admitted", "reference_exit_codes": codes,
                    "reason": f"the trusted reference passes it in all {len(codes)} runs (mutation gate disabled)"}
        if all(c != 0 for c in codes):
            return {"suite": suite_path.name, "decision": "quarantined", "reference_exit_codes": codes,
                    "reason": "the trusted reference fails it, so at least one expectation is wrong",
                    "reference_failure": tails[-1]}
        return {"suite": suite_path.name, "decision": "quarantined", "reference_exit_codes": codes,
                "reason": f"unstable: the reference's outcome varied across runs {codes}"}

    def _save_round(self, iteration: int, suite_path: Path, admission: dict):
        """Keeps every round's candidates, suite and admission decision so the run can be replayed without any model."""
        round_dir = self.output_dir / "rounds" / f"round{iteration}"
        round_dir.mkdir(parents=True, exist_ok=True)
        if self.acceptance_cases and not (round_dir.parent / "acceptance_cases.json").exists():
            (round_dir.parent / "acceptance_cases.json").write_text(json.dumps(self.acceptance_cases, indent=2), encoding="utf-8")
        if self.reference_solution and not (round_dir.parent / "reference_solution.py").exists():
            shutil.copy(self.reference_solution, round_dir.parent / "reference_solution.py")
        for branch_dir in self.branches:
            if (branch_dir / "solution.py").exists():
                shutil.copy(branch_dir / "solution.py", round_dir / f"{branch_dir.name}.py")
        if suite_path.exists():
            shutil.copy(suite_path, round_dir / suite_path.name)
        (round_dir / "admission.json").write_text(json.dumps(admission, indent=2), encoding="utf-8")

    def _prepare_workspace(self):
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        self.workspace.mkdir(parents=True)
        with open(self.workspace / ".gitignore", "w", encoding="utf-8") as f:
            f.write("*\n")
        self.deployments_dir.mkdir(parents=True, exist_ok=True)

    async def _generate_branch(self, index: int, paradigm: str, feedback: str):
        branch_name = f"branch_{index}"
        branch_dir = self.workspace / branch_name
        if branch_dir.exists():
            shutil.rmtree(branch_dir)
        branch_dir.mkdir(parents=True)
        self.branches.append(branch_dir)
        
        if self.mock_mode:
            raw_code = MOCK_SOLUTIONS.get(paradigm, MOCK_SOLUTIONS[list(MOCK_SOLUTIONS.keys())[0]])
            code = raw_code.replace("def process_telemetry(", f"def {self.entrypoint}(")
            with open(branch_dir / "solution.py", "w", encoding="utf-8") as f:
                f.write(code)
            print(f"   [+] Generated {branch_name} ({paradigm}) [MOCK]")
            return

        with tempfile.TemporaryDirectory(prefix="crucible_gen_") as gen_temp:
            config = _create_locked_down_agent_config(
                system_instructions=(
                    "You are an elite Python systems engineer. Output ONLY valid, executable Python code. "
                    "CRITICAL CONSTRAINTS: "
                    f"1. PRIMARY ENTRYPOINT: Your code MUST expose a primary top-level entrypoint named exactly: `def {self.entrypoint}(stream):` Do not use class wrappers. "
                    "2. RIGID STREAM CONTRACT: The stream parameter is an iterable yielding raw comma-separated lines: 'timestamp,sensor_id,temperature' (epoch milliseconds float/int, sensor string, temperature Celsius float). "
                    "3. DETECTION LOGIC: Lazily yield or return an iterable of cascade events (reading >=95.0C followed by reading >=90.0C within <=500.0ms on any sensor). "
                    "4. MEMORY EFFICIENCY: Enforce strict O(1) auxiliary memory consumption without unbounded queues or memory leaks under high-volume streaming (500,000+ records). "
                    "5. NO TYPING INSTANTIATION: Do NOT instantiate typing objects at runtime (never write `Any()` or `Generator()`). "
                    f"6. ARCHITECTURAL PARADIGM: Implement the solution strictly following this paradigm: {paradigm}. "
                    "Enclose your final code in standard ```python ... ``` blocks without conversational commentary."
                ),
                temp_dir=gen_temp
            )
            prompt = f"Solve the following problem:\n{self.problem_statement}\n\nCRITICAL CONSTRAINT: You MUST use this exact architectural paradigm: {paradigm}"
            if feedback:
                prompt += f"\n\n{feedback}"
                
            async with Agent(config) as agent:
                response = await agent.chat(prompt)
                code = extract_code(await response.text())
                with open(branch_dir / "solution.py", "w", encoding="utf-8") as f:
                    f.write(code)
        print(f"   [+] Generated {branch_name} ({paradigm})")

    async def _generate_test_harness(self, iteration: int = 1) -> Path:
        test_path = self.workspace / f"arena_test_iter_{iteration}.py"

        if self.mock_mode:
            template = MOCK_HARNESS_BY_ROUND.get(iteration, MOCK_STRONG_TEST_HARNESS)
            harness = template.replace("solution.process_telemetry(", f"solution.{self.entrypoint}(")
            with open(test_path, "w", encoding="utf-8") as f:
                f.write(harness)
            return test_path

        with tempfile.TemporaryDirectory(prefix="crucible_qa_") as qa_temp:
            config = _create_locked_down_agent_config(
                system_instructions=(
                    "You are an adversarial QA systems engineer writing an uncompromising Python test harness for an untrusted streaming module. "
                    "START YOUR CODE IMMEDIATELY WITH 'import solution'. "
                    "DO NOT print filenames like 'solution.py' at the top of the file. "
                    "CRITICAL PROTOCOL RULES: "
                    "1. RIGID STREAM CONTRACT: The input stream is an iterable yielding standard comma-separated lines: 'timestamp,sensor_id,temperature' where timestamp is float/int epoch milliseconds, sensor_id is string, and temperature is Celsius float. "
                    "DO NOT probe, accommodate, or guess multiple formats (NO try/except probing of alternative formats). If the candidate solution cannot parse this standard CSV format, it must fail immediately. "
                    f"2. RIGID CALL SIGNATURE: You MUST call `solution.{self.entrypoint}(stream)`. The return value must be an iterable yielding detected cascade event records/objects. "
                    "3. RIGID ADVERSARIAL STRESS TEST: You MUST include comprehensive edge cases (exact temperature boundaries, window boundary at 500ms vs 501ms, out-of-order jitter, causality inversion) AND a high-volume continuous streaming test emitting at least 500,000 records while verifying with tracemalloc that peak resident memory remains strictly bounded (O(1) auxiliary memory ceiling under 50.0 MB). "
                    "4. DETERMINISTIC EXIT: Print metrics to stdout and call sys.exit(0) if and only if all tests pass. Call sys.exit(1) on any test or memory failure. "
                    "5. GROUND TRUTH INTEGRITY: In synthetic data generation, any isolated spikes or background noise MUST NOT trigger cascade detection logic (e.g. ensure isolated spikes are separated from subsequent readings by at least the full window duration, or dynamically compute expected cascade counts from actual injected records rather than asserting uncalibrated hardcoded counts). "
                    "Enclose code in standard ```python ... ``` blocks."
                ),
                temp_dir=qa_temp
            )
            prompt = f"Write an adversarial test suite for this problem: {self.problem_statement}"
            async with Agent(config) as agent:
                response = await agent.chat(prompt)
                code = extract_code(await response.text())
                with open(test_path, "w", encoding="utf-8") as f:
                    f.write(code)
        return test_path


    # ── Deterministic AST Contract Enforcement ─────────────────────────────
    # These modules are blocked because untrusted LLM-generated code must not
    # be allowed to make outbound network connections, spawn child processes,
    # interact with the host filesystem outside its sandbox, or load native
    # C extensions that bypass Python-level memory protections.
    BLOCKED_MODULES = frozenset({
        "subprocess", "socket", "http", "urllib", "requests",
        "ctypes", "cffi", "signal", "multiprocessing",
    })

    @staticmethod
    def _audit_contract(source_path: Path, entrypoint: str | None = None, profile: str = "strict") -> tuple[bool, str]:
        """
        Zero-cost AST lint of a candidate before anything runs (see crucible/contract.py): entrypoint contract,
        blocked imports, and dynamic-execution / introspection escape hatches. A lint, not a security boundary:
        isolation comes from the sandbox. Profile 'v1' reproduces the checks used by the recorded pilots.

        Returns:
            (passed: bool, reason: str) - reason is empty on success.
        """
        if entrypoint is None:
            entrypoint = CrucibleOrchestrator.REQUIRED_ENTRYPOINT
        return audit_contract(source_path, entrypoint=entrypoint, profile=profile)


    def _run_acceptance(self, branch_dir: Path) -> tuple[int, str]:
        """Runs the human-written acceptance cases against one candidate. Returns (exit code, detail)."""
        (branch_dir / "acceptance_cases.json").write_text(json.dumps(self.acceptance_cases), encoding="utf-8")
        (branch_dir / "acceptance_runner.py").write_text(ACCEPTANCE_RUNNER, encoding="utf-8")
        code, out, err, _ = self._run_script(branch_dir, "acceptance_runner.py", self.entrypoint)
        summary = (out.strip().splitlines() or [""])[-1]
        return code, summary if summary.startswith("{") else (err or out)[-500:]

    def _run_script(self, cwd: Path, script: str, *args: str) -> tuple[int, str, str, float]:
        """Runs a verdict-bearing script in this run's sandbox (kept for subclasses and the experiment harness)."""
        return self._run(script, cwd, *args)

    async def _execute_arena(self, test_suites: list[Path], advisory_suites: list[Path] = ()) -> list[BranchResult]:
        """
        Judges each candidate. Order: AST gate, then human acceptance cases (decisive), then every blocking suite
        cumulatively (the first failure ends it). Advisory suites run afterwards for information only.
        """
        results = []
        for i, branch_dir in enumerate(self.branches):
            paradigm = self.paradigms[i] if i < len(self.paradigms) else "Unknown"
            print(f"   [>] Executing {branch_dir.name} ({paradigm}) against {len(test_suites)} suite(s)...")
            
            solution_file = branch_dir / "solution.py"
            solution_size = solution_file.stat().st_size if solution_file.exists() else 0
            
            # ── AST Pre-Execution Gate ──────────────────────────────────
            ast_passed, ast_reason = self._audit_contract(
                solution_file, entrypoint=self.entrypoint, profile="v1" if self.verdict_policy == "legacy" else "strict")
            if not ast_passed:
                print(f"       [x] AST REJECTED: {ast_reason[:80]}...")
                results.append(BranchResult(
                    name=branch_dir.name,
                    paradigm=paradigm,
                    exit_code=2,
                    status="AST_REJECTED",
                    duration_seconds=0.0,
                    stdout="",
                    stderr=ast_reason,
                    solution_size_bytes=solution_size
                ))
                continue

            cumulative_duration = 0.0
            cumulative_stdout = []
            cumulative_stderr = []
            branch_exit_code = 0
            branch_status = "PASS"

            # ── Fail closed: a promotion needs at least one decisive check ─
            if self.verdict_policy == "deterministic" and not self.acceptance_cases and not test_suites:
                branch_exit_code, branch_status = 3, "UNVERIFIED"
                cumulative_stderr.append("[No decisive check] No acceptance cases and no admitted suite: this candidate "
                                         "cannot be verified, so it cannot be promoted.")
                print("       [?] UNVERIFIED: no acceptance cases and no admitted suite")

            # ── Human acceptance cases: always decisive ────────────────
            elif self.acceptance_cases:
                code, detail = self._run_acceptance(branch_dir)
                if code != 0:
                    branch_exit_code = code
                    branch_status = "TIMEOUT" if code == 124 else "ACCEPTANCE_FAIL"
                    cumulative_stderr.append(f"[Acceptance cases]\n{self._sanitize_paths(detail)}")
                    print(f"       [-] Failed acceptance cases (Code: {code})")

            # ── Cumulative Regression Gate: admitted suites only ───────
            for idx, suite_path in enumerate(test_suites if branch_exit_code == 0 else [], 1):
                test_file_name = f"arena_test_suite_{idx}.py"
                shutil.copy(suite_path, branch_dir / test_file_name)
                code, out, err, duration = self._run_script(branch_dir, test_file_name)
                cumulative_duration += duration
                if out:
                    cumulative_stdout.append(f"[Test Suite {idx}]\n{out}")
                if err:
                    cumulative_stderr.append(f"[Test Suite {idx}]\n{err}")
                if code != 0:
                    branch_exit_code = code
                    branch_status = "TIMEOUT" if code == 124 else "FAIL"
                    print(f"       [-] Failed Suite {idx} (Code: {code}, Duration: {duration}s)")
                    break

            # ── Idempotence invariant (optional, decisive) ───────────────────
            if self.invariants and branch_exit_code == 0 and self.equivalence_corpus:
                checker = MetamorphicInvariantChecker(lambda *a, **k: self.sandbox.run(*a, **k))
                inv = checker.check_idempotence(solution_file, self.entrypoint, inputs=self.equivalence_corpus)
                if not inv.passed:
                    branch_exit_code, branch_status = 1, "INVARIANT_FAIL"
                    cumulative_stderr.append(f"[Invariant] {self._sanitize_paths(inv.details)[:500]}")
                    print("       [-] Failed idempotence invariant")

            # ── Advisory suites: reported, never blocking ──────────────
            advisory = []
            for suite_path in advisory_suites:
                shutil.copy(suite_path, branch_dir / f"advisory_{suite_path.name}")
                code, out, err, duration = self._run_script(branch_dir, f"advisory_{suite_path.name}")
                advisory.append({"suite": suite_path.name, "exit_code": code, "passed": code == 0,
                                 "tail": self._sanitize_paths(((err or out).strip().splitlines() or [""])[-1])[:200]})

            combined_stdout = "\n".join(cumulative_stdout)
            combined_stderr = "\n".join(cumulative_stderr)
            total_duration = round(cumulative_duration, 3)

            results.append(BranchResult(
                name=branch_dir.name,
                paradigm=paradigm,
                exit_code=branch_exit_code,
                status=branch_status,
                duration_seconds=total_duration,
                stdout=combined_stdout,
                stderr=combined_stderr,
                solution_size_bytes=solution_size,
                advisory=advisory,
            ))
            print(f"       Verdict: {branch_status} (Exit Code: {branch_exit_code}, Total Duration: {total_duration}s)")
        return results

    async def _synthesize_results(self, results: list[BranchResult]) -> str:
        log_payload = "ARENA EXECUTION LOGS:\n\n"
        for r in results:
            log_payload += f"--- {r.name} ({r.paradigm}) ---\nStatus: {r.status} | Exit Code: {r.exit_code} | Duration: {r.duration_seconds}s\nSTDOUT:\n{self._sanitize_paths(r.stdout)}\nSTDERR:\n{self._sanitize_paths(r.stderr)}\n\n"

        if self.mock_mode:
            survivors = [r for r in results if r.exit_code == 0]
            if survivors:
                return f"MOCK SYNTHESIS: {len(survivors)} branch(es) survived. Winners: {', '.join(r.name for r in survivors)}. Full log analysis is available in live mode."
            return MOCK_SYNTHESIS

        with tempfile.TemporaryDirectory(prefix="crucible_synth_") as synth_temp:
            config = _create_locked_down_agent_config(
                system_instructions=SYNTHESIS_SYSTEM,
                temp_dir=synth_temp
            )
            async with Agent(config) as agent:
                response = await agent.chat(log_payload)
                raw_synthesis = await response.text()
                return self._sanitize_paths(raw_synthesis)


def build_parser() -> argparse.ArgumentParser:
    """Builds and returns the CLI argument parser."""
    parser = argparse.ArgumentParser(description="The Crucible Protocol")
    parser.add_argument("problem", type=str, nargs="?", default="Parse a continuous 5GB telemetry stream to detect thermal throttling cascades (>=95C causing >=90C within 500ms).")
    parser.add_argument("--paradigms", nargs="+", default=["Micro-batching with dictionary state aggregation", "Zero-copy memory-mapped file processing", "Streaming Finite-State Machine with a bounded ring buffer"])
    parser.add_argument("--mock", action="store_true", help="Run with synthetic LLM responses (no API key required)")
    parser.add_argument("--entrypoint", type=str, default="process_telemetry", help="Required function name for the API contract (default: process_telemetry)")
    parser.add_argument("--output-dir", type=str, default=None, help="Directory for results.json and artifacts (default: project root in live mode, .crucible_mock in mock mode)")
    parser.add_argument("--force-iterations", type=int, default=1, help="Minimum number of tournament iterations to run before declaring victory (default: 1)")
    parser.add_argument("--max-iterations", type=int, default=3, help="Maximum number of tournament iterations to run (default: 3)")
    parser.add_argument("--verdict-policy", choices=CrucibleOrchestrator.VERDICT_POLICIES, default="deterministic",
                        help="deterministic (default): acceptance cases decide, AI-written suites only once validated "
                             "against --reference; legacy: every AI-written suite blocks (to reproduce old runs)")
    parser.add_argument("--acceptance-cases", type=str, default=None,
                        help="JSON list of human-written cases {id, input, expected}; always decisive")
    parser.add_argument("--reference", type=str, default=None,
                        help="Trusted reference solution; AI-written suites block only if it passes them every time")
    parser.add_argument("--stability-runs", type=int, default=3,
                        help="Times a suite must pass the reference, with identical outcomes, to be admitted (default: 3)")
    parser.add_argument("--advisory-only", action="store_true",
                        help="Run live without acceptance cases or a reference: AI-written suites are advisory only")
    gate = parser.add_mutually_exclusive_group()
    gate.add_argument("--mutation-gate", dest="mutation_gate", action="store_true", default=None,
                      help="Require the mutation gate (default: on automatically whenever a trusted reference exists)")
    gate.add_argument("--no-mutation-gate", dest="mutation_gate", action="store_false",
                      help="Disable the mutation gate: suites are admitted on the reference check alone (not recommended)")
    parser.add_argument("--mutation-threshold", type=float, default=0.60,
                        help="Minimum fraction of viable mutants a suite must kill to be admitted (default: 0.60)")
    parser.add_argument("--equivalence-corpus", type=str, default=None,
                        help="JSON list of entrypoint inputs (no expected values) used to discard equivalent mutants; "
                             "acceptance-case inputs are always added")
    parser.add_argument("--invariants", action="store_true",
                        help="Also require idempotence and input purity on the corpus/acceptance inputs (decisive)")
    parser.add_argument("--unsafe-subprocess-sandbox", action="store_true",
                        help="Run untrusted code as a plain host subprocess instead of a Docker container. "
                             "UNSAFE: no network, filesystem or memory isolation (secrets are still scrubbed)")
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    workspace_path = Path.cwd() / ".crucible_workspace"
    mode_label = "MOCK MODE" if args.mock else "LIVE MODE"
    print(f"Initializing Crucible [{mode_label}, verdict policy: {args.verdict_policy}] in: ./.crucible_workspace")

    effective_max_iterations = args.max_iterations
    if args.force_iterations > args.max_iterations:
        print(
            f"WARNING: --force-iterations ({args.force_iterations}) exceeds --max-iterations ({args.max_iterations}). "
            f"Automatically elevating max_iterations to {args.force_iterations} so survivors can be declared."
        )
        effective_max_iterations = args.force_iterations

    try:
        orchestrator = CrucibleOrchestrator(
            problem_statement=args.problem,
            paradigms=args.paradigms,
            workspace_dir=str(workspace_path),
            mock_mode=args.mock,
            entrypoint=args.entrypoint,
            output_dir=args.output_dir,
            force_iterations=args.force_iterations,
            verdict_policy=args.verdict_policy,
            acceptance_cases=load_acceptance_cases(args.acceptance_cases) if args.acceptance_cases else None,
            reference_solution=args.reference,
            stability_runs=args.stability_runs,
            allow_advisory_only=args.advisory_only,
            mutation_gate=args.mutation_gate,
            mutation_threshold=args.mutation_threshold,
            equivalence_corpus=(json.loads(Path(args.equivalence_corpus).read_text(encoding="utf-8"))
                                if args.equivalence_corpus else None),
            invariants=args.invariants,
            sandbox=Sandbox(backend="subprocess-unsafe") if args.unsafe_subprocess_sandbox else None,
        )
    except (ValueError, SandboxUnavailable) as e:
        parser.error(str(e))
    if orchestrator.sandbox.backend != "docker":
        print("WARNING: --unsafe-subprocess-sandbox: untrusted code runs on the host with no network, filesystem or "
              "memory isolation.")
    asyncio.run(orchestrator.run(max_iterations=effective_max_iterations))

