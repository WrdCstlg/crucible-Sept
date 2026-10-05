"""
Crucible sandbox: where untrusted, AI-written code runs.

What it refuses (each refusal has a test in tests/test_sandbox.py):
  - network access                       (docker: --network none)
  - writes anywhere except a small /tmp  (docker: --read-only rootfs, code mounted read-only)
  - reading host secrets                 (both backends: environment is an allowlist, never os.environ)
  - privilege escalation                 (docker: non-root uid 65534, --cap-drop ALL, no-new-privileges)
  - memory / fork bombs                  (docker: --memory, --memory-swap, --pids-limit)
  - running forever                      (both: hard timeout, container killed, exit code 124)

Backends:
  docker             DEFAULT. Each run is a fresh container from a digest-pinned image.
  subprocess-unsafe  Explicit opt-in only. A host process with a scrubbed environment and a timeout, nothing else:
                     no network, filesystem or memory isolation. For trusted code, CI on hosts without Linux
                     containers, and exact replay of recorded runs (which originally ran this way).

If the docker backend is selected and Docker is unavailable, every run raises SandboxUnavailable. There is no
silent fallback to the weaker backend.

Determinism: verdict-bearing runs get PYTHONHASHSEED=0 and a sitecustomize that seeds `random` with 0.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

try:
    from google.antigravity import LocalAgentConfig
    from google.antigravity.hooks import policy
    HAS_POLICY = True
except ImportError:  # pragma: no cover - depends on the optional SDK
    LocalAgentConfig = None
    policy = None
    HAS_POLICY = False

# Digest-pinned so every run, on every machine, executes in the identical userland.
DEFAULT_IMAGE = "python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d"
BACKENDS = ("docker", "subprocess-unsafe")
ENV_BACKEND = "CRUCIBLE_SANDBOX"
TIMEOUT_EXIT = 124

_SEED_DIR = Path(tempfile.gettempdir()) / "crucible_deterministic_env"
_SITECUSTOMIZE = "import random\nrandom.seed(0)\n"

# The only host variables a subprocess-unsafe child may see. Windows needs SYSTEMROOT to initialise Python.
_HOST_ENV_ALLOWLIST = ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "PATHEXT", "COMSPEC")


class SandboxUnavailable(RuntimeError):
    """The selected backend cannot run. Raised instead of silently degrading isolation."""


def _seed_dir() -> Path:
    _SEED_DIR.mkdir(parents=True, exist_ok=True)
    seed_file = _SEED_DIR / "sitecustomize.py"
    if not seed_file.exists() or seed_file.read_text(encoding="utf-8") != _SITECUSTOMIZE:
        seed_file.write_text(_SITECUSTOMIZE, encoding="utf-8")
    return _SEED_DIR


def scrubbed_env(deterministic: bool = True) -> dict:
    """Environment for a host child process: an allowlist, never a copy of os.environ (which holds API keys)."""
    env = {k: os.environ[k] for k in _HOST_ENV_ALLOWLIST if k in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if deterministic:
        env["PYTHONHASHSEED"] = "0"
        env["PYTHONPATH"] = str(_seed_dir())
    return env


def deterministic_env() -> dict:
    """Backwards-compatible name: the scrubbed, seeded environment for verdict-bearing host processes."""
    return scrubbed_env(deterministic=True)


@lru_cache(maxsize=1)
def docker_available() -> tuple[bool, str]:
    """(available, detail). Cached: probing the daemon costs ~1 s."""
    exe = shutil.which("docker")
    if not exe:
        return False, "docker CLI not found on PATH"
    try:
        p = subprocess.run([exe, "info", "--format", "{{.OSType}}"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"docker daemon not reachable: {e}"
    if p.returncode != 0:
        return False, f"docker daemon not reachable: {(p.stderr or p.stdout).strip()[:200]}"
    if p.stdout.strip() != "linux":
        return False, f"docker is serving {p.stdout.strip()!r} containers; Linux containers are required"
    return True, "ok"


@dataclass(frozen=True)
class Sandbox:
    backend: str = "docker"
    image: str = DEFAULT_IMAGE
    memory_mb: int = 1024
    cpus: float = 1.0
    pids_limit: int = 128
    tmpfs_mb: int = 64
    extra_ro_mounts: tuple = field(default_factory=tuple)

    def __post_init__(self):
        if self.backend not in BACKENDS:
            raise ValueError(f"sandbox backend must be one of {BACKENDS}, got {self.backend!r}")

    @property
    def isolated(self) -> bool:
        return self.backend == "docker"

    def describe(self) -> dict:
        if self.backend == "docker":
            return {"backend": "docker", "image": self.image, "network": "none", "rootfs": "read-only",
                    "code_mount": "read-only", "tmpfs_mb": self.tmpfs_mb, "user": "65534:65534",
                    "capabilities": "all dropped", "no_new_privileges": True, "memory_mb": self.memory_mb,
                    "cpus": self.cpus, "pids_limit": self.pids_limit, "env": "allowlist only"}
        return {"backend": "subprocess-unsafe", "warning": "no network, filesystem or memory isolation",
                "env": "allowlist only"}

    def run(self, script: str, cwd: Path, timeout: int = 120, deterministic: bool = True,
            args: Optional[list] = None) -> tuple[int, str, str, float]:
        """Runs `python <script> [*args]` with `cwd` as the working directory. Returns (exit, stdout, stderr, seconds)."""
        args = [str(a) for a in (args or [])]
        if self.backend == "docker":
            return self._run_docker(script, Path(cwd), timeout, deterministic, args)
        return self._run_subprocess(script, Path(cwd), timeout, deterministic, args)

    # ── backends ────────────────────────────────────────────────────────
    def _run_subprocess(self, script, cwd, timeout, deterministic, args):
        start = time.perf_counter()
        try:
            p = subprocess.run([sys.executable, script, *args], cwd=cwd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout, env=scrubbed_env(deterministic))
            return p.returncode, p.stdout, p.stderr, round(time.perf_counter() - start, 3)
        except subprocess.TimeoutExpired:
            return (TIMEOUT_EXIT, "", f"TIMEOUT EXPIRED: {script} exceeded the {timeout}-second limit.",
                    round(time.perf_counter() - start, 3))
        except Exception as e:
            return 1, "", f"EXECUTION ERROR in {script}: {e}", round(time.perf_counter() - start, 3)

    def docker_command(self, script: str, cwd: Path, deterministic: bool, args: list, name: str) -> list[str]:
        cmd = ["docker", "run", "--rm", "--name", name,
               "--network", "none",
               "--read-only", "--tmpfs", f"/tmp:rw,nosuid,nodev,size={self.tmpfs_mb}m,mode=1777",
               "--memory", f"{self.memory_mb}m", "--memory-swap", f"{self.memory_mb}m",
               "--cpus", str(self.cpus), "--pids-limit", str(self.pids_limit),
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--user", "65534:65534",
               "--env", "HOME=/tmp", "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "PYTHONIOENCODING=utf-8",
               "--mount", f"type=bind,source={cwd.resolve()},target=/work,readonly",
               "--workdir", "/work"]
        if deterministic:
            cmd += ["--env", "PYTHONHASHSEED=0", "--env", "PYTHONPATH=/crucible_seed",
                    "--mount", f"type=bind,source={_seed_dir().resolve()},target=/crucible_seed,readonly"]
        for host, target in self.extra_ro_mounts:
            cmd += ["--mount", f"type=bind,source={Path(host).resolve()},target={target},readonly"]
        return cmd + [self.image, "python", script, *args]

    def _run_docker(self, script, cwd, timeout, deterministic, args):
        ok, detail = docker_available()
        if not ok:
            raise SandboxUnavailable(
                f"Docker sandbox unavailable ({detail}). Refusing to run untrusted code without isolation. "
                f"Start Docker, or opt in explicitly with {ENV_BACKEND}=subprocess-unsafe / --unsafe-subprocess-sandbox.")
        name = f"crucible-{uuid.uuid4().hex[:16]}"
        start = time.perf_counter()
        try:
            p = subprocess.run(self.docker_command(script, cwd, deterministic, args, name), capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=timeout)
            code, out, err = p.returncode, p.stdout, p.stderr
            if code == 137:
                err += "\nSANDBOX: process killed (exit 137): memory limit exceeded or killed by the sandbox."
            elif code == 125:
                err += "\nSANDBOX: docker could not start the container (exit 125)."
            return code, out, err, round(time.perf_counter() - start, 3)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
            return (TIMEOUT_EXIT, "", f"TIMEOUT EXPIRED: {script} exceeded the {timeout}-second limit; container killed.",
                    round(time.perf_counter() - start, 3))


def default_sandbox() -> Sandbox:
    """The sandbox selected by CRUCIBLE_SANDBOX (default: docker)."""
    return Sandbox(backend=os.environ.get(ENV_BACKEND, "docker").strip() or "docker")


def run_python(script: str, cwd: Path, timeout: int = 120, deterministic: bool = True,
               args: Optional[list] = None, sandbox: Optional[Sandbox] = None) -> tuple[int, str, str, float]:
    """Runs `python <script> [*args]` in the given (or default) sandbox. Exit code 124 means timeout."""
    return (sandbox or default_sandbox()).run(script, cwd, timeout=timeout, deterministic=deterministic, args=args)


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
    text = re.sub(r'file:///[A-Za-z]:/[^"\'<>\s)]*?(?:\.crucible_workspace)', r'./.crucible_workspace', text)
    text = re.sub(r'file:///[A-Za-z]:/[^"\'<>\s)]*?Project%20Crucible/?', r'', text)
    text = re.sub(r'file:///[A-Za-z]:/[^"\'<>\s)]*?Project Crucible/?', r'', text)
    text = re.sub(r'[A-Za-z]:(?:\\\\|\\|/)[^"\'\n\r]*?\.crucible_workspace', r'./.crucible_workspace', text)
    text = re.sub(r'[A-Za-z]:(?:\\\\|\\|/)[^"\'\n\r]*?Project Crucible', r'.', text)
    return text


def create_locked_down_agent_config(system_instructions: str, temp_dir: str):
    """
    Agent configuration with no tools, policy.deny_all() and an empty, isolated workspace.
    Fails closed if the SDK security policy module is unavailable.
    """
    if not HAS_POLICY or policy is None or not hasattr(policy, "deny_all"):
        raise RuntimeError(
            "Security lockdown failure: google.antigravity.hooks.policy.deny_all is required "
            "to enforce agent lockdown, but could not be loaded. Refusing to run agent with unverified security posture.")
    return LocalAgentConfig(system_instructions=system_instructions, workspaces=[temp_dir], tools=[],
                            policies=[policy.deny_all()])
