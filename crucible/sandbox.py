"""
Crucible Sandbox & Deterministic Execution Environment.

Provides isolated subprocess execution and agent lockdown:
  1. DETERMINISTIC EXECUTION: Injects sitecustomize.py to seed random.seed(0)
     and forces PYTHONHASHSEED=0.
  2. PROCESS WATCHDOG: Enforces hard timeouts (default 120s) with exit code 124.
  3. AGENT LOCKDOWN: Disables tools, enforces policy.deny_all(), and isolates workspaces.
  4. PATH SANITIZATION: Sanitizes host-specific absolute paths into relative POSIX paths.
"""
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

try:
    from google.antigravity import LocalAgentConfig
    from google.antigravity.hooks import policy
    HAS_POLICY = True
except ImportError:
    LocalAgentConfig = None
    policy = None
    HAS_POLICY = False


_SEED_DIR = Path(tempfile.gettempdir()) / "crucible_deterministic_env"
_SITECUSTOMIZE = "import random\nrandom.seed(0)\n"


def deterministic_env() -> dict:
    """Environment for verdict-bearing child processes: seeded hashing and a seeded `random` module."""
    _SEED_DIR.mkdir(parents=True, exist_ok=True)
    seed_file = _SEED_DIR / "sitecustomize.py"
    if not seed_file.exists() or seed_file.read_text(encoding="utf-8") != _SITECUSTOMIZE:
        seed_file.write_text(_SITECUSTOMIZE, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(_SEED_DIR), env.get("PYTHONPATH", "")) if p)
    return env


def run_python(
    script: str,
    cwd: Path,
    timeout: int = 120,
    deterministic: bool = True,
    args: Optional[list] = None
) -> tuple[int, str, str, float]:
    """
    Runs `python <script> [*args]` in cwd.
    Returns (exit code, stdout, stderr, seconds); exit code 124 means timeout.
    """
    start = time.perf_counter()
    cmd = [sys.executable, script] + (args or [])
    env = deterministic_env() if deterministic else None
    try:
        p = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env
        )
        return p.returncode, p.stdout, p.stderr, round(time.perf_counter() - start, 3)
    except subprocess.TimeoutExpired:
        return 124, "", f"TIMEOUT EXPIRED: {script} exceeded the {timeout}-second limit.", round(time.perf_counter() - start, 3)
    except Exception as e:
        return 1, "", f"EXECUTION ERROR in {script}: {e}", round(time.perf_counter() - start, 3)


def sanitize_paths(text: str, project_root: Optional[Path] = None) -> str:
    """Sanitizes host-specific absolute paths into relative POSIX paths."""
    if not text:
        return ""
    if project_root:
        root_str = str(project_root.resolve())
        text = text.replace(root_str, ".")
        text = text.replace(root_str.replace("\\", "/"), ".")
    text = text.replace(".\\.crucible_workspace", "./.crucible_workspace")
    text = text.replace(".\\deployments", "./deployments")
    # Sanitize file:/// URL paths
    text = re.sub(r'file:///[A-Za-z]:/[^"\'<>\s)]*?(?:\.crucible_workspace)', r'./.crucible_workspace', text)
    text = re.sub(r'file:///[A-Za-z]:/[^"\'<>\s)]*?Project%20Crucible/?', r'', text)
    text = re.sub(r'file:///[A-Za-z]:/[^"\'<>\s)]*?Project Crucible/?', r'', text)
    # Sanitize Windows drive-letter paths
    text = re.sub(r'[A-Za-z]:(?:\\\\|\\|/)[^"\'\n\r]*?\.crucible_workspace', r'./.crucible_workspace', text)
    text = re.sub(r'[A-Za-z]:(?:\\\\|\\|/)[^"\'\n\r]*?Project Crucible', r'.', text)
    return text


def create_locked_down_agent_config(system_instructions: str, temp_dir: str):
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
