"""
Refusal tests for the sandbox. Each test runs a hostile script and asserts the sandbox refused it.

Docker tests are skipped (not passed) when Linux containers are unavailable; CI runs them on ubuntu-latest.
"""
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from crucible.sandbox import (  # noqa: E402
    DEFAULT_IMAGE, Sandbox, SandboxUnavailable, TIMEOUT_EXIT, default_sandbox, docker_available, scrubbed_env,
)

DOCKER = Sandbox(backend="docker", memory_mb=256, pids_limit=64)
UNSAFE = Sandbox(backend="subprocess-unsafe")
needs_docker = pytest.mark.skipif(not docker_available()[0], reason=f"docker unavailable: {docker_available()[1]}")


def _script(tmp_path: Path, body: str) -> Path:
    (tmp_path / "probe.py").write_text(body, encoding="utf-8")
    return tmp_path


# ── Configuration ────────────────────────────────────────────────────────
class TestConfiguration:
    def test_docker_is_the_default(self, monkeypatch):
        monkeypatch.delenv("CRUCIBLE_SANDBOX", raising=False)
        assert default_sandbox().backend == "docker"

    def test_unknown_backend_rejected(self):
        with pytest.raises(ValueError):
            Sandbox(backend="chroot")

    def test_image_is_digest_pinned(self):
        assert "@sha256:" in DEFAULT_IMAGE

    def test_no_silent_fallback_when_docker_missing(self, monkeypatch, tmp_path):
        import crucible.sandbox as sb
        monkeypatch.setattr(sb, "docker_available", lambda: (False, "simulated outage"))
        with pytest.raises(SandboxUnavailable, match="Refusing to run untrusted code"):
            Sandbox(backend="docker").run("probe.py", _script(tmp_path, "print(1)"))

    def test_docker_command_has_every_restriction(self, tmp_path):
        cmd = DOCKER.docker_command("probe.py", tmp_path, True, [], "crucible-test")
        joined = " ".join(cmd)
        for flag in ("--network none", "--read-only", "--cap-drop ALL", "no-new-privileges", "--user 65534:65534",
                     "--memory 256m", "--memory-swap 256m", "--pids-limit 64", "readonly"):
            assert flag in joined, f"missing {flag!r}"


# ── Secrets: both backends ───────────────────────────────────────────────
class TestSecretsNeverReachUntrustedCode:
    def test_scrubbed_env_drops_api_keys(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "secret-gemini")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-anthropic")
        env = scrubbed_env()
        assert "GEMINI_API_KEY" not in env and "ANTHROPIC_API_KEY" not in env
        assert not any("secret" in v for v in env.values())

    def test_unsafe_backend_child_cannot_read_secret(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CRUCIBLE_TEST_SECRET", "leak-me")
        code, out, err, _ = UNSAFE.run("probe.py", _script(
            tmp_path, "import os; print(os.environ.get('CRUCIBLE_TEST_SECRET'))"))
        assert code == 0, err
        assert out.strip() == "None"

    @needs_docker
    def test_docker_child_cannot_read_secret(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CRUCIBLE_TEST_SECRET", "leak-me")
        code, out, err, _ = DOCKER.run("probe.py", _script(
            tmp_path, "import os; print(os.environ.get('CRUCIBLE_TEST_SECRET'))"))
        assert code == 0, err
        assert out.strip() == "None"

    def test_unsafe_backend_still_enforces_timeout(self, tmp_path):
        code, _, err, _ = UNSAFE.run("probe.py", _script(tmp_path, "while True: pass"), timeout=2)
        assert code == TIMEOUT_EXIT and "TIMEOUT" in err


# ── Isolation: docker only ───────────────────────────────────────────────
@needs_docker
class TestDockerRefusals:
    def test_network_refused(self, tmp_path):
        code, out, err, _ = DOCKER.run("probe.py", _script(tmp_path, (
            "import socket\n"
            "try:\n"
            "    socket.create_connection(('1.1.1.1', 53), timeout=3); print('OPEN')\n"
            "except OSError as e:\n"
            "    print('BLOCKED', type(e).__name__)\n")))
        assert code == 0, err
        assert out.startswith("BLOCKED")

    def test_write_to_code_mount_refused_and_host_untouched(self, tmp_path):
        code, out, err, _ = DOCKER.run("probe.py", _script(tmp_path, (
            "try:\n"
            "    open('/work/planted.py', 'w').write('x'); print('OPEN')\n"
            "except OSError as e:\n"
            "    print('BLOCKED', e.errno)\n")))
        assert code == 0, err
        assert out.startswith("BLOCKED")
        assert not (tmp_path / "planted.py").exists()

    def test_write_to_root_filesystem_refused(self, tmp_path):
        code, out, err, _ = DOCKER.run("probe.py", _script(tmp_path, (
            "import os\n"
            "try:\n"
            "    open('/usr/local/lib/evil.pth', 'w').write('x'); print('OPEN')\n"
            "except OSError as e:\n"
            "    print('BLOCKED', e.errno)\n")))
        assert code == 0, err
        assert out.startswith("BLOCKED")

    def test_host_filesystem_invisible(self, tmp_path):
        code, out, err, _ = DOCKER.run("probe.py", _script(tmp_path, (
            "import os\n"
            "print(sorted(os.listdir('/work')))\n"
            "print(os.path.exists('/c') or os.path.exists('/mnt/c') or os.path.exists('/host'))\n")))
        assert code == 0, err
        lines = out.strip().splitlines()
        assert lines[0] == "['probe.py']"
        assert lines[1] == "False"

    def test_runs_as_unprivileged_user(self, tmp_path):
        code, out, err, _ = DOCKER.run("probe.py", _script(tmp_path, "import os; print(os.getuid(), os.getgid())"))
        assert code == 0, err
        assert out.strip() == "65534 65534"

    def test_memory_bomb_killed(self, tmp_path):
        code, out, err, _ = DOCKER.run("probe.py", _script(
            tmp_path, "x = []\nwhile True: x.append(bytearray(16 * 1024 * 1024))"), timeout=60)
        assert code != 0
        assert code in (137, 1), f"unexpected exit {code}: {err[-300:]}"  # OOM kill, or MemoryError

    def test_fork_bomb_contained(self, tmp_path):
        code, out, err, _ = DOCKER.run("probe.py", _script(tmp_path, (
            "import os\n"
            "n = 0\n"
            "try:\n"
            "    for _ in range(1000):\n"
            "        if os.fork() == 0:\n"
            "            import time; time.sleep(30); os._exit(0)\n"
            "        n += 1\n"
            "except OSError:\n"
            "    print('LIMITED', n)\n")), timeout=60)
        assert "LIMITED" in out, f"exit {code}: {out[-200:]} {err[-200:]}"
        assert int(out.split()[-1]) < 64

    def test_infinite_loop_killed(self, tmp_path):
        code, _, err, secs = DOCKER.run("probe.py", _script(tmp_path, "while True: pass"), timeout=5)
        assert code == TIMEOUT_EXIT and "container killed" in err
        assert secs < 40

    def test_deterministic_env_seeds_hash_and_random(self, tmp_path):
        body = "import random; print(hash('crucible'), random.random())"
        a = DOCKER.run("probe.py", _script(tmp_path, body))
        b = DOCKER.run("probe.py", _script(tmp_path, body))
        assert a[0] == 0 and a[1] == b[1]

    def test_ordinary_code_still_works(self, tmp_path):
        (tmp_path / "solution.py").write_text("def f(xs):\n    return sorted(xs)\n", encoding="utf-8")
        code, out, err, _ = DOCKER.run("probe.py", _script(
            tmp_path, "import solution, json; print(json.dumps(solution.f([3, 1, 2])))"))
        assert code == 0, err
        assert out.strip() == "[1, 2, 3]"
