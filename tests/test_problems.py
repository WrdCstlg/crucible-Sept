"""The candidate problems (experiment/problems/) and their screening harness (screen.py).

These are SCREENING artifacts with a single oracle each (reference.py), so the tests attack the oracle from the
sides that do not depend on it:
  * every hand-derived expected output (written from SPEC.md, not from the reference) must equal the reference's;
  * the stored expected outputs are exactly what a fresh build produces (nothing hand-edited or stale);
  * the comparison is strict (1 != 1.0, True != 1, tuples / non-str keys / NaN rejected; key order irrelevant);
  * every planted bug applies to exactly one place, changes the code, and is caught by a scored (non-public) case;
  * the screening harness refuses uncapped or mixed mock/live runs and its keep rule is the one documented.
Slow tests: the Docker self-test per problem, and a zero-cost mock screening run end to end whose grades are checked
against ground truth the harness cannot see (is the graded file byte-identical to the reference?).
Planted-bug and reference code is trusted (written here); only the slow tests execute anything through the sandbox.
"""
import ast
import copy
import hashlib
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROB = ROOT / "experiment" / "problems"
PROBLEMS = ["orderbook", "semver", "sheet", "promo", "payroll",
            "policy", "washsale", "roster", "reconcile", "recur", "schema", "ignore", "merge3"]
if str(PROB) not in sys.path:
    sys.path.insert(0, str(PROB))

import common  # noqa: E402


@pytest.fixture(scope="module")
def scr():
    os.environ.setdefault("PILOT_SPEC", str(ROOT / "experiment" / "bizsla" / "SPEC.md"))
    return common.load("problems_screen_under_test", PROB / "screen.py")


def cases_mod(p):
    return common.load(f"t_{p}_cases", PROB / p / "cases.py")


# ── Oracle cross-checks ──────────────────────────────────────────────────────
@pytest.mark.parametrize("p", PROBLEMS)
def test_every_public_example_has_a_hand_derived_expected_output(p):
    pub = cases_mod(p).public()
    assert len(pub) >= 4
    assert all("spec_expected" in c for c in pub), "a public example would be graded by the reference alone"


@pytest.mark.parametrize("p", PROBLEMS)
def test_hand_derived_hidden_cases_exist(p):
    hid = cases_mod(p).hidden()
    assert sum("spec_expected" in c for c in hid) >= 18
    assert len(hid) >= 100


@pytest.mark.parametrize("p", PROBLEMS)
def test_reference_agrees_with_every_hand_derived_output(p):
    cfg = common.config(p)
    ref = common.load(f"t_{p}_ref", PROB / p / "reference.py")
    fn = getattr(ref, cfg["entry"])
    cm = cases_mod(p)
    checked = 0
    for c in cm.public() + cm.hidden():
        if "spec_expected" in c:
            got = fn(*copy.deepcopy(c["args"]))
            assert common.canon(got) == common.canon(c["spec_expected"]), \
                f"{c['id']}: {common.first_difference(c['spec_expected'], got)}"
            checked += 1
    assert checked >= 22


@pytest.mark.parametrize("p", PROBLEMS)
def test_stored_cases_equal_a_fresh_build_and_build_is_deterministic(p):
    stored = json.loads((PROB / p / "screen_cases.json").read_text(encoding="utf-8"))
    a, b = common.build(p, write=False), common.build(p, write=False)
    assert a == b
    assert stored == a, "screen_cases.json is stale or was edited by hand"
    ids = [c["id"] for layer in ("public", "hidden", "stress") for c in a[layer]]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("p", PROBLEMS)
def test_spec_names_the_entry_point_and_never_mentions_the_grader(p):
    spec = (PROB / p / "SPEC.md").read_text(encoding="utf-8")
    entry = common.config(p)["entry"]
    assert f"def {entry}(" in spec
    for leak in ("reference.py", "mutants.py", "screen_cases", "hidden case", "spec_expected"):
        assert leak not in spec


@pytest.mark.parametrize("p", PROBLEMS)
def test_problem_code_is_stdlib_only(p):
    allowed = set(sys.stdlib_module_names)
    for f in ("reference.py", "cases.py", "oracle2.py"):
        if f == "oracle2.py" and not (PROB / p / f).exists():     # only problems past screening have one
            continue
        tree = ast.parse((PROB / p / f).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                    [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
            for n in names:
                assert n.split(".")[0] in allowed, f"{p}/{f} imports {n}"


# ── Strict comparison ────────────────────────────────────────────────────────
@pytest.mark.parametrize("a,b", [(1, 1.0), (True, 1), (False, 0), ([1], [1.0]), ({"a": 1}, {"a": True}),
                                 ("1", 1), (None, "null"), ([], {})])
def test_canon_distinguishes_values_python_calls_equal(a, b):
    assert common.canon(a) != common.canon(b)


def test_canon_ignores_dict_key_order_only():
    assert common.canon({"a": 1, "b": [1, 2]}) == common.canon({"b": [1, 2], "a": 1})
    assert common.canon([1, 2]) != common.canon([2, 1])


@pytest.mark.parametrize("bad", [(1, 2), {1: "x"}, {"a": (1,)}, float("nan"), float("inf"), {1, 2}, b"x",
                                 [iter([1])]])
def test_canon_rejects_non_json_types(bad):
    with pytest.raises(TypeError):
        common.canon(bad)


def test_first_difference_reports_type_and_path():
    d = common.first_difference({"x": [1, 2]}, {"x": [1, 2.0]})
    assert "result.x[1]" in d and "int" in d and "float" in d
    assert common.first_difference([1], [1, 2]) == "result: length 2 != expected 1"


# ── Planted bugs (trusted code, run in-process) ──────────────────────────────
@pytest.mark.parametrize("p", PROBLEMS)
def test_every_planted_bug_applies_once_and_changes_the_code(p):
    src = (PROB / p / "reference.py").read_text(encoding="utf-8")
    mutants = common.load(f"t_{p}_mut", PROB / p / "mutants.py").MUTANTS
    assert len(mutants) >= 14
    seen = set()
    for m in mutants:
        out = common.planted(p, m)
        assert out != src, m
        compile(out, m, "exec")
        assert out not in seen, f"{m} duplicates another planted bug"
        seen.add(out)


def test_planted_refuses_ambiguous_target(tmp_path, monkeypatch):
    d = tmp_path / "toy"
    d.mkdir()
    (d / "problem.json").write_text('{"entry": "f"}', encoding="utf-8")
    (d / "reference.py").write_text("def f():\n    return 1 + 1\n", encoding="utf-8")
    (d / "mutants.py").write_text('MUTANTS = {"twice": [("1", "2")], "absent": [("zzz", "y")]}', encoding="utf-8")
    monkeypatch.setattr(common, "HERE", tmp_path)
    for m in ("twice", "absent"):
        with pytest.raises(SystemExit, match="exactly 1"):
            common.planted("toy", m)


def _killers(p, fn, built, stress_inputs):
    killers = []
    for c in built["hidden"]:
        try:
            bad = common.canon(fn(*copy.deepcopy(c["args"]))) != common.canon(c["expected"])
        except Exception:  # noqa: BLE001  (a crash is a catch)
            bad = True
        if bad:
            killers.append(c["id"])
    if not killers:
        for c in built["stress"]:
            try:
                text = common.canon(fn(*copy.deepcopy(stress_inputs[c["id"]])))
                bad = hashlib.sha256(text.encode("utf-8")).hexdigest() != c["expected_sha256"]
            except Exception:  # noqa: BLE001
                bad = True
            if bad:
                killers.append(c["id"])
    return killers


@pytest.mark.parametrize("p", PROBLEMS)
def test_every_planted_bug_is_caught_by_a_scored_case(p):
    """In-process mirror of the Docker self-test. Public examples do not count: a bug caught only there would mean
    the scored layers are blind to it."""
    built = common.build(p, write=False)
    gen = cases_mod(p)
    stress_inputs = {c["id"]: gen.stress_args(c) for c in built["stress"]}
    entry = built["entry"]
    missed = []
    for m in common.load(f"t_{p}_mut2", PROB / p / "mutants.py").MUTANTS:
        mod = types.ModuleType(f"mut_{p}")
        exec(compile(common.planted(p, m), m, "exec"), mod.__dict__)
        if not _killers(p, getattr(mod, entry), built, stress_inputs):
            missed.append(m)
    assert not missed, f"planted bugs no scored case catches: {missed}"


# ── Screening harness ────────────────────────────────────────────────────────
def test_screen_plan_interleaves_and_counts(scr):
    order = scr.plan(["x", "y"], 3, 1)
    assert len(order) == 8
    assert order[:4] == [("x", "A1"), ("x", "C1"), ("y", "A1"), ("y", "C1")]
    assert sorted(n for p, n in order if p == "y") == ["A1", "A2", "A3", "C1"]


def test_screen_keep_rule_is_the_documented_one(scr):
    assert scr.KEEP_RULE == {"a_max_pass_rate": 0.25, "c_min_passes": 1}
    doc = (PROB / "screen.py").read_text(encoding="utf-8")
    assert "A strict passes <= 25% of valid A runs" in doc and "C strict passes >= 1" in doc
    k = lambda a, av, c, cv: scr.keep_verdict({"strict_passes": a, "valid": av},  # noqa: E731
                                              {"strict_passes": c, "valid": cv})["keep_candidate"]
    assert k(1, 4, 1, 2) is True
    assert k(0, 4, 2, 2) is True
    assert k(2, 4, 2, 2) is False          # 50% > 25%: too easy
    assert k(0, 4, 0, 2) is False          # nobody solves it: unsolvable or broken spec/oracle
    assert k(0, 0, 1, 2) is False          # undefined


def test_screen_summarize_excludes_harness_errors(scr):
    rows = [{"problem": "x", "arm": "A", "harness_error": False, "strict_pass": True, "cases_passed": 10,
             "cases_total": 10, "cost_usd": 0.1},
            {"problem": "x", "arm": "A", "harness_error": True, "strict_pass": False, "cases_passed": 0,
             "cases_total": None, "cost_usd": None},
            {"problem": "x", "arm": "C", "harness_error": False, "strict_pass": False, "cases_passed": 5,
             "cases_total": 10, "cost_usd": 0.3}]
    s = scr.summarize(["x"], rows)["x"]
    assert s["arms"]["A"] == {"runs": 2, "valid": 1, "harness_errors": 1, "strict_passes": 1,
                              "mean_case_fraction": 1.0, "cost_usd": 0.1}
    assert s["arms"]["C"]["mean_case_fraction"] == 0.5
    assert s["keep_candidate"] is False     # A 1/1 = 100%


def test_screen_detects_stale_cases(scr, monkeypatch):
    real = scr.common.build
    monkeypatch.setattr(scr.common, "build", lambda p, write=True: {**real(p, write=False), "hidden": []})
    assert scr.stale_problems(["promo"]) == ["promo"]
    monkeypatch.setattr(scr.common, "build", real)
    assert scr.stale_problems(["promo"]) == []


def _screen(*args, timeout=120):
    return subprocess.run([sys.executable, str(PROB / "screen.py"), *args], cwd=ROOT, capture_output=True,
                          text=True, timeout=timeout)


def test_screen_refuses_without_cap():
    r = _screen("--plan-only", "--problems", "promo")
    assert r.returncode != 0 and "--cap-usd is required" in r.stderr + r.stdout


def test_screen_refuses_mock_with_live_roles():
    r = _screen("--mock", "--roles", str(ROOT / "experiment" / "study" / "roles_study.json"), "--cap-usd", "1",
                "--plan-only", "--problems", "promo")
    assert r.returncode != 0 and "--mock with a non-mock roles file" in r.stderr + r.stdout


def test_screen_refuses_unsafe_sandbox_for_live_output():
    r = _screen("--unsafe-subprocess-sandbox", "--cap-usd", "1", "--plan-only", "--problems", "promo")
    assert r.returncode != 0 and "only ever executed in the Docker sandbox" in r.stderr + r.stdout


def test_screen_plan_only_prices_every_run_and_calls_nothing(tmp_path):
    r = _screen("--plan-only", "--cap-usd", "10", "--out-root", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "8 problems x (4 A + 2 C) = 48 runs" in r.stdout      # default: the unscreened problems only
    assert not any(tmp_path.iterdir()), "plan-only must not create run folders"


# ── Slow: real sandbox ───────────────────────────────────────────────────────
def _docker_or_skip():
    from crucible.sandbox import docker_available
    ok, why = docker_available()
    if not ok and os.environ.get("CRUCIBLE_SANDBOX") != "subprocess-unsafe":
        pytest.skip(f"Docker unavailable: {why}")


@pytest.mark.slow
@pytest.mark.parametrize("p", PROBLEMS)
def test_self_test_in_sandbox(p):
    """The reference passes every case in the sandbox and every planted bug is caught by a scored case there."""
    _docker_or_skip()
    assert common.self_test(p)


@pytest.mark.slow
def test_mock_screening_end_to_end_grades_against_ground_truth(tmp_path):
    """Real screen.py, real arm_study.py subprocesses, real grader, on the zero-cost mock provider. The mock roles
    serve either the promo reference or a planted-bug copy; a run must pass exactly when its solution.py is
    byte-identical to the reference. The cap equals the exact all-runs worst case, so every run is admitted (the
    refusal path of the shared Budget is covered in tests/test_study.py)."""
    _docker_or_skip()
    ref = PROB / "promo" / "reference.py"
    bug = tmp_path / "planted_promo_M01.py"
    bug.write_text(common.planted("promo", next(iter(common.load("t_promo_m3", PROB / "promo" /
                                                                  "mutants.py").MUTANTS))), encoding="utf-8")
    roles = json.loads((ROOT / "experiment" / "study" / "roles_mock.json").read_text(encoding="utf-8"))
    for r in roles.values():
        r["settings"]["solution_files"] = [str(ref), str(bug)]
    roles_file = tmp_path / "roles_mock_promo.json"
    roles_file.write_text(json.dumps(roles), encoding="utf-8")
    from importlib import import_module
    sys.path.insert(0, str(ROOT / "experiment" / "study"))
    rs = import_module("run_study")
    wa, wc = rs.worst_case_run("A", roles), rs.worst_case_run("C", roles)
    cap = round(3 * wa + 2 * wc, 4)
    unsafe = os.environ.get("CRUCIBLE_SANDBOX") == "subprocess-unsafe"
    args = ["--mock", "--roles", str(roles_file), "--problems", "promo", "--a-runs", "3", "--c-runs", "2",
            "--cap-usd", str(cap), "--out-root", str(tmp_path / "out")] + (["--unsafe-subprocess-sandbox"]
                                                                          if unsafe else [])
    r = _screen(*args, timeout=3600)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    run_dir = next((tmp_path / "out").glob("screen_mock_*"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["config"]["mock"] is True and "MOCK DRY RUN" in (run_dir / "SCREENING.md").read_text("utf-8")
    assert summary["not_run"] == []
    assert summary["spent_usd"] <= cap
    spec = (PROB / "promo" / "SPEC.md").read_text(encoding="utf-8")
    system = ast.literal_eval(next(n.value for n in ast.parse((ROOT / "experiment" / "arms.py").read_text(
        encoding="utf-8")).body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "SYSTEM"))
    reference = ref.read_text(encoding="utf-8").strip()
    assert len(summary["runs"]) == 5
    outcomes = set()
    for row in summary["runs"]:
        assert not row["harness_error"], row
        assert row["input_tokens"] == len(system + spec) // 4, "the model was not sent exactly the promo SPEC.md"
        sol = run_dir / "promo" / row["run"] / "solution.py"
        is_ref = sol.read_text(encoding="utf-8").strip() == reference
        assert row["strict_pass"] is is_ref, row
        assert row["cases_total"] == len(common.load_cases("promo")["hidden"]) + len(
            common.load_cases("promo")["stress"])
        outcomes.add(is_ref)
    assert outcomes == {True, False}, "the mock served only one kind of solution; the check proves nothing"
    p = summary["problems"]["promo"]
    for arm in "AC":
        arm_rows = [x for x in summary["runs"] if x["arm"] == arm]
        assert p["arms"][arm]["strict_passes"] == sum(x["strict_pass"] for x in arm_rows)
