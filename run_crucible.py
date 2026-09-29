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
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from google.antigravity import Agent, LocalAgentConfig

try:
    from google.antigravity.hooks import policy
    HAS_POLICY = True
except ImportError:
    policy = None
    HAS_POLICY = False

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

def extract_code(text: str) -> str:
    match = re.search(r'```(?:python)?\s*(.*?)```', text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text.strip()


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

MOCK_SYNTHESIS = (
    "MOCK SYNTHESIS: This is a synthetic synthesis report generated in mock mode. "
    "In live mode, a Lead Systems Architect LLM agent reviews the raw stdout/stderr logs "
    "from each branch execution, identifies the root cause of each failure, and provides "
    "actionable architectural feedback for the next tournament iteration."
)


class CrucibleOrchestrator:
    DEFAULT_ENTRYPOINT = "process_telemetry"
    REQUIRED_ENTRYPOINT = "process_telemetry"

    def __init__(self, problem_statement: str, paradigms: list[str], workspace_dir: str = ".crucible_workspace", mock_mode: bool = False, entrypoint: str = "process_telemetry", output_dir: str | None = None, force_iterations: int = 1):
        self.problem_statement = problem_statement
        self.paradigms = paradigms
        self.mock_mode = mock_mode
        self.entrypoint = entrypoint
        self.force_iterations = force_iterations
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
            "schema_version": "1.1.0",
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
                "sandbox_engine": "isolated_subprocess",
                "verifiers": [
                    "deterministic_exit_code_zero",
                    "120s_watchdog_kill",
                    "ast_entrypoint_contract",
                    "ast_import_guard",
                    "cumulative_regression_gate"
                ]
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
                
                print(f"\n>> Phase 3: The Arena (Executing Across {len(self.test_suites)} Cumulative Test Suite(s))")
                results = await self._execute_arena(self.test_suites)
                
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
                        "cumulative_suites_enforced": len(self.test_suites)
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
                            "stderr": self._sanitize_paths(r.stderr)
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
        print(f"   Dashboard Log: {self.results_path.resolve()}")
        print(f"   Audit Archive: {audit_log_path.resolve()}")
        print(f"   Run ID:        {self.run_id}")
        print(f"   Verdict:       {status} (Survived: {survived})")
        print(f"   Evaluations:   {total_evals} total | {passed_evals} passed | {failed_evals} failed | {timeout_evals} timeouts")
        print(f"   Total Runtime: {total_duration}s")
        print("=" * 80 + "\n")

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
            harness = MOCK_TEST_HARNESS.replace("solution.process_telemetry(", f"solution.{self.entrypoint}(")
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
    def _audit_contract(source_path: Path, entrypoint: str | None = None) -> tuple[bool, str]:
        """
        Deterministic, zero-cost AST verification of a candidate solution.
        
        Enforces two structural invariants before any subprocess is spawned:
          1. ENTRYPOINT CONTRACT: A top-level function matching the required entrypoint name.
          2. IMPORT GUARD: Static check rejecting direct imports of blocked module families.
             Note: This is an accidental-import check, not an OS sandbox boundary.
        
        Returns:
            (passed: bool, reason: str) - reason is empty on success.
        """
        if entrypoint is None:
            entrypoint = CrucibleOrchestrator.REQUIRED_ENTRYPOINT

        try:
            source_code = source_path.read_text(encoding="utf-8")
        except Exception as e:
            return False, f"FILE READ ERROR: {e}"

        # --- Parse AST ---
        try:
            tree = ast.parse(source_code, filename=str(source_path))
        except SyntaxError as e:
            return False, f"SYNTAX ERROR (line {e.lineno}): {e.msg}"

        # --- Check 1: Entrypoint contract ---
        required_name = entrypoint
        has_entrypoint = any(
            isinstance(node, ast.FunctionDef) and node.name == required_name
            for node in ast.iter_child_nodes(tree)
        )
        if not has_entrypoint:
            return False, (
                "AST CONTRACT VIOLATION: Missing required top-level function "
                f"'def {required_name}(stream):'. "
                "Found top-level definitions: "
                + ", ".join(
                    f"{type(n).__name__}('{n.name}')"
                    for n in ast.iter_child_nodes(tree)
                    if hasattr(n, "name")
                )
            )

        # --- Check 2: Import guard ---
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_module = alias.name.split(".")[0]
                    if root_module in CrucibleOrchestrator.BLOCKED_MODULES:
                        return False, (
                            f"AST IMPORT VIOLATION (line {node.lineno}): "
                            f"Import of blocked module '{alias.name}'. "
                            f"Blocked module families: {sorted(CrucibleOrchestrator.BLOCKED_MODULES)}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_module = node.module.split(".")[0]
                    if root_module in CrucibleOrchestrator.BLOCKED_MODULES:
                        return False, (
                            f"AST IMPORT VIOLATION (line {node.lineno}): "
                            f"Import from blocked module '{node.module}'. "
                            f"Blocked module families: {sorted(CrucibleOrchestrator.BLOCKED_MODULES)}"
                        )

        return True, ""

    async def _execute_arena(self, test_suites: list[Path]) -> list[BranchResult]:
        """
        Executes each candidate solution against all cumulative test suites.
        A branch passes only if it achieves exit code 0 across every test suite.
        """
        results = []
        for i, branch_dir in enumerate(self.branches):
            paradigm = self.paradigms[i] if i < len(self.paradigms) else "Unknown"
            print(f"   [>] Executing {branch_dir.name} ({paradigm}) against {len(test_suites)} suite(s)...")
            
            solution_file = branch_dir / "solution.py"
            solution_size = solution_file.stat().st_size if solution_file.exists() else 0
            
            # ── AST Pre-Execution Gate ──────────────────────────────────
            ast_passed, ast_reason = self._audit_contract(solution_file, entrypoint=self.entrypoint)
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

            # ── Cumulative Regression Gate ─────────────────────────────
            for idx, suite_path in enumerate(test_suites, 1):
                test_file_name = f"arena_test_suite_{idx}.py"
                shutil.copy(suite_path, branch_dir / test_file_name)
                
                start_t = time.perf_counter()
                try:
                    process = subprocess.run(
                        [sys.executable, test_file_name],
                        cwd=branch_dir,
                        capture_output=True,
                        text=True,
                        timeout=120
                    )
                    duration = round(time.perf_counter() - start_t, 3)
                    code = process.returncode
                    out = process.stdout
                    err = process.stderr
                except subprocess.TimeoutExpired:
                    duration = round(time.perf_counter() - start_t, 3)
                    code = 124
                    out = ""
                    err = f"TIMEOUT EXPIRED: Test suite {idx} exceeded the 120-second limit."
                except Exception as e:
                    duration = round(time.perf_counter() - start_t, 3)
                    code = 1
                    out = ""
                    err = f"EXECUTION ERROR in suite {idx}: {str(e)}"

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
                solution_size_bytes=solution_size
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
                system_instructions="You are the Lead Systems Architect. Review the execution logs of competing implementations. Discard any branch with a non-zero exit code or memory crash. Write a Ruthless Synthesis explaining exactly why the winner survived and the others failed, citing specific metrics from the terminal logs.",
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
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    workspace_path = Path.cwd() / ".crucible_workspace"
    mode_label = "MOCK MODE" if args.mock else "LIVE MODE"
    print(f"Initializing Crucible [{mode_label}] in: {workspace_path}")

    effective_max_iterations = args.max_iterations
    if args.force_iterations > args.max_iterations:
        print(
            f"WARNING: --force-iterations ({args.force_iterations}) exceeds --max-iterations ({args.max_iterations}). "
            f"Automatically elevating max_iterations to {args.force_iterations} so survivors can be declared."
        )
        effective_max_iterations = args.force_iterations

    orchestrator = CrucibleOrchestrator(
        problem_statement=args.problem,
        paradigms=args.paradigms,
        workspace_dir=str(workspace_path),
        mock_mode=args.mock,
        entrypoint=args.entrypoint,
        output_dir=args.output_dir,
        force_iterations=args.force_iterations,
    )
    asyncio.run(orchestrator.run(max_iterations=effective_max_iterations))
