"""The study harness's safety rails and pre-registered analysis (experiment/study, experiment/PREREGISTRATION.md).

These test that the harness REFUSES what it must refuse (uncapped spend, unpriced models, an extra model call, an
oversized prompt, a live run without a committed pre-registration, live output outside Docker), that the spend cap
holds under concurrency, and that the analysis computes exactly the pre-registered statistics. The slow test runs
a full zero-cost mock study end to end and checks every grade against ground truth the harness cannot see.
"""
import importlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / "experiment"
STUDY = EXP / "study"
BIZ = EXP / "bizsla"
for p in (str(ROOT), str(EXP), str(STUDY), str(BIZ)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("PILOT_SPEC", str(BIZ / "SPEC.md"))
os.environ.setdefault("CRUCIBLE_ROLES", str(STUDY / "roles_mock.json"))

import run_study  # noqa: E402
import stats  # noqa: E402


@pytest.fixture(scope="module")
def arm_study():
    return importlib.import_module("arm_study")


def roles(path="roles_mock.json"):
    return json.loads((STUDY / path).read_text(encoding="utf-8"))


# ── Ceilings and the spend cap ─────────────────────────────────────────────
def test_call_ceilings_agree_between_runner_and_arm(arm_study):
    assert run_study.CALLS_PER_RUN == arm_study.CALL_LIMIT


def test_worst_case_is_exact_ceiling_arithmetic():
    r = roles()
    # B: 10 calls x (60000 in x $1 + 4000 out x $1) / 1e6
    assert run_study.worst_case_run("B", r) == pytest.approx(0.64)
    assert run_study.worst_case_run("A", r) == pytest.approx(0.064)
    # C: 1 call x (20000 x $2 + 4000 x $2) / 1e6
    assert run_study.worst_case_run("C", r) == pytest.approx(0.048)
    live = roles("roles_study.json")
    assert run_study.worst_case_run("C", live) == pytest.approx((20000 * 4.0 + 64000 * 20.0) / 1e6)


@pytest.mark.parametrize("price", [None, {}, 0])
def test_unpriced_role_refuses(price):
    r = roles()
    r["evaluated"]["price_per_mtok"] = price
    with pytest.raises(SystemExit, match="no price_per_mtok"):
        run_study.worst_case_run("A", r)


def test_live_roles_file_is_refused_until_gemini_is_priced():
    live = roles("roles_study.json")
    if live["evaluated"]["price_per_mtok"] is None:
        with pytest.raises(SystemExit):
            run_study.worst_case_run("B", live)


def test_budget_refuses_past_cap_and_charges_unknown_cost_at_ceiling():
    b = run_study.Budget(1.0)
    assert b.reserve(0.6)
    assert not b.reserve(0.5)                     # 0.6 reserved + 0.5 > 1.0
    b.settle(0.6, None)                           # unknown cost -> full ceiling charged
    assert b.spent == pytest.approx(0.6) and b.reserved == pytest.approx(0)
    assert b.reserve(0.4) and not b.reserve(0.01)
    b.settle(0.4, 0.1)
    assert b.spent == pytest.approx(0.7)
    assert b.halted is None


def test_budget_halts_all_launches_when_a_run_exceeds_its_ceiling():
    b = run_study.Budget(100.0)
    assert b.reserve(1.0)
    b.settle(1.0, 1.5)
    assert b.halted and "above its reserved worst case" in b.halted
    assert not b.reserve(0.0001)


def test_budget_holds_under_concurrency():
    b = run_study.Budget(10.0)
    ok = []
    barrier = threading.Barrier(64)

    def go():
        barrier.wait()
        ok.append(b.reserve(1.0))

    ts = [threading.Thread(target=go) for _ in range(64)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sum(ok) == 10 and b.reserved == pytest.approx(10.0)


def test_schedule_interleaves_so_a_cap_truncates_arms_evenly():
    order = run_study.schedule({"A": 3, "B": 2, "C": 3})
    assert order == ["A1", "C1", "B1", "A2", "C2", "B2", "A3", "C3"]
    full = run_study.schedule({"A": 30, "B": 20, "C": 30})
    assert len(full) == len(set(full)) == 80
    for cut in range(1, len(full)):
        counts = {a: sum(1 for x in full[:cut] if x[0] == a) for a in "ABC"}
        if cut <= 60:                              # while B still has runs left, no arm leads another by > 1
            assert max(counts.values()) - min(counts.values()) <= 1


# ── The call/prompt guard inside each arm ──────────────────────────────────
def test_guard_refuses_extra_call_and_oversized_prompt(arm_study, monkeypatch):
    seen = []
    monkeypatch.setattr(arm_study, "_real_generate", lambda cfg, s, p: seen.append(p) or "ok")
    monkeypatch.setitem(arm_study._state, "arm", "A")
    monkeypatch.setitem(arm_study._state, "calls", 0)
    cfg = {"max_input_tokens_per_call": 1000}
    assert arm_study.guarded_generate(cfg, "sys", "prompt") == "ok"
    with pytest.raises(arm_study.BudgetGuard, match="exceeds the 1-call ceiling"):
        arm_study.guarded_generate(cfg, "sys", "prompt")
    assert len(seen) == 1                          # the refused call never reached the provider

    monkeypatch.setitem(arm_study._state, "arm", "B")
    monkeypatch.setitem(arm_study._state, "calls", 0)
    with pytest.raises(arm_study.BudgetGuard, match="exceeds max_input_tokens_per_call"):
        arm_study.guarded_generate(cfg, "", "x" * 2501)   # 2501 / 2.5 > 1000 tokens
    assert len(seen) == 1
    for _ in range(9):
        arm_study.guarded_generate(cfg, "", "x")
    with pytest.raises(arm_study.BudgetGuard):
        arm_study.guarded_generate(cfg, "", "x")         # the 11th call of arm B


def test_guard_is_installed_on_the_provider_module(arm_study):
    assert arm_study.rig.providers.generate is arm_study.guarded_generate


# ── Pre-registered exclusion rule ──────────────────────────────────────────
@pytest.mark.parametrize("status,meta,excluded", [
    ("done", {"cost_usd": 0.1}, False),
    ("error", {"error": "refusal"}, False),                                   # refusal counts as failure
    ("timeout", {"error": "no meta"}, False),                                 # timeout counts as failure
    ("error", {"error": "BudgetGuard: x", "traceback": "...", "model_attributable": True}, False),
    ("error", {"error": "ConnectionError: x", "traceback": "..."}, True),     # harness / infrastructure crash
    ("error", {"error": "no meta"}, True),
])
def test_harness_error_rule(status, meta, excluded):
    assert run_study.is_harness_error({"status": status, "meta": meta}) is excluded


# ── Pre-registered analysis ────────────────────────────────────────────────
def _rows(arm, passes, fails, harness=0):
    out = [{"arm": arm, "harness_error": False, "strict_pass": True, "cases_passed": 225, "cost_usd": 0.01}] * passes
    out += [{"arm": arm, "harness_error": False, "strict_pass": False, "cases_passed": 100, "cost_usd": 0.01}] * fails
    out += [{"arm": arm, "harness_error": True, "strict_pass": True, "cases_passed": 225, "cost_usd": None}] * harness
    return out


def test_analysis_matches_independent_fisher_and_excludes_harness_errors():
    scipy_stats = pytest.importorskip("scipy.stats")
    rows = _rows("B", 16, 4) + _rows("C", 12, 18, harness=2) + _rows("A", 6, 24)
    an = run_study.analyze(rows, [], [], {"A": 30, "B": 20, "C": 30})
    assert an["arms"]["C"]["valid"] == 30 and an["arms"]["C"]["harness_errors"] == 2
    assert an["arms"]["C"]["strict_passes"] == 12           # harness-error "passes" never count
    p = scipy_stats.fisher_exact([[16, 4], [12, 18]], alternative="two-sided")[1]
    assert an["H1_B_vs_C"]["p_two_sided"] == pytest.approx(p, abs=1e-5)
    assert an["H1_B_vs_C"]["verdict"].startswith("B higher than C")
    assert an["arms"]["B"]["wilson95"] == [round(x, 3) for x in stats.wilson(16, 20)]
    assert an["integrity"]["compromised"] is False           # 2 <= 10% of 30


def test_analysis_null_result_states_detectable_gap_not_equivalence():
    rows = _rows("B", 9, 11) + _rows("C", 12, 18) + _rows("A", 10, 20)
    v = run_study.analyze(rows, [], [], {"A": 30, "B": 20, "C": 30})["H1_B_vs_C"]["verdict"]
    assert v.startswith("no detectable difference") and "could not be detected at 80% power" in v


def test_analysis_flags_compromised_when_harness_errors_exceed_ten_percent():
    rows = _rows("B", 10, 7, harness=3) + _rows("C", 15, 15) + _rows("A", 15, 15)
    an = run_study.analyze(rows, [], [], {"A": 30, "B": 20, "C": 30})
    assert an["integrity"] == {"harness_error_limit": "10% of planned runs per arm", "arms_over_limit": ["B"],
                               "compromised": True}
    summary = {"config": {"mock": False, "prereg": {"sha256": "0" * 64}, "hidden_cases": 225, "cap_usd": 1.0,
                          "labels": {"A": "A", "B": "B", "C": "C"}},
               "spent_usd": 0.5, "analysis": an, "not_run": [], "runs": []}
    assert "COMPROMISED" in run_study.render(summary)


def test_analysis_h3_and_h4_counting():
    cands = [{"crucible_verdict": "PASS", "hidden_pass": True}, {"crucible_verdict": "PASS", "hidden_pass": False},
             {"crucible_verdict": "FAIL", "hidden_pass": True}, {"crucible_verdict": "FAIL", "hidden_pass": False},
             {"crucible_verdict": None, "hidden_pass": True}]
    gates = [{"gate_admits": True, "independently_strong": True, "agree": True},
             {"gate_admits": False, "independently_strong": False, "agree": True},
             {"gate_admits": True, "independently_strong": False, "agree": False}]
    an = run_study.analyze(_rows("A", 1, 1) + _rows("B", 1, 1) + _rows("C", 1, 1), cands, gates,
                           {"A": 2, "B": 2, "C": 2})
    h3, h4 = an["H3_crucible_vs_hidden"], an["H4_gate_out_of_sample"]
    assert (h3["promoted"], h3["promoted_but_fail_hidden"], h3["rejected_but_pass_hidden"]) == (2, 1, 1)
    assert (h4["false_security"], h4["lost_signal"], h4["agreement"]) == (1, 0, "2/3")
    assert h4["criterion_met"] is False                     # any false security fails the pre-registered criterion
    gates[2] = {"gate_admits": False, "independently_strong": False, "agree": True}
    h4 = run_study.analyze(_rows("A", 1, 1) + _rows("B", 1, 1) + _rows("C", 1, 1), cands, gates,
                           {"A": 2, "B": 2, "C": 2})["H4_gate_out_of_sample"]
    assert h4["criterion_met"] is True


def test_analysis_with_an_empty_arm_is_undefined_not_a_crash():
    an = run_study.analyze(_rows("A", 1, 1) + _rows("C", 1, 1), [], [], {"A": 2, "B": 2, "C": 2})
    assert an["H1_B_vs_C"]["p_two_sided"] is None and "undefined" in an["H1_B_vs_C"]["verdict"]


# ── Pre-flight refusals of the real CLI ────────────────────────────────────
def _cli(*args, env=None):
    return subprocess.run([sys.executable, str(STUDY / "run_study.py"), *args], cwd=ROOT, capture_output=True,
                          text=True, timeout=120, env={**os.environ, **(env or {})})


def test_cli_requires_a_spend_cap():
    r = _cli("--mock", "--plan-only")
    assert r.returncode != 0 and "--cap-usd is required" in r.stdout + r.stderr


def test_cli_live_run_refuses_unpriced_or_uncommitted(tmp_path):
    live = roles("roles_study.json")
    live["evaluated"]["price_per_mtok"] = None
    p = tmp_path / "roles.json"
    p.write_text(json.dumps(live), encoding="utf-8")
    r = _cli("--plan-only", "--cap-usd", "1", "--roles", str(p))
    out = r.stdout + r.stderr
    assert r.returncode != 0 and "STOP:" in out
    assert "PREREGISTRATION.md must be committed" in out or "no price_per_mtok" in out


def test_cli_refuses_live_output_outside_docker(tmp_path):
    live = roles("roles_study.json")
    live["evaluated"]["price_per_mtok"] = {"input": 1.0, "output": 1.0}
    p = tmp_path / "roles.json"
    p.write_text(json.dumps(live), encoding="utf-8")
    r = _cli("--cap-usd", "1", "--roles", str(p), "--unsafe-subprocess-sandbox")
    assert r.returncode != 0 and "only ever executed in the Docker sandbox" in r.stdout + r.stderr


def test_prereg_missing_refuses(monkeypatch, tmp_path):
    monkeypatch.setattr(run_study, "PREREG", tmp_path / "nope.md")
    with pytest.raises(SystemExit, match="PREREGISTRATION.md is missing"):
        run_study.prereg_status(require_committed=False)


def test_prereg_records_its_hash():
    assert run_study.prereg_status(require_committed=False)["sha256"] == run_study.sha(run_study.PREREG)


# ── Zero-cost mock study end to end ────────────────────────────────────────
@pytest.mark.slow
def test_mock_study_end_to_end_grades_against_ground_truth(tmp_path):
    """Runs the real runner (real subprocesses, real Crucible loop, real grader, real gate) on the mock provider.
    The mock writes either the trusted reference or a planted-bug copy; the hidden grader must pass a run
    exactly when its solution is byte-identical to the reference. The cap is set so B2 cannot be afforded."""
    unsafe = os.environ.get("CRUCIBLE_SANDBOX") == "subprocess-unsafe"
    args = ["--mock", "--a-runs", "2", "--b-runs", "2", "--c-runs", "2", "--cap-usd", "0.9",
            "--out-root", str(tmp_path)] + (["--unsafe-subprocess-sandbox"] if unsafe else [])
    r = subprocess.run([sys.executable, str(STUDY / "run_study.py"), *args], cwd=ROOT, capture_output=True,
                       text=True, timeout=3600)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    run_dir = next(tmp_path.glob("study_mock_*"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["config"]["mock"] is True and "MOCK DRY RUN" in (run_dir / "RESULTS.md").read_text("utf-8")
    # cap: A 2x0.064 + C 2x0.048 + one B 0.64 = 0.864 <= 0.9; a second B would need another 0.64. Which B run
    # reserves first is thread-order dependent; exactly one must be refused.
    assert len(summary["not_run"]) == 1 and summary["not_run"][0].startswith("B")
    assert summary["spent_usd"] <= 0.9
    reference = (BIZ / "reference.py").read_text(encoding="utf-8").strip()
    assert len(summary["runs"]) == 5
    for row in summary["runs"]:
        assert not row["harness_error"], row
        sol = run_dir / row["run"] / "solution.py"
        is_ref = sol.exists() and sol.read_text(encoding="utf-8").strip() == reference
        assert row["strict_pass"] is is_ref, row   # the grader agrees with ground truth on every run
        assert row["cases_total"] == 225
    b = [c for c in summary["b_candidates"]]
    assert b, "arm B produced no candidates"
    for c in b:
        cand = (run_dir / c["run"] / "candidates" / f"{c['candidate']}.py").read_text(encoding="utf-8").strip()
        assert c["hidden_pass"] is (cand == reference), c
    assert summary["gate_out_of_sample"], "H4 evaluated no suites"
    for g in summary["gate_out_of_sample"]:
        # the mock QA suite only encodes the 4 public examples: it must not be admitted as strong
        assert g["gate_admits"] is False and g["independently_strong"] is False
