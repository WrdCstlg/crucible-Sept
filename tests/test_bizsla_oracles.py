"""Is the hidden ground truth for Problem 5 (experiment/bizsla) trustworthy?

Three independent sources must agree, so a shared misreading of the spec has to slip past all of them:
  * hand_cases.json: expected values worked out by hand from the spec text (with the reasoning recorded);
  * brute_force.py: a minute-by-minute simulation that mirrors the spec sentence by sentence;
  * reference.py: closed-form calendar arithmetic (the only one fast enough for the stress layer).
Plus spec-derived metamorphic properties, calendar property tests, and a check that the hidden cases catch every
planted bug. These run in-process: every piece of code here is ours, not model output.
"""
import json
import random
import sys
from pathlib import Path

import pytest

BIZ = Path(__file__).resolve().parent.parent / "experiment" / "bizsla"
sys.path.insert(0, str(BIZ))
import brute_force  # noqa: E402
import generate_cases as gen  # noqa: E402
import reference  # noqa: E402
import importlib.util  # noqa: E402

# Loaded by path under a unique name: experiment/grade.py (the pilots' grader) is also a module called `grade`.
_spec = importlib.util.spec_from_file_location("bizsla_grade", BIZ / "grade.py")
_bizgrade = sys.modules.setdefault("bizsla_grade", importlib.util.module_from_spec(_spec))
if not hasattr(_bizgrade, "MUTANTS"):
    _spec.loader.exec_module(_bizgrade)
MUTANTS, check, planted = _bizgrade.MUTANTS, _bizgrade.check, _bizgrade.planted
assert all(k.startswith("B") for k in MUTANTS), "loaded the wrong grader"
for _m in (brute_force, reference, gen):           # same guard for the other bare names shared with experiment/sla
    assert Path(_m.__file__).resolve().parent == BIZ.resolve(), f"{_m.__name__} resolved outside experiment/bizsla"

HAND = json.loads((BIZ / "hand_cases.json").read_text(encoding="utf-8"))
GENERATED = json.loads((BIZ / "generated_cases.json").read_text(encoding="utf-8"))
PUBLIC = json.loads((BIZ / "public_cases.json").read_text(encoding="utf-8"))
STRESS = json.loads((BIZ / "stress_cases.json").read_text(encoding="utf-8"))
ORACLES = {"reference": reference.compute_sla, "brute_force": brute_force.compute_sla}


def row(tid, prio, used, breached_at, status):
    return {"ticket_id": tid, "priority": prio, "used_minutes": used, "breached": breached_at is not None,
            "breached_at": breached_at, "status": status}


# ── Ground truth agreement ──────────────────────────────────────────────
def test_public_cases_are_exactly_the_spec_examples():
    spec = (BIZ / "SPEC.md").read_text(encoding="utf-8")
    expected = [[row("A", "P2", 60, None, "closed")], [row("B", "P1", 120, None, "paused")],
                [row("C", "P1", 360, 781, "closed")], [row("D", "P3", 60, None, "paused")]]
    assert [c["expected"] for c in PUBLIC] == expected
    for c in PUBLIC:
        assert "\n".join(c["lines"]) in spec, f"{c['id']} lines are not the SPEC example"


@pytest.mark.parametrize("name", ORACLES)
@pytest.mark.parametrize("case", HAND, ids=[c["id"] for c in HAND])
def test_both_oracles_match_every_hand_derived_case(name, case):
    assert ORACLES[name](list(case["lines"])) == case["expected"], case["why"]


def test_hand_cases_document_their_reasoning():
    assert len(HAND) >= 20 and all(c["why"].strip() for c in HAND)


def _fuzz_stream(rng):
    return gen.random_stream(rng, span=rng.choice([600, 3000, 12000, 25000]), n=rng.randint(1, 22),
                             ids=rng.sample(["A", "B", "C", "t1"], rng.randint(1, 3)), holidays=(0, 4),
                             prio_bias=rng.choice([0, 3]))


def test_differential_fuzz_brute_force_equals_reference():
    rng = random.Random(4242)
    breaches = 0
    for i in range(2500):
        s = _fuzz_stream(rng)
        a, b = brute_force.compute_sla(s), reference.compute_sla(s)
        assert a == b, f"stream #{i}: {s}"
        breaches += sum(r["breached"] for r in a)
    assert breaches > 300, "the fuzzer must exercise breaches, not only quiet tickets"


def test_generated_expectations_still_match_both_oracles():
    for c in GENERATED + PUBLIC:
        assert reference.compute_sla(list(c["lines"])) == c["expected"], c["id"]
    for c in [c for c in GENERATED if c["layer"] != "medium"][::3]:
        assert brute_force.compute_sla(list(c["lines"])) == c["expected"], c["id"]


def test_layers_have_the_documented_sizes():
    layers = {}
    for c in GENERATED:
        layers[c["layer"]] = layers.get(c["layer"], 0) + 1
    assert layers == {"edge": 35, "random": 80, "holiday": 40, "churn": 40, "medium": 6}
    assert [s["id"] for s in STRESS] == ["S01", "S02", "S03", "S04"]


# ── Calendar arithmetic (the part brute force cannot check at scale) ────
def _brute_count(a, b, hol):
    return sum(1 for x in range(a, b) if brute_force.is_business(x, hol))


def test_calendar_count_matches_minute_by_minute_counting():
    rng = random.Random(7)
    for _ in range(400):
        hol = {rng.randint(0, 60) for _ in range(rng.randint(0, 8))}
        cal = reference.Calendar(hol)
        a = rng.randint(0, 50_000)
        b = a + rng.randint(0, 25_000)
        assert cal.count(a, b) == _brute_count(a, b, hol), (a, b, sorted(hol))


def test_calendar_is_additive_and_weekly_periodic_at_huge_minutes():
    rng = random.Random(8)
    cal = reference.Calendar([])
    for _ in range(300):
        a, b, c = sorted(rng.randint(0, 10 ** 12) for _ in range(3))
        assert cal.count(a, c) == cal.count(a, b) + cal.count(b, c)
        k = rng.randint(1, 10 ** 6)
        assert cal.count(a + 10080 * k, b + 10080 * k) == cal.count(a, b)
    assert cal.count(0, 10080) == 2400 and cal.count(10 ** 9 - 10 ** 9 % 10080, 10 ** 9 - 10 ** 9 % 10080 + 10080) == 2400


def test_each_weekday_holiday_removes_exactly_one_working_day():
    for d in range(14):
        cal = reference.Calendar([d])
        assert cal.count(0, 20160) == 4800 - (480 if d % 7 < 5 else 0), d


def test_first_reaching_returns_the_minimal_minute():
    rng = random.Random(9)
    for _ in range(300):
        hol = {rng.randint(0, 40) for _ in range(rng.randint(0, 6))}
        cal = reference.Calendar(hol)
        a, need = rng.randint(0, 30_000), rng.randint(1, 3000)
        t = cal.first_reaching(a, need)
        assert cal.count(a, t) >= need > cal.count(a, t - 1)


# ── Metamorphic properties, each cited from SPEC.md ─────────────────────
def _shift(lines, k):
    out = []
    for l in lines:
        p = reference.parse(l)
        if p is None:
            continue
        m, tid, ev, arg = p
        out.append(",".join([str(m + k), tid, ev] + ([arg] if arg else [])))
    return out


def _cases(n=300, seed=11):
    rng = random.Random(seed)
    return [_fuzz_stream(rng) for _ in range(n)]


@pytest.mark.parametrize("name", ORACLES)
def test_shifting_everything_by_whole_weeks_shifts_only_breached_at(name):
    """Calendar: business minutes depend on weekday and minute-of-day only, so a whole-week shift is invisible."""
    f = ORACLES[name]
    for s in _cases(150):
        base, moved = f(s), f(_shift(s, 10080 * 3))
        assert len(base) == len(moved)
        for x, y in zip(base, moved):
            assert {**x, "breached_at": None} == {**y, "breached_at": None}
            assert (x["breached_at"] is None) == (y["breached_at"] is None)
            if x["breached_at"] is not None:
                assert y["breached_at"] == x["breached_at"] + 10080 * 3


@pytest.mark.parametrize("name", ORACLES)
def test_arrival_order_is_irrelevant_except_for_ties(name):
    """Ordering: process by minute; equal minutes keep stream order. Any permutation that keeps every group of
    equal-minute events in its original relative order must give the same output."""
    f, rng = ORACLES[name], random.Random(12)
    for s in _cases(150):
        good = [l for l in s if reference.parse(l) is not None]
        shuffled = good[:]
        rng.shuffle(shuffled)
        groups: dict = {}
        for l in good:                                    # original relative order per minute
            groups.setdefault(reference.parse(l)[0], []).append(l)
        cursor = {m: iter(g) for m, g in groups.items()}
        permuted = [next(cursor[reference.parse(l)[0]]) for l in shuffled]
        assert sorted(permuted) == sorted(good)
        assert f(permuted) == f(good)


@pytest.mark.parametrize("name", ORACLES)
def test_malformed_lines_change_nothing(name):
    """Input: any malformed line is ignored completely, including for 'now'."""
    f, rng = ORACLES[name], random.Random(13)
    junk = ["", "garbage", "99999,A,pause", "99999,A,PAUSE,P1", "99999,A,OPEN", "99999,A,OPEN,P5", "9.5,A,CLOSE",
            "99999,*,CLOSE", "99999,B,HOLIDAY", "99999,,OPEN,P1", "-5,A,OPEN,P1", "99999,A,OPEN,p1", "1,2,3,4,5"]
    for s in _cases(150):
        noisy = s[:]
        for j in rng.sample(junk, 5):
            noisy.insert(rng.randint(0, len(noisy)), j)
        assert f(noisy) == f(s)


@pytest.mark.parametrize("name", ORACLES)
def test_tickets_are_independent_given_now(name):
    """Each ticket's row depends only on its own events, the calendar and now."""
    f = ORACLES[name]
    for s in _cases(100):
        full = f(s)
        good = [reference.parse(l) for l in s]
        good = [p for p in good if p is not None]
        events = [p for p in good if p[2] != "HOLIDAY"]
        if not events:
            continue
        now = max(p[0] for p in events)
        hol = [l for l in s if (reference.parse(l) or (0, "", ""))[2] == "HOLIDAY"]
        for r in full:
            own = [l for l in s if (reference.parse(l) or (0, None))[1] == r["ticket_id"]]
            alone = f(own + hol + [f"{now},~pin,PAUSE"])  # ignored event on a never-opened ticket pins now
            assert alone == [r]


@pytest.mark.parametrize("name", ORACLES)
def test_weekend_holidays_and_duplicate_holidays_change_nothing(name):
    f = ORACLES[name]
    for s in _cases(100):
        extra = [f"{w * 10080 + 5 * 1440 + 7},*,HOLIDAY" for w in range(4)]
        dup = [l for l in s if l.endswith(",*,HOLIDAY")]
        assert f(s + extra + dup) == f(s)


@pytest.mark.parametrize("name", ORACLES)
def test_breach_flag_and_time_are_consistent(name):
    """Output contract: breached iff breached_at is set; breached_at <= now; used never negative."""
    f = ORACLES[name]
    for s in _cases(200):
        res = f(s)
        events = [reference.parse(l) for l in s]
        events = [p for p in events if p and p[2] != "HOLIDAY"]
        now = max((p[0] for p in events), default=None)
        assert [r["ticket_id"] for r in res] == sorted(r["ticket_id"] for r in res)
        for r in res:
            assert r["breached"] == (r["breached_at"] is not None)
            assert r["used_minutes"] >= 0
            if r["breached_at"] is not None:
                assert r["breached_at"] <= now


# ── The hidden cases catch every planted bug ────────────────────────────
def _load(src):
    ns: dict = {}
    exec(compile(src, "<planted>", "exec"), ns)  # our own planted fixture, not model output
    return ns["compute_sla"]


@pytest.mark.parametrize("name", [n for n in MUTANTS if not n.startswith("B21")])
def test_every_planted_bug_fails_some_hidden_case(name):
    f = _load(planted(name))
    hidden = HAND + GENERATED
    killers = []
    for c in hidden:
        try:
            got = f(list(c["lines"]))
            bad = type(got) is not list or check(c["expected"], got) is not None
        except Exception:
            bad = True
        if bad:
            killers.append(c["id"])
    assert len(killers) >= 2, f"{name} is caught by {killers or 'no hidden case'}; need at least two"


def test_the_slow_planted_bug_is_correct_on_small_cases_so_only_stress_catches_it():
    f = _load(planted("B21 counts minute by minute (too slow)"))
    for c in HAND + PUBLIC:
        assert f(list(c["lines"])) == c["expected"], c["id"]


# ── Stress layer and freeze ─────────────────────────────────────────────
def test_stress_generator_is_version_independent():
    r = gen.SplitMix(1)
    assert [r.next() for _ in range(3)] == [10451216379200822465, 13757245211066428519, 17911839290282890590]
    s = STRESS[1]
    assert gen.stress_lines(s) == gen.stress_lines(s)


def test_reference_meets_the_performance_requirement_on_the_largest_stress_case():
    import time
    s = STRESS[0]
    lines = gen.stress_lines(s)
    assert len(lines) == 220_000
    t0 = time.perf_counter()
    out = reference.compute_sla(lines)
    assert time.perf_counter() - t0 < 10
    assert gen.canonical_digest(out) == s["expected_sha256"]


def test_frozen_files_match_the_manifest():
    assert gen.check()
