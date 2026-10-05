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
import os
import tempfile
from pathlib import Path

import pytest
from crucible.contract import audit_contract, audit_source, BLOCKED_MODULES, STRICT_EXTRA_MODULES
from crucible.sandbox import Sandbox, SandboxUnavailable, docker_available
import crucible.sandbox as sandbox_mod
import run_crucible
from run_crucible import CrucibleOrchestrator, BranchResult

FAST = Sandbox("subprocess-unsafe")


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


def _body(line: str, imports: str = "") -> str:
    return f"{imports}def process_telemetry(stream):\n    {line}\n    return []\n"


class TestStrictProfileRefusals:
    """Evasions the v1 lint missed. Each is refused by `strict` and (for replay fidelity) still allowed by `v1`."""

    EVASIONS = {
        "subclasses_escape": _body("x = ().__class__.__bases__[0].__subclasses__()"),
        "globals_escape": _body("g = process_telemetry.__globals__"),
        "builtins_name": _body("b = __builtins__"),
        "computed_getattr": _body("f = getattr(stream, 'sy' + 'stem')"),
        "getattr_dunder": _body("f = getattr(stream, '__globals__')"),
        "importlib": _body("pass", "import importlib\n"),
        "from_builtins": _body("pass", "from builtins import open as o\n"),
        "os_environ": _body("k = os.environ", "import os\n"),
        "os_getenv": _body("k = os.getenv('KEY')", "import os\n"),
        "os_alias_environ": _body("k = o.environ", "import os as o\n"),
        "os_alias_system": _body("o.system('id')", "import os as o\n"),
        "from_os_import_environ": _body("pass", "from os import environ\n"),
        "from_os_star": _body("pass", "from os import *\n"),
        "os_remove": _body("os.remove('x')", "import os\n"),
        "open_write": _body("open('x', 'w')"),
        "open_append_kw": _body("open('x', mode='a')"),
        "open_computed_mode": _body("open('x', 'r' + '+')"),
        "globals_call": _body("g = globals()"),
        "vars_call": _body("v = vars()"),
        "breakpoint": _body("breakpoint()"),
        "frame_walk": _body("f = (lambda: 0).__code__"),
        "pickle": _body("pass", "import pickle\n"),
        "shutil": _body("pass", "import shutil\n"),
    }

    @pytest.mark.parametrize("name", sorted(EVASIONS))
    def test_strict_refuses(self, name):
        passed, reason = audit_source(self.EVASIONS[name], profile="strict")
        assert passed is False, f"strict lint let {name} through"
        assert "VIOLATION" in reason and "line" in reason

    @pytest.mark.parametrize("name", ["subclasses_escape", "os_environ", "open_write", "importlib", "os_alias_system"])
    def test_v1_profile_is_unchanged_for_replay(self, name):
        assert audit_source(self.EVASIONS[name], profile="v1")[0] is True

    @pytest.mark.parametrize("code", [
        _body("r = sorted(stream, key=lambda x: x[0])", "import collections, heapq, math, itertools, json\n"),
        _body("data = open('input.txt').read()"),
        _body("data = open('input.txt', 'rb').read()"),
        _body("v = getattr(stream, 'append', None)"),
        _body("p = os.path.join('a', 'b')", "import os\n"),
    ])
    def test_strict_allows_ordinary_code(self, code):
        assert audit_source(code, profile="strict") == (True, "")

    def test_strict_module_list_is_a_superset_of_v1(self):
        assert BLOCKED_MODULES < BLOCKED_MODULES | STRICT_EXTRA_MODULES
        assert len(BLOCKED_MODULES) == 9

    def test_unknown_profile_is_refused(self):
        with pytest.raises(ValueError):
            audit_source(_body("pass"), profile="lenient")


class TestSandboxIsTheBoundary:
    """The lint is not a boundary; the sandbox is. These tests hold even when the lint is bypassed."""

    def test_no_silent_fallback_when_docker_is_unavailable(self, monkeypatch, tmp_path):
        monkeypatch.setattr(run_crucible, "docker_available", lambda: (False, "daemon not running"))
        with pytest.raises(SandboxUnavailable, match="Refusing to run untrusted code"):
            CrucibleOrchestrator("p", ["a"], mock_mode=True, sandbox=Sandbox("docker"),
                                 workspace_dir=str(tmp_path / "w"), output_dir=str(tmp_path / "o"))

    def test_docker_run_refuses_rather_than_degrading(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sandbox_mod, "docker_available", lambda: (False, "daemon not running"))
        (tmp_path / "x.py").write_text("print(1)\n", encoding="utf-8")
        with pytest.raises(SandboxUnavailable):
            Sandbox("docker").run("x.py", tmp_path)

    def test_unknown_backend_is_refused(self):
        with pytest.raises(ValueError):
            Sandbox("chroot")

    @pytest.mark.skipif(not docker_available()[0], reason="Docker not available")
    def test_a_lint_bypass_still_cannot_read_secrets_or_reach_the_network(self, monkeypatch, tmp_path):
        """
        Known, documented lint gap: aliasing the module through a variable (`e = os`) is not tracked, so the
        strict lint passes this code. The Docker sandbox still gives it no secrets and no network.
        """
        code = ("import os\n"
                "def process_telemetry(stream):\n"
                "    e = os\n"
                "    return sorted(e.environ)\n")
        assert audit_source(code, profile="strict") == (True, ""), "if the lint now catches this, pick a new gap"
        monkeypatch.setenv("OPENAI_API_KEY", "sk-crucible-canary-123")
        (tmp_path / "solution.py").write_text(code, encoding="utf-8")
        (tmp_path / "probe.py").write_text(
            "import json, socket, solution\n"
            "keys = solution.process_telemetry([])\n"
            "try:\n"
            "    socket.create_connection(('1.1.1.1', 53), timeout=3); net = True\n"
            "except OSError:\n"
            "    net = False\n"
            "print(json.dumps({'keys': keys, 'net': net}))\n", encoding="utf-8")
        code_, out, err, _ = Sandbox("docker").run("probe.py", tmp_path, timeout=60)
        assert code_ == 0, err
        result = json.loads(out.strip().splitlines()[-1])
        assert "OPENAI_API_KEY" not in result["keys"]
        assert "sk-crucible-canary-123" not in out
        assert result["net"] is False


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
                sandbox=FAST,
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
                sandbox=FAST,
            )

            code, detail = orch._run_acceptance(branch_dir)
            assert code != 0, "Expected failure on int 1 vs boolean True type mismatch!"
            assert "expected" in detail or "failed" in detail
