"""Provider-agnostic model calls for the evaluation rig.

    completion = generate(role_config, system_prompt, user_prompt)

Plain completion APIs only. No tools are ever declared, so no role can read, write or run anything:
isolation holds by construction rather than by policy. Any tool call a model attempts anyway is
counted in `Completion.tool_calls` so the audit can verify it stayed at zero.

Supported providers (set per role in roles.json):
  anthropic          Claude models via the Anthropic SDK (streaming; `effort` setting supported)
  google             Gemini models via the google-genai SDK (optional `thinking_level` or `thinking_budget`)
  openai_compatible  Any OpenAI-compatible endpoint: OpenAI, Moonshot Kimi, LM Studio, Ollama, vLLM
"""
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv

RIG = Path(__file__).resolve().parent
PROJECT_ROOT = RIG.parent.parent
load_dotenv(PROJECT_ROOT / ".env")
ROLES_FILE = RIG / "roles.json"


@dataclass
class Completion:
    text: str
    provider: str
    model: str                   # model ID as reported by the provider
    input_tokens: int | None
    output_tokens: int | None    # everything billed as output, including thinking
    thinking_tokens: int | None
    cost_usd: float | None
    seconds: float
    stop_reason: str | None
    tool_calls: int              # must be 0: no tools are declared

    def usage(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k not in ("text",)}


def load_roles(path: Path = ROLES_FILE) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _cost(cfg, input_tokens, output_tokens):
    price = cfg.get("price_per_mtok")
    if not price or input_tokens is None or output_tokens is None:
        return None
    return round(input_tokens * price["input"] / 1e6 + output_tokens * price["output"] / 1e6, 5)


def _key(cfg, default_env):
    name = cfg.get("api_key_env", default_env)
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set in .env")
    return value


def _anthropic(cfg, system, prompt):
    import anthropic
    s = cfg.get("settings", {})
    client = anthropic.Anthropic(api_key=_key(cfg, "ANTHROPIC_API_KEY"))
    kwargs = {"model": cfg["model"], "max_tokens": s.get("max_tokens", 64000), "system": system,
              "messages": [{"role": "user", "content": prompt}]}
    if s.get("effort"):
        kwargs["output_config"] = {"effort": s["effort"]}
    with client.messages.stream(**kwargs) as stream:
        m = stream.get_final_message()
    text = "".join(b.text for b in m.content if b.type == "text")
    tool_calls = sum(1 for b in m.content if b.type == "tool_use")
    return text, m.model, m.usage.input_tokens, m.usage.output_tokens, None, m.stop_reason, tool_calls


def _google(cfg, system, prompt):
    from google import genai
    from google.genai import types
    s = cfg.get("settings", {})
    client = genai.Client(api_key=_key(cfg, "GEMINI_API_KEY"))
    config = types.GenerateContentConfig(system_instruction=system, max_output_tokens=s.get("max_tokens", 65536))
    if "thinking_level" in s:
        config.thinking_config = types.ThinkingConfig(thinking_level=types.ThinkingLevel(s["thinking_level"]))
    elif "thinking_budget" in s:
        config.thinking_config = types.ThinkingConfig(thinking_budget=s["thinking_budget"])
    if "temperature" in s:
        config.temperature = s["temperature"]
    if "seed" in s:
        config.seed = s["seed"]
    r = client.models.generate_content(model=cfg["model"], contents=prompt, config=config)
    parts = [p for c in (r.candidates or []) for p in ((c.content.parts if c.content else None) or [])]
    text = "".join(p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False))
    tool_calls = sum(1 for p in parts if getattr(p, "function_call", None))
    u = r.usage_metadata
    thinking = u.thoughts_token_count or 0
    output = (u.candidates_token_count or 0) + thinking
    stop = r.candidates[0].finish_reason.name if r.candidates and r.candidates[0].finish_reason else None
    return text, r.model_version or cfg["model"], u.prompt_token_count, output, thinking, stop, tool_calls


def _openai_compatible(cfg, system, prompt):
    from openai import OpenAI
    s = cfg.get("settings", {})
    base_url = os.environ.get(cfg.get("base_url_env", ""), "").strip() or cfg.get("base_url")
    client = OpenAI(api_key=_key(cfg, "OPENAI_API_KEY"), base_url=base_url or None)
    kwargs = {"model": cfg["model"], "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
    if "max_tokens" in s:
        kwargs["max_tokens"] = s["max_tokens"]
    if "temperature" in s:
        kwargs["temperature"] = s["temperature"]
    if "seed" in s:
        kwargs["seed"] = s["seed"]
    r = client.chat.completions.create(**kwargs)
    msg = r.choices[0].message
    details = getattr(r.usage, "completion_tokens_details", None)
    thinking = getattr(details, "reasoning_tokens", None) if details else None
    return (msg.content or "", r.model, r.usage.prompt_tokens, r.usage.completion_tokens, thinking,
            r.choices[0].finish_reason, len(msg.tool_calls or []))


ADAPTERS = {"anthropic": _anthropic, "google": _google, "openai_compatible": _openai_compatible}


def generate(cfg: dict, system: str, prompt: str) -> Completion:
    t0 = time.time()
    text, model, tin, tout, thinking, stop, tools = ADAPTERS[cfg["provider"]](cfg, system, prompt)
    return Completion(text=text, provider=cfg["provider"], model=model, input_tokens=tin, output_tokens=tout,
                      thinking_tokens=thinking, cost_usd=_cost(cfg, tin, tout), seconds=round(time.time() - t0, 1),
                      stop_reason=stop, tool_calls=tools)
