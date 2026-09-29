"""One run of one arm through the provider-agnostic rig. Same CLI and output files as experiment/arms.py:

  python experiment/rig/arm.py A --out DIR   evaluated role, one call
  python experiment/rig/arm.py B --out DIR   evaluated role inside Crucible (every agent call uses the evaluated role)
  python experiment/rig/arm.py C --out DIR   competitor role, one call

Models are chosen in rig/roles.json. Every call is a plain completion with no tools declared.
Arms A and C receive the identical system prompt and spec text as in experiment/arms.py.
"""
import argparse
import asyncio
import json
import sys
import traceback
from pathlib import Path

RIG = Path(__file__).resolve().parent
sys.path.insert(0, str(RIG))
sys.path.insert(0, str(RIG.parent))
import providers  # noqa: E402
import arms as base  # noqa: E402  (spec, prompts, SpecCrucible, run_crucible)

ROLES = providers.load_roles()


def usage(c):
    return {"input_tokens": c.input_tokens, "output_tokens": c.output_tokens, "thinking_tokens": c.thinking_tokens}


def single_call(role: str, out: Path) -> dict:
    c = providers.generate(ROLES[role], base.SYSTEM, base.SPEC)
    base.write(out, "response.txt", c.text)
    meta = {"role": role, "provider": c.provider, "model": c.model, "seconds": c.seconds, "agent_calls": 1,
            "usage": usage(c), "cost_usd": c.cost_usd, "stop_reason": c.stop_reason, "tool_calls": c.tool_calls}
    if c.stop_reason == "refusal":
        meta["error"] = "refusal"
        return meta
    base.write(out, "solution.py", base.rc.extract_code(c.text))
    return meta


class RigCrucible(base.SpecCrucible):
    """Crucible whose code writers, test writer and synthesis agent all call the evaluated role."""

    async def _chat(self, role: str, system: str, prompt: str) -> str:
        c = await asyncio.to_thread(providers.generate, ROLES["evaluated"], system, prompt)
        self.calls.append({"role": role, "provider": c.provider, "model": c.model, "seconds": c.seconds,
                           "usage": usage(c), "cost_usd": c.cost_usd, "stop_reason": c.stop_reason,
                           "tool_calls": c.tool_calls})
        return c.text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arm", choices=["A", "B", "C"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    try:
        if a.arm == "A":
            meta = single_call("evaluated", out)
        elif a.arm == "C":
            meta = single_call("competitor", out)
        else:
            meta = asyncio.run(base.arm_b(out, RigCrucible))
            meta["role"] = "evaluated"
            meta["model"] = ROLES["evaluated"]["model"]
            meta["tool_calls"] = sum(c.get("tool_calls", 0) for c in meta.get("calls", []))
    except Exception as e:
        meta = {"error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-2000:]}
    meta["arm"] = a.arm
    meta["runner"] = "rig"
    meta["spec"] = base.SPEC_PATH.name
    base.write(out, "meta.json", json.dumps(meta, indent=2, default=str))
    print(json.dumps({k: v for k, v in meta.items() if k not in ("calls", "traceback", "usage")}, default=str))
    sys.exit(1 if "error" in meta else 0)


if __name__ == "__main__":
    main()
