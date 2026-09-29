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
)


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
        Verify mock mode executes the tournament and produces exact branch outcomes:
        Branch 1 fails (algorithmic edge case).
        Branch 2 and 3 pass.
        Winners are promoted to deployments directory.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            workspace = tmp_path / ".crucible_workspace"
            out_dir = tmp_path / "mock_output"
            orchestrator = CrucibleOrchestrator(
                problem_statement="Test thermal throttling cascade detection",
                paradigms=[
                    "Micro-batching with dictionary state aggregation",
                    "Zero-copy memory-mapped file processing",
                    "Streaming Finite-State Machine with a bounded ring buffer",
                ],
                workspace_dir=str(workspace),
                mock_mode=True,
                output_dir=str(out_dir),
            )

            asyncio.run(orchestrator.run(max_iterations=1))

            assert orchestrator.results_path.exists(), "results.json not created in output dir"
            data = json.loads(orchestrator.results_path.read_text(encoding="utf-8"))

            # 1. Telemetry metadata
            assert data["schema_version"] == "1.1.0"
            assert data["configuration"]["mode"] == "mock"
            assert data["configuration"]["entrypoint"] == "process_telemetry"
            assert "cumulative_regression_gate" in data["configuration"]["verifiers"]

            # 2. Summary counts: 3 evaluations, 2 pass, 1 fail
            s = data["summary"]
            assert s["status"] == "PASSED"
            assert s["survived"] is True
            assert s["total_evaluations"] == 3
            assert s["passed_evaluations"] == 2
            assert s["failed_evaluations"] == 1
            assert s["timeout_evaluations"] == 0
            assert s["winning_branches"] == ["branch_2", "branch_3"]

            # 3. Deployed artifacts verification
            deployed = s["deployed_artifacts"]
            assert len(deployed) == 2
            for rel_str in deployed:
                full_path = orchestrator.project_root / rel_str
                assert full_path.exists(), f"Deployed artifact does not exist: {full_path}"
                content = full_path.read_text(encoding="utf-8")
                assert "def process_telemetry(stream):" in content
                # Ensure no absolute paths leaked into deployed_artifacts
                assert not rel_str.startswith("C:") and not rel_str.startswith("/"), \
                    f"Deployed artifact path is not relative: {rel_str}"

    def test_mock_pipeline_with_custom_entrypoint(self):
        """
        Verify mock mode adapts mock solutions and harness to a custom entrypoint.
        Executing with --entrypoint analyze_data must succeed with 2 winners.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            workspace = tmp_path / ".crucible_workspace"
            out_dir = tmp_path / "mock_output"
            orchestrator = CrucibleOrchestrator(
                problem_statement="Test custom contract",
                paradigms=[
                    "Micro-batching with dictionary state aggregation",
                    "Zero-copy memory-mapped file processing",
                    "Streaming Finite-State Machine with a bounded ring buffer",
                ],
                workspace_dir=str(workspace),
                mock_mode=True,
                entrypoint="analyze_data",
                output_dir=str(out_dir),
            )

            asyncio.run(orchestrator.run(max_iterations=1))

            data = json.loads(orchestrator.results_path.read_text(encoding="utf-8"))
            assert data["configuration"]["entrypoint"] == "analyze_data"
            assert data["summary"]["survived"] is True
            assert data["summary"]["winning_branches"] == ["branch_2", "branch_3"]

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
            )

            asyncio.run(orchestrator.run(max_iterations=2))

            data = json.loads(orchestrator.results_path.read_text(encoding="utf-8"))
            assert len(data["iterations"]) == 2
            assert data["summary"]["total_iterations_run"] == 2
            assert len(orchestrator.test_suites) == 2
            # Both suites were generated and preserved
            assert orchestrator.test_suites[0].name == "arena_test_iter_1.py"
            assert orchestrator.test_suites[1].name == "arena_test_iter_2.py"

    def test_force_iterations_overrides_early_exit(self):
        """Verify that --force-iterations forces subsequent iterations even when survivors exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            workspace = tmp_path / ".crucible_workspace"
            out_dir = tmp_path / "mock_output"
            # In mock mode, branch_2 and branch_3 survive iteration 1
            orchestrator = CrucibleOrchestrator(
                problem_statement="Force iterations test",
                paradigms=["Zero-copy memory-mapped file processing"],
                workspace_dir=str(workspace),
                mock_mode=True,
                output_dir=str(out_dir),
                force_iterations=2,
            )

            asyncio.run(orchestrator.run(max_iterations=2))

            data = json.loads(orchestrator.results_path.read_text(encoding="utf-8"))
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
            "--max-iterations", "4"
        ])
        assert args.problem == "Custom Problem"
        assert args.mock is True
        assert args.entrypoint == "run_pipeline"
        assert args.output_dir == "custom_out"
        assert args.paradigms == ["P1", "P2"]
        assert args.force_iterations == 2
        assert args.max_iterations == 4


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
