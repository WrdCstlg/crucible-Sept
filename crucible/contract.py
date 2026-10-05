"""
Crucible AST contract gate: a zero-cost static check run before any untrusted code executes.

What it refuses:
  1. ENTRYPOINT CONTRACT: no top-level `def <entrypoint>(...)` (class wrappers, lambdas and nested defs don't count).
  2. IMPORT GUARD: imports of module families that reach the network, processes, native code or the import system.
  3. EVASION GUARD: dynamic execution (`eval`, `exec`, `compile`, `__import__`), introspection escapes
     (`__subclasses__`, `__globals__`, `__builtins__`, ...), dynamic attribute lookups with computed names,
     process/filesystem-mutation calls on `os`, reading the host environment, and `open()` in a writing mode.

This is a lint, NOT a security boundary. Static analysis of Python can always be evaded by a determined author.
Its job is to reject obvious misuse instantly and cheaply, with a readable reason. Isolation comes from the
sandbox (crucible/sandbox.py: no network, read-only filesystem, no secrets, resource limits), which assumes this
gate has been bypassed.

Profiles:
  strict  (default) all checks above.
  v1      the checks in force when the recorded pilots ran (entrypoint, 9 module families, eval/exec/compile/
          __import__, os.system-style calls). Used only to replay recorded verdicts exactly.
"""
import ast
from pathlib import Path

PROFILES = ("strict", "v1")

BLOCKED_MODULES = frozenset({
    "subprocess", "socket", "http", "urllib", "requests",
    "ctypes", "cffi", "signal", "multiprocessing",
})
STRICT_EXTRA_MODULES = frozenset({
    "importlib", "builtins", "pty", "shutil", "pickle", "marshal", "shelve", "asyncio", "ssl", "ftplib",
    "smtplib", "telnetlib", "xmlrpc", "webbrowser", "code", "codeop", "runpy", "sysconfig", "_thread",
    "posix", "nt", "winreg", "msvcrt", "mmap", "resource", "gc",
})

DANGEROUS_CALLS = frozenset({"__import__", "eval", "exec", "compile"})
STRICT_EXTRA_CALLS = frozenset({"breakpoint", "globals", "vars", "locals"})

DANGEROUS_ATTRS = frozenset({"system", "popen", "execv", "execl", "execve", "spawnl", "spawnv"})
STRICT_EXTRA_OS_ATTRS = frozenset({
    "fork", "forkpty", "kill", "killpg", "remove", "unlink", "rmdir", "removedirs", "rename", "renames",
    "replace", "chmod", "chown", "link", "symlink", "truncate", "putenv", "unsetenv", "environ", "environb",
    "getenv", "execvp", "execvpe", "execle", "execlp", "execlpe", "spawnve", "spawnvp", "spawnvpe", "startfile",
    "posix_spawn", "posix_spawnp", "setuid", "setgid", "chroot", "makedirs", "mkdir", "open", "write",
})
ESCAPE_DUNDERS = frozenset({
    "__subclasses__", "__globals__", "__builtins__", "__code__", "__closure__", "__bases__", "__base__", "__mro__",
    "__import__", "__loader__", "__spec__", "__getattribute__", "__dict__", "__reduce__", "__reduce_ex__",
    "__func__", "__self__", "f_globals", "f_locals", "f_back", "gi_frame", "cr_frame", "tb_frame",
})
DYNAMIC_ATTR_CALLS = frozenset({"getattr", "setattr", "delattr", "hasattr"})
WRITE_MODE_CHARS = set("wax+")


def _violation(node, kind: str, detail: str) -> tuple[bool, str]:
    return False, f"AST {kind} VIOLATION (line {getattr(node, 'lineno', '?')}): {detail}"


def _open_mode(call: ast.Call):
    """The literal mode of an open() call, or None if it is computed (which strict mode also refuses)."""
    mode_node = call.args[1] if len(call.args) > 1 else next((k.value for k in call.keywords if k.arg == "mode"), None)
    if mode_node is None:
        return "r"
    if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
        return mode_node.value
    return None


def audit_source(source_code: str, entrypoint: str = "process_telemetry", profile: str = "strict",
                 filename: str = "<candidate>") -> tuple[bool, str]:
    """Deterministic AST verification of candidate source. Returns (passed, reason); reason is '' on success."""
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {PROFILES}")
    strict = profile == "strict"
    try:
        tree = ast.parse(source_code, filename=filename)
    except SyntaxError as e:
        return False, f"SYNTAX ERROR (line {e.lineno}): {e.msg}"

    if not any(isinstance(n, ast.FunctionDef) and n.name == entrypoint for n in ast.iter_child_nodes(tree)):
        found = [f"{type(n).__name__}('{n.name}')" for n in ast.iter_child_nodes(tree) if hasattr(n, "name")]
        return False, (f"AST CONTRACT VIOLATION: Missing required top-level function 'def {entrypoint}(stream):'. "
                       f"Found top-level definitions: {', '.join(found) if found else 'none'}")

    blocked_modules = BLOCKED_MODULES | (STRICT_EXTRA_MODULES if strict else frozenset())
    blocked_calls = DANGEROUS_CALLS | (STRICT_EXTRA_CALLS if strict else frozenset())
    blocked_os = DANGEROUS_ATTRS | (STRICT_EXTRA_OS_ATTRS if strict else frozenset())
    # Names bound to the os module. v1 only knew the literal name `os`; strict also follows `import os as o`.
    os_names = {"os"}
    if strict:
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                os_names |= {a.asname for a in n.names if a.name == "os" and a.asname}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in blocked_modules:
                    return _violation(node, "IMPORT", f"Import of blocked module '{alias.name}'. "
                                                      f"Blocked module families: {sorted(blocked_modules)}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in blocked_modules:
                return _violation(node, "IMPORT", f"Import from blocked module '{node.module}'. "
                                                  f"Blocked module families: {sorted(blocked_modules)}")
            if strict and node.module == "os" and any(a.name in blocked_os or a.name == "*" for a in node.names):
                return _violation(node, "SECURITY", f"Import of prohibited os primitive(s) "
                                                    f"{[a.name for a in node.names]} from 'os'.")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id in blocked_calls:
                    return _violation(node, "SECURITY", f"Call to prohibited dynamic execution primitive '{func.id}()'.")
                if strict and func.id in DYNAMIC_ATTR_CALLS and len(node.args) >= 2 and not (
                        isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)
                        and node.args[1].value not in ESCAPE_DUNDERS):
                    return _violation(node, "SECURITY", f"'{func.id}()' with a computed or escape-hatch attribute "
                                                        f"name is refused (static analysis cannot vet it).")
                if strict and func.id == "open":
                    mode = _open_mode(node)
                    if mode is None or WRITE_MODE_CHARS & set(mode):
                        return _violation(node, "SECURITY", f"open() in a writing or computed mode ({mode!r}) is "
                                                            f"refused: candidates must not write files.")
            elif isinstance(func, ast.Attribute) and func.attr in blocked_os:
                if isinstance(func.value, ast.Name) and func.value.id in os_names:
                    return _violation(node, "SECURITY", f"Call to prohibited system process primitive 'os.{func.attr}()'.")
        if strict:
            if isinstance(node, ast.Attribute):
                if node.attr in ESCAPE_DUNDERS:
                    return _violation(node, "SECURITY", f"Access to introspection escape hatch '.{node.attr}'.")
                if node.attr in blocked_os and isinstance(node.value, ast.Name) and node.value.id in os_names:
                    return _violation(node, "SECURITY", f"Reference to prohibited 'os.{node.attr}'.")
            elif isinstance(node, ast.Name) and node.id in ("__builtins__", "__loader__", "__spec__"):
                return _violation(node, "SECURITY", f"Reference to '{node.id}'.")
    return True, ""


def audit_contract(source_path: Path, entrypoint: str = "process_telemetry", profile: str = "strict") -> tuple[bool, str]:
    """audit_source() for a file. Returns (passed, reason); reason is '' on success."""
    try:
        source_code = Path(source_path).read_text(encoding="utf-8")
    except Exception as e:
        return False, f"FILE READ ERROR: {e}"
    return audit_source(source_code, entrypoint=entrypoint, profile=profile, filename=str(source_path))
