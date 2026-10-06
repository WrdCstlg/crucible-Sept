"""experiment/rig/providers.py: the per-request timeout reaches each SDK client, and stays off unless asked for.

No network: each SDK client constructor is replaced by a recorder that raises before any request is made.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiment"))
from rig import providers  # noqa: E402


class _Stop(Exception):
    pass


def _recorder(seen):
    def ctor(*args, **kwargs):
        seen.append(kwargs)
        raise _Stop
    return ctor


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(name, "test-not-a-real-key")
    monkeypatch.delenv("CRUCIBLE_REQUEST_TIMEOUT_S", raising=False)


def test_timeout_resolution_order_and_validation(monkeypatch):
    assert providers.request_timeout_s({}) is None
    monkeypatch.setenv("CRUCIBLE_REQUEST_TIMEOUT_S", "300")
    assert providers.request_timeout_s({}) == 300.0
    assert providers.request_timeout_s({"settings": {"request_timeout_s": 120}}) == 120.0   # setting wins
    with pytest.raises(ValueError):
        providers.request_timeout_s({"settings": {"request_timeout_s": 0}})


def test_google_client_gets_timeout_in_milliseconds(monkeypatch):
    genai = pytest.importorskip("google.genai")
    from google.genai import types
    seen = []
    monkeypatch.setattr(genai, "Client", _recorder(seen))
    cfg = {"provider": "google", "model": "gemini-3.8-flash", "settings": {"request_timeout_s": 600}}
    with pytest.raises(_Stop):
        providers.generate(cfg, "sys", "prompt")
    opts = seen[0]["http_options"]
    assert isinstance(opts, types.HttpOptions) and opts.timeout == 600_000


def test_google_client_untouched_when_no_timeout(monkeypatch):
    genai = pytest.importorskip("google.genai")
    seen = []
    monkeypatch.setattr(genai, "Client", _recorder(seen))
    with pytest.raises(_Stop):
        providers.generate({"provider": "google", "model": "gemini-3.8-flash"}, "sys", "prompt")
    assert "http_options" not in seen[0]


@pytest.mark.parametrize("module,attr,provider", [("anthropic", "Anthropic", "anthropic"),
                                                  ("openai", "OpenAI", "openai_compatible")])
def test_anthropic_and_openai_clients_get_timeout_in_seconds(monkeypatch, module, attr, provider):
    mod = pytest.importorskip(module)
    seen = []
    monkeypatch.setattr(mod, attr, _recorder(seen))
    monkeypatch.setenv("CRUCIBLE_REQUEST_TIMEOUT_S", "450")
    with pytest.raises(_Stop):
        providers.generate({"provider": provider, "model": "m"}, "sys", "prompt")
    assert seen[0]["timeout"] == 450.0
