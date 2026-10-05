"""One run of one study arm (pre-registered in experiment/PREREGISTRATION.md).

    python experiment/study/arm_study.py A --out DIR    evaluated role, one call
    python experiment/study/arm_study.py B --out DIR    evaluated role inside Crucible (deterministic policy)
    python experiment/study/arm_study.py C --out DIR    competitor role, one call

Environment (set by run_study.py): PILOT_SPEC = experiment/bizsla/SPEC.md, CRUCIBLE_ROLES = the roles file.

Information parity: every arm sees exactly SPEC.md. Arm B's only ground truth is the 4 worked examples printed in
SPEC.md (public_cases.json), used as acceptance cases. Arm B gets no reference solution, so its AI-written suites
can never decide a verdict (advisory only); the hidden grader is never visible to any arm.
"""
import argparse
import asyncio
import json
import shutil
import sys
import threading
import time
import traceback
from pathlib import Path

STUDY = Path(__file__).resolve().parent
EXP = STUDY.parent
ROOT = EXP.parent
sys.path.insert(0, str(EXP / "rig"))
sys.path.insert(0, str(EXP))
sys.path.insert(0, str(ROOT))
import arm as rig  # noqa: E402  (providers, RigCrucible, single_call)
import arms as base  # noqa: E402
import run_crucible as rc  # noqa: E402

PUBLIC = EXP / "bizsla" / "public_cases.json"
STUDY_PARADIGMS = ["Per-ticket state machine that advances each ticket with closed-form business-minute arithmetic",
                   "Event sweep that rebuilds each ticket's running intervals, then counts business minutes per interval"]
B_MAX_ROUNDS = 2
CALL_LIMIT = {"A": 1, "C": 1, "B": 10}          # must equal run_study.CALLS_PER_RUN (checked by tests/test_study.py)
CHARS_PER_TOKEN_FLOOR = 2.5                       # conservative: real text averages ~4 characters per token


class BudgetGuard(RuntimeError):
    """A call that would break the worst case the spend cap reserved for this run."""


_state = {"arm": None, "calls": 0}
_lock = threading.Lock()
_real_generate = rig.providers.generate


def guarded_generate(cfg, system, prompt):
    with _lock:
        _state["calls"] += 1
        n = _state["calls"]
    if n > CALL_LIMIT[_state["arm"]]:
        raise BudgetGuard(f"call {n} exceeds the {CALL_LIMIT[_state['arm']]}-call ceiling for arm {_state['arm']}")
    est = (len(system) + len(prompt)) / CHARS_PER_TOKEN_FLOOR
    if est > cfg.get("max_input_tokens_per_call", 60000):
        raise BudgetGuard(f"prompt of ~{est:.0f} tokens exceeds max_input_tokens_per_call")
    return _real_generate(cfg, system, prompt)


rig.providers.generate = guarded_generate


class StudyCrucible(rig.RigCrucible):
    """RigCrucible on the deterministic verdict policy, with the spec's public examples as acceptance cases."""

    def __init__(self, run_dir: Path):
        rc.CrucibleOrchestrator.__init__(
            self, problem_statement=base.SPEC, paradigms=STUDY_PARADIGMS,
            workspace_dir=str(run_dir / ".crucible_workspace"), mock_mode=False, entrypoint="compute_sla",
            output_dir=str(run_dir), force_iterations=1, verdict_policy="deterministic",
            acceptance_cases=rc.load_acceptance_cases(str(PUBLIC)))
        self.run_dir = run_dir
        self.calls = []
        (run_dir / "candidates").mkdir(exist_ok=True)


async def arm_b(out: Path) -> dict:
    """Inlined rather than base.arm_b: that function is tied to the SLA pilot's labels."""
    t0 = time.time()
    orch = StudyCrucible(out)
    await orch.run(max_iterations=B_MAX_ROUNDS)
    summary = orch.telemetry["summary"]
    verdicts = {f"round{it['iteration']}_{b['name']}": b["status"]
                for it in orch.telemetry["iterations"] for b in it["branches"]}
    winners = sorted(summary.get("winning_branches", []))
    if winners:
        shutil.copy(orch.workspace / winners[0] / "solution.py", out / "solution.py")
    meta = {"model": rig.ROLES["evaluated"]["model"], "seconds": round(time.time() - t0, 1),
            "agent_calls": len(orch.calls), "calls": orch.calls, "rounds_run": summary.get("total_iterations_run"),
            "crucible_status": summary.get("status"), "winners": winners,
            "graded_branch": winners[0] if winners else None, "crucible_verdicts": verdicts,
            "verdict_policy": "deterministic", "acceptance_cases": "SPEC.md examples (4)",
            "cost_usd": _sum_cost(orch.calls)}
    return meta


def _sum_cost(calls):
    costs = [c.get("cost_usd") for c in calls]
    return None if any(c is None for c in costs) else round(sum(costs), 5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arm", choices=["A", "B", "C"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    _state["arm"] = a.arm
    try:
        if a.arm == "A":
            meta = rig.single_call("evaluated", out)
        elif a.arm == "C":
            meta = rig.single_call("competitor", out)
        else:
            meta = asyncio.run(arm_b(out))
    except BudgetGuard as e:
        # Pre-registered: a run that hits its call/prompt ceiling is a FAILED run (counted), not a harness error.
        meta = {"error": f"BudgetGuard: {e}", "model_attributable": True, "cost_usd": None,
                "traceback": traceback.format_exc()[-2000:]}
    except Exception as e:
        meta = {"error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-2000:]}
    meta["arm"] = a.arm
    meta["runner"] = "study"
    meta["spec"] = base.SPEC_PATH.name
    meta["roles_provider"] = {k: v["provider"] for k, v in rig.ROLES.items()}
    base.write(out, "meta.json", json.dumps(meta, indent=2, default=str))
    print(json.dumps({k: v for k, v in meta.items() if k not in ("calls", "traceback", "usage")}, default=str))
    sys.exit(1 if "error" in meta else 0)


if __name__ == "__main__":
    main()
