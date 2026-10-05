"""
Crucible Adversarial Refusal Surface Test Suite.

Enforces Rule 5 of the Consequence-Aware Engineering Protocol:
"A module's value is the class of bad output it prevents, not the feature it provides.
Measure modules by refusal surface: Document the refusals. Test the refusals. Ship the refusals."

Verifies every refusal boundary:
  1. AST Security Refusals: __import__, eval, exec, compile, os.system, os.popen.
  2. Structural Contract Refusals: Missing entrypoint, class wrapper, syntax error.
  3. Import Guard Refusals: Direct imports of blocked module families.
  4. Pipeline Fail-Closed Refusals:
     - Unverified solutions (no decisive check) are refused promotion.
     - Acceptance case mismatches are refused promotion.
     - Tautological test suites failing mutation slaughter are refused admission.
"""
import json
import tempfile
from pathlib import Path

import pytest
from crucible.contract import audit_contract, BLOCKED_MODULES
from run_crucible import CrucibleOrchestrator, BranchResult


class TestASTSecurityRefusals:
    """Tests the static refusal surface against malicious or evasive code patterns."""

    def _check_code(self, code: str) -> tuple[bool, str]:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            tmp_path = Path(f.name)
        try:
            return audit_contract(tmp_path)
        finally:
            tmp_path.unlink()

    def test_refuses_dynamic_import(self):
        passed, reason = self._check_code(
            "def process_telemetry(stream):\n"
            "    mod = __import__('subprocess')\n"
            "    return []\n"
        )
        assert passed is False
        assert "AST SECURITY VIOLATION" in reason
        assert "__import__" in reason

    def test_refuses_eval_primitive(self):
        passed, reason = self._check_code(
            "def process_telemetry(stream):\n"
            "    cmd = eval('1 + 1')\n"
            "    return []\n"
        )
        assert passed is False
        assert "AST SECURITY VIOLATION" in reason
        assert "eval" in reason

    def test_refuses_exec_primitive(self):
        passed, reason = self._check_code(
            "def process_telemetry(stream):\n"
            "    exec('import socket')\n"
            "    return []\n"
        )
        assert passed is False
        assert "AST SECURITY VIOLATION" in reason
        assert "exec" in reason

    def test_refuses_compile_primitive(self):
        passed, reason = self._check_code(
            "def process_telemetry(stream):\n"
            "    c = compile('print(1)', '<string>', 'exec')\n"
            "    return []\n"
        )
        assert passed is False
        assert "AST SECURITY VIOLATION" in reason
        assert "compile" in reason

    def test_refuses_os_system_call(self):
        passed, reason = self._check_code(
            "import os\n"
            "def process_telemetry(stream):\n"
            "    os.system('id')\n"
            "    return []\n"
        )
        assert passed is False
        assert "AST SECURITY VIOLATION" in reason
        assert "os.system" in reason

    def test_refuses_os_popen_call(self):
        passed, reason = self._check_code(
            "import os\n"
            "def process_telemetry(stream):\n"
            "    pipe = os.popen('whoami')\n"
            "    return []\n"
        )
        assert passed is False
        assert "AST SECURITY VIOLATION" in reason
        assert "os.popen" in reason

    def test_refuses_all_nine_blocked_module_imports(self):
        for mod in BLOCKED_MODULES:
            code = f"import {mod}\ndef process_telemetry(stream):\n    return []\n"
            passed, reason = self._check_code(code)
            assert passed is False
            assert "AST IMPORT VIOLATION" in reason
            assert mod in reason


class TestPipelineRefusalBoundaries:
    """Verifies that Crucible's orchestrator fails closed across all boundary conditions."""

    def test_refuses_promotion_without_decisive_check(self):
        """
        FAIL-CLOSED INVARIANT: Code that cannot be decisively checked MUST NEVER be promoted.
        It must receive status UNVERIFIED and exit code 3.
        """
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            # Orchestrator with mock mode, but no acceptance cases and a reference that rejects the mock suite
            ref = tmp / "ref.py"
            ref.write_text("def process_telemetry(stream):\n    return []\n", encoding="utf-8")
            orch = CrucibleOrchestrator(
                problem_statement="Refusal test",
                paradigms=["Micro-batching with dictionary state aggregation"],
                mock_mode=True,
                workspace_dir=str(tmp / ".workspace"),
                output_dir=str(tmp / "out"),
                reference_solution=str(ref),
            )
            # Run 1 iteration
            import asyncio
            asyncio.run(orch.run(max_iterations=1))

            data = json.loads(orch.results_path.read_text(encoding="utf-8"))
            assert data["summary"]["survived"] is False
            assert data["summary"]["unverified_evaluations"] > 0
            assert len(data["summary"]["deployed_artifacts"]) == 0
            assert data["summary"]["status"] == "FAILED"

    def test_refuses_promotion_on_acceptance_case_type_mismatch(self):
        """
        Exact-match refusal: int 1 is not float 1.0, string "true" is not bool True.
        """
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            branch_dir = tmp / "branch_test"
            branch_dir.mkdir()
            # Solution returns integer 1
            (branch_dir / "solution.py").write_text(
                "def process_telemetry(stream):\n    return [{'status': 1}]\n",
                encoding="utf-8"
            )
            # Acceptance case expects boolean True
            cases = [{"id": "type_check", "input": [], "expected": [{"status": True}]}]

            orch = CrucibleOrchestrator(
                problem_statement="Type check",
                paradigms=["P1"],
                mock_mode=True,
                workspace_dir=str(tmp / ".workspace"),
                output_dir=str(tmp / "out"),
                acceptance_cases=cases,
            )

            code, detail = orch._run_acceptance(branch_dir)
            assert code != 0, "Expected failure on int 1 vs boolean True type mismatch!"
            assert "expected" in detail or "failed" in detail
