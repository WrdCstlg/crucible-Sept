"""The three arms of the SLA pilot. Each invocation performs ONE run and writes into --out:
  solution.py   the code that gets graded (arm B: first surviving branch; absent if nothing survived)
  meta.json     timing, token usage, cost, errors
  response.txt  raw model output (arms A and C)

  python experiment/arms.py A --out DIR   Gemini Flash, one locked-down call
  python experiment/arms.py C --out DIR   Claude Opus 5.5, one call, effort high, no tools
  python experiment/arms.py B --out DIR   Crucible with the same spec (2 approaches, max 2 rounds)

Arms A and C receive the identical system prompt and spec text. No arm ever sees the test cases.
"""
import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import run_crucible as rc  # noqa: E402  (also loads .env for both API keys)

SPEC_PATH = Path(os.environ.get("PILOT_SPEC", str(HERE / "sla" / "SPEC.md")))  # set by run_pilot.py --spec
SPEC = SPEC_PATH.read_text(encoding="utf-8")
SYSTEM = ("You are an expert Python engineer. Implement the specification you are given exactly. "
          "Respond with one complete, self-contained Python module in a single ```python code block and nothing else.")
CLAUDE_MODEL, CLAUDE_EFFORT, CLAUDE_MAX_TOKENS = "claude-opus-5-5", "high", 64000
CLAUDE_PRICE_IN, CLAUDE_PRICE_OUT = 4.00, 20.00  # USD per million tokens (first-party API)
B_PARADIGMS = ["Per-ticket state machine updated event by event",
               "Rebuild each ticket's running time intervals, then sum them"]
B_MAX_ROUNDS = 2


def write(out: Path, name: str, text: str):
    (out / name).write_text(text, encoding="utf-8")


def safe_usage(agent) -> dict:
    """Session token usage. Bookkeeping must never be able to discard a model's answer."""
    try:
        return agent.conversation.total_usage.model_dump()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


async def arm_a(out: Path) -> dict:
    from google.antigravity.models import DEFAULT_MODEL
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="pilot_a_") as tmp:
        config = rc._create_locked_down_agent_config(system_instructions=SYSTEM, temp_dir=tmp)
        async with rc.Agent(config) as agent:
            response = await agent.chat(SPEC)
            text = await response.text()
            write(out, "response.txt", text)
            write(out, "solution.py", rc.extract_code(text))
            usage = safe_usage(agent)
    return {"model": DEFAULT_MODEL, "seconds": round(time.time() - t0, 1), "usage": usage, "agent_calls": 1}


def arm_c(out: Path) -> dict:
    import anthropic
    t0 = time.time()
    client = anthropic.Anthropic()
    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=CLAUDE_MAX_TOKENS,
        system=SYSTEM,
        output_config={"effort": CLAUDE_EFFORT},
        messages=[{"role": "user", "content": SPEC}],
    ) as stream:
        message = stream.get_final_message()
    text = "".join(b.text for b in message.content if b.type == "text")
    write(out, "response.txt", text)
    u = message.usage
    meta = {"model": message.model, "effort": CLAUDE_EFFORT, "stop_reason": message.stop_reason,
            "seconds": round(time.time() - t0, 1), "agent_calls": 1,
            "usage": {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens},
            "cost_usd": round(u.input_tokens * CLAUDE_PRICE_IN / 1e6 + u.output_tokens * CLAUDE_PRICE_OUT / 1e6, 4)}
    if message.stop_reason == "refusal":
        meta["error"] = "refusal"
        return meta
    write(out, "solution.py", rc.extract_code(text))
    return meta


GEN_SYSTEM = ("You are an expert Python engineer. Implement the specification you are given exactly. "
              "Your module MUST expose a top-level `def compute_sla(stream):`. "
              "Implement it following this architectural approach: {paradigm}. "
              "Respond with one complete, self-contained Python module in a single ```python code block and nothing else.")
QA_SYSTEM = ("You are an adversarial QA engineer. Write a standalone Python test script for an untrusted module that "
             "implements the specification you are given. START YOUR CODE WITH 'import solution'. Call "
             "`solution.compute_sla(stream)` passing a list of CSV strings. Cover edge cases thoroughly: every cell of the "
             "state-transition table, the exact SLA boundary, ties, out-of-order events, malformed lines, the definition of "
             "'now', and output ordering and types. Compute every expected value by hand from the specification. Print a "
             "summary to stdout and call sys.exit(0) if and only if every test passes, otherwise sys.exit(1). "
             "Respond with the complete script in a single ```python code block.")
SYNTH_SYSTEM = ("You are the Lead Systems Architect. Review the execution logs of competing implementations. Discard any "
                "branch with a non-zero exit code or memory crash. Write a Ruthless Synthesis explaining exactly why the "
                "winner survived and the others failed, citing specific metrics from the terminal logs.")


class SpecCrucible(rc.CrucibleOrchestrator):
    """Crucible driven by SPEC.md instead of the built-in telemetry prompts. Same lockdown, same arena, same gate."""

    def __init__(self, run_dir: Path):
        super().__init__(problem_statement=SPEC, paradigms=B_PARADIGMS,
                         workspace_dir=str(run_dir / ".crucible_workspace"), mock_mode=False,
                         entrypoint="compute_sla", output_dir=str(run_dir), force_iterations=1)
        self.run_dir = run_dir
        self.calls = []
        (run_dir / "candidates").mkdir(exist_ok=True)

    async def _chat(self, role: str, system: str, prompt: str) -> str:
        t0 = time.time()
        with tempfile.TemporaryDirectory(prefix=f"crucible_{role}_") as tmp:
            config = rc._create_locked_down_agent_config(system_instructions=system, temp_dir=tmp)
            async with rc.Agent(config) as agent:
                response = await agent.chat(prompt)
                text = await response.text()
                usage = safe_usage(agent)
        self.calls.append({"role": role, "seconds": round(time.time() - t0, 1), "usage": usage})
        return text

    async def _generate_branch(self, index: int, paradigm: str, feedback: str):
        branch_dir = self.workspace / f"branch_{index}"
        if branch_dir.exists():
            shutil.rmtree(branch_dir)
        branch_dir.mkdir(parents=True)
        self.branches.append(branch_dir)
        prompt = f"{SPEC}\n\nYou MUST use this architectural approach: {paradigm}"
        if feedback:
            prompt += f"\n\n{feedback}"
        code = rc.extract_code(await self._chat("gen", GEN_SYSTEM.format(paradigm=paradigm), prompt))
        (branch_dir / "solution.py").write_text(code, encoding="utf-8")
        round_no = len(self.test_suites) + 1
        (self.run_dir / "candidates" / f"round{round_no}_branch_{index}.py").write_text(code, encoding="utf-8")
        print(f"   [+] Generated branch_{index} ({paradigm})")

    async def _generate_test_harness(self, iteration: int = 1) -> Path:
        test_path = self.workspace / f"arena_test_iter_{iteration}.py"
        text = await self._chat("qa", QA_SYSTEM, f"Write an adversarial test script for this specification:\n\n{SPEC}")
        test_path.write_text(rc.extract_code(text), encoding="utf-8")
        shutil.copy(test_path, self.run_dir / "candidates" / f"round{iteration}_crucible_tests.py")
        return test_path

    async def _synthesize_results(self, results) -> str:
        payload = "ARENA EXECUTION LOGS:\n\n"
        for r in results:
            payload += (f"--- {r.name} ({r.paradigm}) ---\nStatus: {r.status} | Exit Code: {r.exit_code} | "
                        f"Duration: {r.duration_seconds}s\nSTDOUT:\n{self._sanitize_paths(r.stdout)}\n"
                        f"STDERR:\n{self._sanitize_paths(r.stderr)}\n\n")
        return self._sanitize_paths(await self._chat("synth", SYNTH_SYSTEM, payload))


async def arm_b(out: Path, crucible_cls=None) -> dict:
    t0 = time.time()
    orchestrator = (crucible_cls or SpecCrucible)(out)
    await orchestrator.run(max_iterations=B_MAX_ROUNDS)
    summary = orchestrator.telemetry["summary"]
    verdicts = {}
    for it in orchestrator.telemetry["iterations"]:
        for b in it["branches"]:
            verdicts[f"round{it['iteration']}_{b['name']}"] = b["status"]
    winners = sorted(summary.get("winning_branches", []))
    if winners:
        shutil.copy(orchestrator.workspace / winners[0] / "solution.py", out / "solution.py")
    return {"model": "gemini (Crucible)", "seconds": round(time.time() - t0, 1), "agent_calls": len(orchestrator.calls),
            "calls": orchestrator.calls, "rounds_run": summary.get("total_iterations_run"),
            "crucible_status": summary.get("status"), "winners": winners, "graded_branch": winners[0] if winners else None,
            "crucible_verdicts": verdicts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arm", choices=["A", "B", "C"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    try:
        if a.arm == "A":
            meta = asyncio.run(arm_a(out))
        elif a.arm == "B":
            meta = asyncio.run(arm_b(out))
        else:
            meta = arm_c(out)
    except Exception as e:
        meta = {"error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-2000:]}
    meta["arm"] = a.arm
    meta["spec"] = SPEC_PATH.name
    write(out, "meta.json", json.dumps(meta, indent=2, default=str))
    print(json.dumps({k: v for k, v in meta.items() if k not in ("calls", "traceback", "usage")}, default=str))
    sys.exit(1 if "error" in meta else 0)


if __name__ == "__main__":
    main()
