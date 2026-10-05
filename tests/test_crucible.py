"""
Crucible Protocol Comprehensive Test Suite
Tests the orchestrator's deterministic components:
  - AST contract enforcement gate and import guard
  - Code extraction and data structures
  - Mock mode pipeline execution and outcomes
  - Configurable entrypoint in mock mode
  - Telemetry schema, isolation, and relative paths
  - Multi-iteration retry loop and cumulative regression gate
  - Path sanitization
  - Agent lockdown configuration
  - Real CLI argument parser
"""
import sys
import os
import json
import asyncio
import tempfile
import types
from pathlib import Path

# Safe mocking of google.antigravity if not already present
if "google.antigravity" not in sys.modules:
    try:
        import google.antigravity
    except ImportError:
        mock_google = sys.modules.get("google", types.ModuleType("google"))
        mock_antigravity = types.ModuleType("google.antigravity")

        class _MockResponse:
            def __init__(self, text):
                self._text = text

            async def text(self):
                return self._text

        class _MockAgent:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def chat(self, message):
                return _MockResponse("")

        class _MockConfig:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        mock_policy = types.ModuleType("google.antigravity.hooks.policy")
        mock_policy.deny_all = lambda: "deny_all_policy"
        mock_hooks = types.ModuleType("google.antigravity.hooks")
        mock_hooks.policy = mock_policy

        mock_antigravity.Agent = _MockAgent
        mock_antigravity.LocalAgentConfig = _MockConfig
        mock_antigravity.hooks = mock_hooks
        mock_google.antigravity = mock_antigravity
        sys.modules["google"] = mock_google
        sys.modules["google.antigravity"] = mock_antigravity
        sys.modules["google.antigravity.hooks"] = mock_hooks
        sys.modules["google.antigravity.hooks.policy"] = mock_policy

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from run_crucible import (
    CrucibleOrchestrator,
    BranchResult,
    extract_code,
    build_parser,
    _create_locked_down_agent_config,
    run_python,
    MOCK_SOLUTIONS,
)
from crucible.sandbox import Sandbox, docker_available

import pytest

# Pipeline mechanics run on the subprocess backend for speed (mock solutions and suites are our own fixtures).
# TestDockerEndToEnd runs the full pipeline inside the Docker sandbox.
FAST = Sandbox("subprocess-unsafe")
MOCK_PARADIGMS = [
    "Micro-batching with dictionary state aggregation",
    "Zero-copy memory-mapped file processing",
    "Streaming Finite-State Machine with a bounded ring buffer",
]


# ============================================================
# AST Contract Enforcement & Import Guard Tests
# ============================================================

class TestASTGate:
    """Tests for the deterministic AST contract enforcement gate."""

    def _write_temp(self, code: str) -> Path:
        tmp = Path(tempfile.mktemp(suffix=".py"))
        tmp.write_text(code, encoding="utf-8")
        return tmp

    def test_valid_entrypoint_passes(self):
        f = self._write_temp("def process_telemetry(stream):\n    return list(stream)\n")
        passed, reason = CrucibleOrchestrator._audit_contract(f)
        f.unlink()
        assert passed is True, f"Expected pass, got: {reason}"

    def test_missing_entrypoint_rejected(self):
        f = self._write_temp("def detect_cascades(stream):\n    return []\n")
        passed, reason = CrucibleOrchestrator._audit_contract(f)
        f.unlink()
        assert passed is False
        assert "AST CONTRACT VIOLATION" in reason

    def test_syntax_error_rejected(self):
        f = self._write_temp("def process_telemetry(stream)\n    return []\n")
        passed, reason = CrucibleOrchestrator._audit_contract(f)
        f.unlink()
        assert passed is False
        assert "SYNTAX ERROR" in reason

    def test_class_wrapper_rejected(self):
        f = self._write_temp(
            "class Processor:\n"
            "    def process_telemetry(self, stream):\n"
            "        pass\n"
        )
        passed, reason = CrucibleOrchestrator._audit_contract(f)
        f.unlink()
        assert passed is False
        assert "AST CONTRACT VIOLATION" in reason

    def test_blocked_import_subprocess(self):
        f = self._write_temp("import subprocess\ndef process_telemetry(stream):\n    pass\n")
        passed, reason = CrucibleOrchestrator._audit_contract(f)
        f.unlink()
        assert passed is False
        assert "AST IMPORT VIOLATION" in reason

    def test_blocked_import_from_socket(self):
        f = self._write_temp("from socket import create_connection\ndef process_telemetry(stream):\n    pass\n")
        passed, reason = CrucibleOrchestrator._audit_contract(f)
        f.unlink()
        assert passed is False
        assert "AST IMPORT VIOLATION" in reason

    def test_blocked_import_http_client(self):
        f = self._write_temp("import http.client\ndef process_telemetry(stream):\n    pass\n")
        passed, reason = CrucibleOrchestrator._audit_contract(f)
        f.unlink()
        assert passed is False
        assert "AST IMPORT VIOLATION" in reason

    def test_all_nine_blocked_module_families(self):
        """Verify each of the 9 blocked module families is intercepted."""
        assert len(CrucibleOrchestrator.BLOCKED_MODULES) == 9
        for mod in CrucibleOrchestrator.BLOCKED_MODULES:
            f = self._write_temp(f"import {mod}\ndef process_telemetry(stream):\n    pass\n")
            passed, reason = CrucibleOrchestrator._audit_contract(f)
            f.unlink()
            assert passed is False, f"Expected {mod} to be blocked"
            assert "AST IMPORT VIOLATION" in reason

    def test_safe_stdlib_imports_pass(self):
        f = self._write_temp(
            "import collections\nimport time\nimport struct\n"
            "def process_telemetry(stream):\n    return []\n"
        )
        passed, reason = CrucibleOrchestrator._audit_contract(f)
        f.unlink()
        assert passed is True, f"Expected pass, got: {reason}"

    def test_configurable_entrypoint(self):
        """Verify the AST gate respects a custom entrypoint passed as argument."""
        f = self._write_temp("def analyze_data(stream):\n    return []\n")
        passed, reason = CrucibleOrchestrator._audit_contract(f, entrypoint="analyze_data")
        f.unlink()
        assert passed is True, f"Expected pass with custom entrypoint, got: {reason}"

        f2 = self._write_temp("def process_telemetry(stream):\n    return []\n")
        passed2, reason2 = CrucibleOrchestrator._audit_contract(f2, entrypoint="analyze_data")
        f2.unlink()
        assert passed2 is False, "Expected rejection: wrong entrypoint for custom contract"
        assert "def analyze_data(stream):" in reason2


# ============================================================
# Agent Lockdown & Path Sanitization Tests
# ============================================================

class TestAgentLockdownAndSanitization:
    """Tests for agent security policies and path sanitization."""

    def test_agent_config_is_strictly_locked_down(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _create_locked_down_agent_config("Instructions", tmp_dir)
            assert config.workspaces == [tmp_dir]
            assert config.tools == []
            assert hasattr(config, "policies") and len(config.policies) > 0

    def test_lockdown_fails_closed_when_policy_unavailable(self, monkeypatch):
        import run_crucible
        import pytest
        monkeypatch.setattr(run_crucible, "HAS_POLICY", False)
        with tempfile.TemporaryDirectory() as tmp_dir:
            with pytest.raises(RuntimeError, match="Security lockdown failure"):
                run_crucible._create_locked_down_agent_config("Instructions", tmp_dir)

    def test_path_sanitization_removes_absolute_paths(self):
        orchestrator = CrucibleOrchestrator("Test", ["P1"], mock_mode=True)
        raw_stderr = (
            'Traceback (most recent call last):\n'
            f'  File "{orchestrator.project_root}\\.crucible_workspace\\branch_1\\arena_test.py", line 10\n'
            'AssertionError: Expected cascade\n'
        )
        sanitized = orchestrator._sanitize_paths(raw_stderr)
        assert str(orchestrator.project_root) not in sanitized
        assert "C:" not in sanitized
        assert "./.crucible_workspace" in sanitized

    def test_path_sanitization_removes_file_urls_and_json_escaped_paths(self):
        orchestrator = CrucibleOrchestrator("Test", ["P1"], mock_mode=True)
        sample = (
            'Engine: file:///C:/Example%20Dir/Project%20Crucible/run_crucible.py#L179\n'
            'Workspace: file:///C:/Example%20Dir/Project%20Crucible/.crucible_workspace/branch_2/arena_test.py\n'
            'Traceback: File "C:\\\\Example Dir\\\\Project Crucible\\\\.crucible_workspace\\\\branch_2\\\\solution.py"\n'
        )
        sanitized = orchestrator._sanitize_paths(sample)
        assert "C:" not in sanitized
        assert "file:///C:" not in sanitized
        assert "./.crucible_workspace" in sanitized


# ============================================================
# Code Extraction Tests
# ============================================================

class TestExtractCode:
    """Tests for the extract_code utility."""

    def test_extracts_from_python_block(self):
        text = "Here is the code:\n```python\ndef foo():\n    pass\n```\nDone."
        assert extract_code(text) == "def foo():\n    pass"

    def test_extracts_from_bare_block(self):
        text = "```\ndef bar():\n    return 1\n```"
        assert extract_code(text) == "def bar():\n    return 1"

    def test_returns_raw_text_without_fences(self):
        text = "def baz():\n    return 42"
        assert extract_code(text) == text.strip()


# ============================================================
# BranchResult Tests
# ============================================================

class TestBranchResult:
    """Tests for the BranchResult dataclass."""

    def test_default_solution_size(self):
        r = BranchResult(name="b1", paradigm="p1", exit_code=0, status="PASS",
                         duration_seconds=1.0, stdout="", stderr="")
        assert r.solution_size_bytes == 0

    def test_custom_solution_size(self):
        r = BranchResult(name="b1", paradigm="p1", exit_code=1, status="FAIL",
                         duration_seconds=0.5, stdout="out", stderr="err",
                         solution_size_bytes=1234)
        assert r.solution_size_bytes == 1234


# ============================================================
# Mock Mode Pipeline Tests (Real Outcomes & Verifications)
# ============================================================

class TestMockPipeline:
    """End-to-end tests for mock mode execution verifying real outcomes."""

    def test_mock_pipeline_branch_outcomes_and_deployments(self):
        """
        Both gate paths, end to end:
          Round 1: the count-only suite passes the reference and kills most code mutants, but almost no output
                   probes, so it is QUARANTINED. Nothing decisive exists, so all branches are UNVERIFIED and
                   nothing is promoted.
          Round 2: the exact-output suite is ADMITTED on both axes. Branch 1 (algorithm bug) and branch 2 (wrong
                   output schema) fail; only branch 3 is promoted.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            orchestrator = CrucibleOrchestrator(
                problem_statement="Test thermal throttling cascade detection",
                paradigms=MOCK_PARADIGMS,
                workspace_dir=str(tmp_path / ".crucible_workspace"),
                mock_mode=True,
                output_dir=str(tmp_path / "mock_output"),
                sandbox=FAST,
            )

            asyncio.run(orchestrator.run(max_iterations=2))

            assert orchestrator.results_path.exists(), "results.json not created in output dir"
            data = json.loads(orchestrator.results_path.read_text(encoding="utf-8"))

            # 1. Telemetry metadata
            assert data["schema_version"] == "1.3.0"
            assert data["configuration"]["mode"] == "mock"
            assert data["configuration"]["entrypoint"] == "process_telemetry"
            assert "cumulative_regression_gate" in data["configuration"]["verifiers"]
            assert "suite_admission_vs_reference" in data["configuration"]["verifiers"]
            assert data["configuration"]["verdict_policy"]["name"] == "deterministic"

            # 2. Round 1: quarantined by the output-contract axis, nothing verified
            r1 = data["iterations"][0]
            adm1 = r1["test_harness"]["admission"]
            assert adm1["decision"] == "quarantined"
            assert adm1["reference_exit_codes"] == [0, 0, 0]
            ms1 = adm1["mutation_slaughter"]
            assert ms1["code_axis_passed"] is True and ms1["output_axis_passed"] is False
            assert {b["status"] for b in r1["branches"]} == {"UNVERIFIED"}

            # 3. Round 2: admitted on both axes, only the correct branch passes
            r2 = data["iterations"][1]
            adm2 = r2["test_harness"]["admission"]
            assert adm2["decision"] == "admitted", adm2["reason"]
            assert adm2["mutation_slaughter"]["slaughter_rate"] >= 0.60
            assert adm2["mutation_slaughter"]["output_rate"] >= 0.60
            assert {b["name"]: b["exit_code"] == 0 for b in r2["branches"]} == \
                {"branch_1": False, "branch_2": False, "branch_3": True}

            # 4. Summary
            s = data["summary"]
            assert s["status"] == "PASSED"
            assert s["survived"] is True
            assert s["total_evaluations"] == 6
            assert s["passed_evaluations"] == 1
            assert s["unverified_evaluations"] == 3
            assert s["timeout_evaluations"] == 0
            assert s["winning_branches"] == ["branch_3"]

            # 5. Deployed artifacts verification
            deployed = s["deployed_artifacts"]
            assert len(deployed) == 1
            for rel_str in deployed:
                full_path = orchestrator.project_root / rel_str
                assert full_path.exists(), f"Deployed artifact does not exist: {full_path}"
                content = full_path.read_text(encoding="utf-8")
                assert "def process_telemetry(stream):" in content
                assert "latency_ms" in content  # the correct (FSM) schema, not branch_2's
                # Ensure no absolute paths leaked into deployed_artifacts
                assert not rel_str.startswith("C:") and not rel_str.startswith("/"), \
                    f"Deployed artifact path is not relative: {rel_str}"

    def test_without_the_mutation_gate_the_weak_suite_promotes_wrong_code(self):
        """
        The hazard the gate exists for, demonstrated: with the gate off, the count-only suite is admitted because
        the reference passes it, and branch_2 (wrong output schema: trigger_ts / cascade_ts, no latency) is
        promoted to production alongside the correct branch.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            orch = CrucibleOrchestrator(problem_statement="gate off", paradigms=MOCK_PARADIGMS,
                                        workspace_dir=str(tmp_path / ".crucible_workspace"), mock_mode=True,
                                        output_dir=str(tmp_path / "mock_output"), mutation_gate=False, sandbox=FAST)
            asyncio.run(orch.run(max_iterations=1))
            data = json.loads(orch.results_path.read_text(encoding="utf-8"))
            assert data["iterations"][0]["test_harness"]["admission"]["decision"] == "admitted"
            assert data["summary"]["winning_branches"] == ["branch_2", "branch_3"]
            promoted = [(orch.project_root / p).read_text(encoding="utf-8") for p in data["summary"]["deployed_artifacts"]]
            assert any('"trigger_ts"' in c and "latency_ms" not in c for c in promoted)

    def test_mock_pipeline_with_custom_entrypoint(self):
        """
        Verify mock mode adapts mock solutions, harnesses, reference and probes to a custom entrypoint.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            orchestrator = CrucibleOrchestrator(
                problem_statement="Test custom contract",
                paradigms=MOCK_PARADIGMS,
                workspace_dir=str(tmp_path / ".crucible_workspace"),
                mock_mode=True,
                entrypoint="analyze_data",
                output_dir=str(tmp_path / "mock_output"),
                sandbox=FAST,
            )

            asyncio.run(orchestrator.run(max_iterations=2))

            data = json.loads(orchestrator.results_path.read_text(encoding="utf-8"))
            assert data["configuration"]["entrypoint"] == "analyze_data"
            assert [i["test_harness"]["admission"]["decision"] for i in data["iterations"]] == \
                ["quarantined", "admitted"]
            assert data["summary"]["survived"] is True
            assert data["summary"]["winning_branches"] == ["branch_3"]

            # Verify deployed solutions declare def analyze_data
            for rel_str in data["summary"]["deployed_artifacts"]:
                full_path = orchestrator.project_root / rel_str
                content = full_path.read_text(encoding="utf-8")
                assert "def analyze_data(stream):" in content

    def test_mock_output_isolation(self):
        """Verify mock mode defaults to .crucible_mock to protect root audit trail."""
        orchestrator = CrucibleOrchestrator(
            problem_statement="Test isolation",
            paradigms=["Streaming Finite-State Machine with a bounded ring buffer"],
            mock_mode=True,
            sandbox=FAST,
        )
        assert orchestrator.output_dir.name == ".crucible_mock"
        assert orchestrator.results_path.parent.name == ".crucible_mock"
        assert orchestrator.artifacts_dir.parent.name == ".crucible_mock"
        assert orchestrator.deployments_dir.parent.name == ".crucible_mock"

    def test_multi_iteration_retry_loop_and_cumulative_suites(self):
        """Verify the multi-iteration loop accumulates test suites across iterations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            workspace = tmp_path / ".crucible_workspace"
            out_dir = tmp_path / "mock_output"
            # Micro-batching branch fails mock tests
            orchestrator = CrucibleOrchestrator(
                problem_statement="Cumulative test suite test",
                paradigms=["Micro-batching with dictionary state aggregation"],
                workspace_dir=str(workspace),
                mock_mode=True,
                output_dir=str(out_dir),
                sandbox=FAST,
            )

            asyncio.run(orchestrator.run(max_iterations=2))

            data = json.loads(orchestrator.results_path.read_text(encoding="utf-8"))
            assert len(data["iterations"]) == 2
            assert data["summary"]["total_iterations_run"] == 2
            assert len(orchestrator.test_suites) == 2
            # Both suites were generated and preserved
            assert orchestrator.test_suites[0].name == "arena_test_iter_1.py"
            assert orchestrator.test_suites[1].name == "arena_test_iter_2.py"
            assert data["summary"]["survived"] is False

    def test_force_iterations_overrides_early_exit(self):
        """Verify that --force-iterations forces subsequent iterations even when survivors exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            workspace = tmp_path / ".crucible_workspace"
            out_dir = tmp_path / "mock_output"
            # Gate off so round 1's suite is admitted and the FSM branch survives it; force=2 must still run round 2.
            orchestrator = CrucibleOrchestrator(
                problem_statement="Force iterations test",
                paradigms=["Streaming Finite-State Machine with a bounded ring buffer"],
                workspace_dir=str(workspace),
                mock_mode=True,
                output_dir=str(out_dir),
                force_iterations=2,
                mutation_gate=False,
                sandbox=FAST,
            )

            asyncio.run(orchestrator.run(max_iterations=2))

            data = json.loads(orchestrator.results_path.read_text(encoding="utf-8"))
            assert data["iterations"][0]["branches"][0]["exit_code"] == 0  # a survivor existed in round 1
            # Should have executed 2 iterations despite surviving round 1
            assert len(data["iterations"]) == 2
            assert data["summary"]["total_iterations_run"] == 2
            assert len(orchestrator.test_suites) == 2
            assert data["summary"]["survived"] is True

    def test_timeout_telemetry_accounting(self):
        """Verify exit code 124 correctly increments timeout_evaluations in telemetry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            workspace = tmp_path / ".crucible_workspace"
            out_dir = tmp_path / "mock_output"
            orchestrator = CrucibleOrchestrator(
                problem_statement="Timeout test",
                paradigms=["Zero-copy memory-mapped file processing"],
                workspace_dir=str(workspace),
                mock_mode=True,
                output_dir=str(out_dir),
                sandbox=FAST,
            )

            # Manually inject iteration with a simulated timeout (exit code 124)
            orchestrator.telemetry["iterations"].append({
                "iteration": 1,
                "timestamp": "2026-09-29T00:00:00Z",
                "test_harness": {"path": "arena_test_iter_1.py", "size_bytes": 100},
                "branches": [
                    {
                        "name": "branch_1",
                        "paradigm": "Zero-copy memory-mapped file processing",
                        "exit_code": 124,
                        "status": "TIMEOUT",
                        "duration_seconds": 120.0,
                        "solution_size_bytes": 1000,
                        "stdout": "",
                        "stderr": "TIMEOUT EXPIRED: Process exceeded the 120-second limit."
                    }
                ],
                "synthesis_report": "Watchdog timeout"
            })

            orchestrator._persist_telemetry(
                status="FAILED",
                survived=False,
                winners=[],
                deployed_artifacts=[],
                total_duration=120.0
            )

            data = json.loads(orchestrator.results_path.read_text(encoding="utf-8"))
            s = data["summary"]
            assert s["timeout_evaluations"] == 1
            assert s["total_evaluations"] == 1
            assert s["failed_evaluations"] == 1
            assert s["passed_evaluations"] == 0


# ============================================================
# CLI Argument Parsing Tests (Testing REAL build_parser)
# ============================================================

class TestCLIArguments:
    """Tests for the actual command-line interface argument parser from run_crucible."""

    def test_default_arguments(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert "thermal throttling cascades" in args.problem
        assert len(args.paradigms) == 3
        assert args.mock is False
        assert args.entrypoint == "process_telemetry"
        assert args.output_dir is None
        assert args.force_iterations == 1
        assert args.max_iterations == 3
        assert args.mutation_gate is None  # None = automatic: on whenever a reference exists (deterministic policy)
        assert args.mutation_threshold == 0.60

    def test_mutation_gate_arguments(self):
        parser = build_parser()
        args = parser.parse_args(["--mutation-gate", "--mutation-threshold", "0.75"])
        assert args.mutation_gate is True
        assert args.mutation_threshold == 0.75
        assert parser.parse_args(["--no-mutation-gate"]).mutation_gate is False

    def test_force_iterations_argument(self):
        parser = build_parser()
        args = parser.parse_args(["--force-iterations", "3"])
        assert args.force_iterations == 3

    def test_max_iterations_argument(self):
        parser = build_parser()
        args = parser.parse_args(["--max-iterations", "5"])
        assert args.max_iterations == 5

    def test_custom_mock_and_entrypoint_arguments(self):
        parser = build_parser()
        args = parser.parse_args([
            "Custom Problem",
            "--mock",
            "--entrypoint", "run_pipeline",
            "--output-dir", "custom_out",
            "--paradigms", "P1", "P2",
            "--force-iterations", "2",
            "--max-iterations", "4",
            "--mutation-gate",
            "--mutation-threshold", "0.80",
        ])
        assert args.problem == "Custom Problem"
        assert args.mock is True
        assert args.entrypoint == "run_pipeline"
        assert args.output_dir == "custom_out"
        assert args.paradigms == ["P1", "P2"]
        assert args.force_iterations == 2
        assert args.max_iterations == 4
        assert args.mutation_gate is True
        assert args.mutation_threshold == 0.80



# ============================================================
# Deterministic Verdict Tests
# ============================================================

FSM_REFERENCE = MOCK_SOLUTIONS["Streaming Finite-State Machine with a bounded ring buffer"]


def _mock_orchestrator(tmp_path: Path, **kwargs) -> CrucibleOrchestrator:
    params = dict(problem_statement="Deterministic verdict test",
                  paradigms=MOCK_PARADIGMS,
                  workspace_dir=str(tmp_path / ".crucible_workspace"), mock_mode=True,
                  output_dir=str(tmp_path / "mock_output"), sandbox=FAST)
    params.update(kwargs)
    return CrucibleOrchestrator(**params)


class TestDeterministicVerdicts:
    """Verdicts come only from deterministic checks: acceptance cases and reference-validated suites."""

    def test_live_run_without_ground_truth_is_refused(self):
        try:
            CrucibleOrchestrator("p", ["a"], mock_mode=False, sandbox=FAST)
            raise AssertionError("expected ValueError: no acceptance cases or reference")
        except ValueError as e:
            assert "ground truth" in str(e)
        CrucibleOrchestrator("p", ["a"], mock_mode=False, allow_advisory_only=True, sandbox=FAST)  # explicit opt-out
        CrucibleOrchestrator("p", ["a"], mock_mode=False, verdict_policy="legacy", sandbox=FAST)   # legacy needs none

    def test_suite_that_fails_the_reference_is_quarantined(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            ref = tmp / "reference.py"
            ref.write_text(FSM_REFERENCE, encoding="utf-8")
            wrong = tmp / "wrong_suite.py"
            wrong.write_text("import solution, sys\n"
                             "result = solution.process_telemetry([(1000, 'cpu0', 96.0), (1200, 'cpu1', 91.0)])\n"
                             "sys.exit(0 if len(result) == 5 else 1)  # wrong expectation: the true answer is 1\n",
                             encoding="utf-8")
            orch = _mock_orchestrator(tmp, reference_solution=str(ref))
            decision = orch._admit_suite(wrong)
            assert decision["decision"] == "quarantined"
            assert "reference fails it" in decision["reason"]
            assert decision["reference_exit_codes"] == [1, 1, 1]

    def test_no_decisive_check_means_no_promotion(self):
        """Fail closed: when every suite is quarantined and there are no acceptance cases, nothing is promoted."""
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            ref = tmp / "always_empty_reference.py"
            ref.write_text("def process_telemetry(stream):\n    return []\n", encoding="utf-8")  # mock suite rejects it
            orch = _mock_orchestrator(tmp, reference_solution=str(ref))
            asyncio.run(orch.run(max_iterations=1))
            data = json.loads(orch.results_path.read_text(encoding="utf-8"))
            assert data["iterations"][0]["test_harness"]["admission"]["decision"] == "quarantined"
            assert {b["status"] for b in data["iterations"][0]["branches"]} == {"UNVERIFIED"}
            assert data["summary"]["survived"] is False
            assert data["summary"]["unverified_evaluations"] == 3

    def test_suite_without_reference_is_advisory(self):
        with tempfile.TemporaryDirectory() as d:
            suite = Path(d) / "suite.py"
            suite.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
            orch = CrucibleOrchestrator("p", ["a"], mock_mode=False, allow_advisory_only=True,
                                        workspace_dir=str(Path(d) / ".crucible_workspace"),
                                        output_dir=str(Path(d) / "out"), sandbox=FAST)
            assert orch._admit_suite(suite)["decision"] == "advisory"

    def test_acceptance_cases_are_decisive(self):
        """Only the branch whose output matches the human-written case exactly survives."""
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            case = [{"id": "two_sensor_cascade",
                     "input": [[1000, "cpu0", 96.0], [1200, "cpu1", 91.0]],
                     "expected": [{"trigger_timestamp_ms": 1000, "trigger_sensor": "cpu0", "trigger_temp_c": 96.0,
                                   "cascade_timestamp_ms": 1200, "cascade_sensor": "cpu1", "cascade_temp_c": 91.0,
                                   "latency_ms": 200}]}]
            orch = _mock_orchestrator(tmp, acceptance_cases=case)
            asyncio.run(orch.run(max_iterations=1))
            data = json.loads(orch.results_path.read_text(encoding="utf-8"))
            statuses = {b["name"]: b["status"] for b in data["iterations"][0]["branches"]}
            assert statuses == {"branch_1": "ACCEPTANCE_FAIL", "branch_2": "ACCEPTANCE_FAIL", "branch_3": "PASS"}
            assert data["summary"]["winning_branches"] == ["branch_3"]

    def test_verdict_environment_is_seeded(self):
        """Two separate processes see identical string hashes and random numbers."""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "probe.py").write_text("import random, os\nprint(hash('crucible'), random.random(), "
                                              "os.environ.get('PYTHONHASHSEED'))\n", encoding="utf-8")
            first = run_python("probe.py", Path(d))[1]
            second = run_python("probe.py", Path(d))[1]
            assert first == second
            assert first.strip().endswith(" 0")

    def test_rounds_are_saved_for_replay(self):
        with tempfile.TemporaryDirectory() as d:
            orch = _mock_orchestrator(Path(d))
            asyncio.run(orch.run(max_iterations=1))
            round_dir = orch.output_dir / "rounds" / "round1"
            assert sorted(p.name for p in round_dir.glob("branch_*.py")) == ["branch_1.py", "branch_2.py", "branch_3.py"]
            assert (round_dir / "arena_test_iter_1.py").exists()
            saved = json.loads((round_dir / "admission.json").read_text(encoding="utf-8"))
            assert saved["decision"] == "quarantined"
            assert saved["mutation_slaughter"]["output_axis_passed"] is False
            assert (orch.output_dir / "rounds" / "reference_solution.py").exists()

    def test_invariant_gate_rejects_an_impure_candidate(self, monkeypatch):
        """
        --invariants, end to end: a candidate that returns correct output but clears its caller's input list passes
        every admitted test, so without the invariant gate it is promoted. With it, it is rejected (INVARIANT_FAIL).
        """
        import run_crucible
        impure = FSM_REFERENCE.replace("    return cascades", "    if isinstance(stream, list):\n"
                                                              "        stream.clear()\n"
                                                              "    return cascades")
        assert impure != FSM_REFERENCE
        monkeypatch.setitem(run_crucible.MOCK_SOLUTIONS, "Impure FSM", impure)
        outcomes = {}
        for invariants in (False, True):
            with tempfile.TemporaryDirectory() as d:
                orch = _mock_orchestrator(Path(d), paradigms=["Impure FSM"], invariants=invariants)
                asyncio.run(orch.run(max_iterations=2))
                data = json.loads(orch.results_path.read_text(encoding="utf-8"))
                last = data["iterations"][-1]["branches"][0]
                outcomes[invariants] = (last["status"], data["summary"]["survived"], last["stderr"])
                if invariants:
                    assert "idempotence_invariant" in data["configuration"]["verifiers"]
        assert outcomes[False][:2] == ("PASS", True), outcomes[False]
        assert outcomes[True][:2] == ("INVARIANT_FAIL", False), outcomes[True]
        assert "mutated its input" in outcomes[True][2]


@pytest.mark.skipif(not docker_available()[0], reason="Docker not available")
class TestDockerEndToEnd:
    """The full mock pipeline inside the real Docker sandbox: same verdicts as the fast backend."""

    def test_full_pipeline_in_docker_quarantines_then_promotes_only_the_correct_branch(self):
        with tempfile.TemporaryDirectory() as d:
            orch = _mock_orchestrator(Path(d), sandbox=Sandbox("docker"))
            asyncio.run(orch.run(max_iterations=2))
            data = json.loads(orch.results_path.read_text(encoding="utf-8"))
            assert data["configuration"]["sandbox"]["backend"] == "docker"
            assert data["configuration"]["sandbox"]["network"] == "none"
            assert [i["test_harness"]["admission"]["decision"] for i in data["iterations"]] == \
                ["quarantined", "admitted"]
            assert data["summary"]["winning_branches"] == ["branch_3"]


if __name__ == "__main__":
    try:
        import pytest
        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        print("pytest not installed, running tests manually...")
        passed = 0
        failed = 0
        for cls in [TestASTGate, TestAgentLockdownAndSanitization, TestExtractCode, TestBranchResult, TestMockPipeline, TestCLIArguments]:
            instance = cls()
            for method_name in sorted(dir(instance)):
                if method_name.startswith("test_"):
                    try:
                        getattr(instance, method_name)()
                        print(f"  [PASS] {cls.__name__}.{method_name}")
                        passed += 1
                    except Exception as e:
                        print(f"  [FAIL] {cls.__name__}.{method_name}: {e}")
                        failed += 1
        print(f"\n{passed} passed, {failed} failed")
        sys.exit(1 if failed else 0)
