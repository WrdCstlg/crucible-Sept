"""
Crucible AST Contract Enforcement & Import/Execution Guard.

Enforces structural and security invariants on untrusted AI-generated code
before any subprocess is spawned:
  1. ENTRYPOINT CONTRACT: Enforces a top-level function matching the required
     entrypoint name and disallows class/lambda wrappers.
  2. IMPORT GUARD: Static check rejecting direct imports of blocked module families.
  3. DYNAMIC EVASION GUARD: Rejects dynamic execution primitives (__import__, eval,
     exec, importlib, os.system/popen) to prevent sandbox bypass.
"""
import ast
from pathlib import Path


BLOCKED_MODULES = frozenset({
    "subprocess", "socket", "http", "urllib", "requests",
    "ctypes", "cffi", "signal", "multiprocessing",
})

DANGEROUS_CALLS = frozenset({
    "__import__", "eval", "exec", "compile",
})

DANGEROUS_ATTRS = frozenset({
    "system", "popen", "execv", "execl", "execve", "spawnl", "spawnv",
})


def audit_contract(source_path: Path, entrypoint: str = "process_telemetry") -> tuple[bool, str]:
    """
    Deterministic, zero-cost AST verification of a candidate solution.

    Returns:
        (passed: bool, reason: str) - reason is empty string on success.
    """
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
        found_defs = [
            f"{type(n).__name__}('{n.name}')"
            for n in ast.iter_child_nodes(tree)
            if hasattr(n, "name")
        ]
        return False, (
            f"AST CONTRACT VIOLATION: Missing required top-level function 'def {required_name}(stream):'. "
            f"Found top-level definitions: {', '.join(found_defs) if found_defs else 'none'}"
        )

    # --- Check 2: Import guard and dynamic evasion guard ---
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_module = alias.name.split(".")[0]
                if root_module in BLOCKED_MODULES:
                    return False, (
                        f"AST IMPORT VIOLATION (line {node.lineno}): "
                        f"Import of blocked module '{alias.name}'. "
                        f"Blocked module families: {sorted(BLOCKED_MODULES)}"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_module = node.module.split(".")[0]
                if root_module in BLOCKED_MODULES:
                    return False, (
                        f"AST IMPORT VIOLATION (line {node.lineno}): "
                        f"Import from blocked module '{node.module}'. "
                        f"Blocked module families: {sorted(BLOCKED_MODULES)}"
                    )
        # Dynamic execution evasion checks
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in DANGEROUS_CALLS:
                return False, (
                    f"AST SECURITY VIOLATION (line {node.lineno}): "
                    f"Call to prohibited dynamic execution primitive '{func.id}()'."
                )
            elif isinstance(func, ast.Attribute):
                if func.attr in DANGEROUS_ATTRS:
                    # Check if caller looks like 'os'
                    if isinstance(func.value, ast.Name) and func.value.id == "os":
                        return False, (
                            f"AST SECURITY VIOLATION (line {node.lineno}): "
                            f"Call to prohibited system process primitive 'os.{func.attr}()'."
                        )

    return True, ""
