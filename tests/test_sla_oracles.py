"""
Ground truth that does not depend on any AI: three independent SLA oracles must agree, and spec-derived
metamorphic properties must hold.

  reference.py            global stable sort + per-ticket state machine        (frozen, experiment/sla)
  reference_intervals.py  own parser, per-ticket grouping, summed intervals    (frozen, experiment/sla)
  brute_force (below)     millisecond-by-millisecond simulation: at every tick, apply that tick's events and
                          add 1 ms if the ticket is RUNNING. Slow, but each line maps directly onto a spec sentence.

Differential fuzzing: thousands of seeded random streams (out-of-order arrivals, equal timestamps, malformed
lines, Unicode digits, whitespace, case-sensitive IDs, every transition in the spec's table). Any disagreement
means at least one oracle misreads the spec, and the hidden test set's expected values could be wrong.

Metamorphic properties come straight from SPEC.md sentences, so they hold for any correct implementation and
need no expected values at all.
"""
import importlib.util
import json
import random
from pathlib import Path

import pytest

SLA = Path(__file__).resolve().parent.parent / "experiment" / "sla"
LIMIT = 14_400_000
EVENTS = ("OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN")
TICKETS = ("A", "B", "a", "T1", "T2", "T10")


def _load(name):
    spec = importlib.util.spec_from_file_location(f"sla_{name}", SLA / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.compute_sla


REF = _load("reference")
INTERVALS = _load("reference_intervals")


def _pilot_grader_mutants() -> dict:
    """MUTANTS from experiment/grade.py, loaded by path: experiment/bizsla/grade.py has the same module name, and a
    bare `from grade import MUTANTS` would silently pick whichever was imported first in this process."""
    spec = importlib.util.spec_from_file_location("sla_pilot_grade", SLA.parent / "grade.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert all(not k.startswith("B0") for k in mod.MUTANTS), "loaded the wrong grader"
    return mod.MUTANTS


# ── Oracle 3: brute force ────────────────────────────────────────────────
def _parse(line):
    """SPEC 'Input': trim, exactly 3 comma fields, trim each; ASCII digits; non-empty id; exact uppercase event."""
    if not isinstance(line, str):
        return None
    fields = line.strip().split(",")
    if len(fields) != 3:
        return None
    ts, tid, ev = (f.strip() for f in fields)
    if not ts or any(c not in "0123456789" for c in ts) or not tid or ev not in EVENTS:
        return None
    return int(ts), tid, ev


def brute_force(stream, limit=LIMIT):
    events = [(p[0], i, p[1], p[2]) for i, p in enumerate(map(_parse, stream)) if p]
    if not events:
        return []
    now = max(e[0] for e in events)                               # SPEC "Now"
    events.sort(key=lambda e: (e[0], e[1]))                       # SPEC "Ordering" (stable)
    state, used = {}, {}
    by_tick = {}
    for ts, _, tid, ev in events:
        by_tick.setdefault(ts, []).append((tid, ev))

    def apply(tid, ev):                                           # SPEC transition table, row by row
        s = state.get(tid, "NOT_OPENED")
        if ev == "OPEN" and s in ("NOT_OPENED", "CLOSED"):
            state[tid], used[tid] = "RUNNING", 0
        elif ev == "PAUSE" and s == "RUNNING":
            state[tid] = "PAUSED"
        elif ev == "RESUME" and s == "PAUSED":
            state[tid] = "RUNNING"
        elif ev == "CLOSE" and s in ("RUNNING", "PAUSED"):
            state[tid] = "CLOSED"
        elif ev == "REOPEN" and s == "CLOSED":
            state[tid] = "RUNNING"

    for t in range(events[0][0], now):                            # each millisecond [t, t+1)
        for tid, ev in by_tick.get(t, ()):
            apply(tid, ev)
        for tid, s in state.items():
            if s == "RUNNING":
                used[tid] += 1
    for tid, ev in by_tick.get(now, ()):                          # events at "now" add no time
        apply(tid, ev)
    return [{"ticket_id": tid, "used_ms": used[tid], "breached": used[tid] > limit,
             "status": "closed" if state[tid] == "CLOSED" else "open"} for tid in sorted(state)]


# ── Random streams ───────────────────────────────────────────────────────
MALFORMED = ("", "   ", "5,A,open", "5.0,A,OPEN", "-5,A,OPEN", "5,,OPEN", "5,A,OPEN,x", "5,A", "\u0663,A,OPEN",
             "5,A,OPENED", "x,A,OPEN", "5;A;OPEN", "1e3,A,OPEN")


def random_stream(rng, n_max=30, t_max=300):
    lines = []
    for _ in range(rng.randint(0, n_max)):
        r = rng.random()
        if r < 0.12:
            lines.append(rng.choice(MALFORMED))
        else:
            ts = str(rng.randint(0, t_max))
            if rng.random() < 0.1:
                ts = "0" + ts                                     # leading zeros are allowed
            line = f"{ts},{rng.choice(TICKETS)},{rng.choice(EVENTS)}"
            if rng.random() < 0.1:
                line = " " + line.replace(",", " , ") + "  "      # surrounding/field whitespace is trimmed
            lines.append(line)
    return lines


def _cases(seed, n):
    rng = random.Random(seed)
    return [random_stream(rng) for _ in range(n)]


# ── Differential fuzzing ─────────────────────────────────────────────────
@pytest.mark.parametrize("seed", range(6))
def test_three_independent_oracles_agree_on_random_streams(seed):
    for stream in _cases(seed, 500):
        expected = brute_force(stream)
        assert REF(list(stream)) == expected, stream
        assert INTERVALS(list(stream)) == expected, stream


def test_oracles_agree_on_every_frozen_hidden_case():
    for f in ("hand_cases.json", "generated_cases.json"):
        for case in json.loads((SLA / f).read_text(encoding="utf-8")):
            assert REF(list(case["lines"])) == case["expected"], case["id"]
            assert INTERVALS(list(case["lines"])) == case["expected"], case["id"]
            if case.get("layer") != "stress" and all(_parse(l) is None or _parse(l)[0] < 50_000 for l in case["lines"]):
                assert brute_force(case["lines"]) == case["expected"], case["id"]


def test_fuzzer_actually_exercises_the_spec():
    """Coverage of the fuzz corpus itself: a fuzzer that never hits a transition proves nothing about it."""
    seen = set()
    for stream in _cases(0, 500):
        res = brute_force(stream)
        seen |= {"closed" if r["status"] == "closed" else "open" for r in res}
        seen |= {"malformed" for l in stream if _parse(l) is None}
        seen |= {"tie" for i, l in enumerate(stream) for m in stream[i + 1:] if _parse(l) and _parse(m)
                 and _parse(l)[0] == _parse(m)[0]}
        seen |= {"empty_output"} if stream and not res else set()
    assert {"open", "closed", "malformed", "tie", "empty_output"} <= seen, seen


# ── Metamorphic properties (each cites the spec sentence it comes from) ──
def _structured(rng, n=25, distinct=False):
    ts = rng.sample(range(0, 10_000), n) if distinct else [rng.randint(0, 10_000) for _ in range(n)]
    return [(t, rng.choice(TICKETS), rng.choice(EVENTS)) for t in ts]


def _lines(events):
    return [f"{t},{tid},{ev}" for t, tid, ev in events]


@pytest.mark.parametrize("impl", [REF, INTERVALS], ids=["reference", "intervals"])
class TestMetamorphic:
    def test_time_shift_invariance(self, impl):
        """Used time is measured between timestamps and to 'now' (the max timestamp): shifting all of them by
        the same amount changes nothing."""
        rng = random.Random(1)
        for _ in range(300):
            ev = _structured(rng)
            c = rng.randint(1, 10**9)
            assert impl(_lines(ev)) == impl(_lines([(t + c, i, e) for t, i, e in ev]))

    def test_time_scaling_scales_used_time(self, impl):
        """Used time is a sum of timestamp differences: scaling every timestamp by k scales used_ms by k."""
        rng = random.Random(2)
        for _ in range(300):
            ev = _structured(rng)
            k = rng.randint(2, 5000)
            base, scaled = impl(_lines(ev)), impl(_lines([(t * k, i, e) for t, i, e in ev]))
            assert [(r["ticket_id"], r["used_ms"] * k, r["status"]) for r in base] == \
                   [(r["ticket_id"], r["used_ms"], r["status"]) for r in scaled]
            assert all(r["breached"] == (r["used_ms"] > LIMIT) for r in scaled)

    def test_malformed_lines_have_no_effect(self, impl):
        """'Any other line ... is malformed and is ignored completely: it has no effect on anything.'"""
        rng = random.Random(3)
        for _ in range(300):
            lines = _lines(_structured(rng))
            noisy = list(lines)
            for _ in range(rng.randint(1, 8)):
                noisy.insert(rng.randint(0, len(noisy)), rng.choice(MALFORMED))
            assert impl(lines) == impl(noisy)

    def test_arrival_order_does_not_matter_for_distinct_timestamps(self, impl):
        """'Events may arrive out of order. Process the well-formed events in order of timestamp.'"""
        rng = random.Random(4)
        for _ in range(300):
            lines = _lines(_structured(rng, distinct=True))
            shuffled = list(lines)
            rng.shuffle(shuffled)
            assert impl(lines) == impl(shuffled)

    def test_tickets_are_independent_given_now(self, impl):
        """Each ticket's clock depends only on its own events and on 'now'. Keep one ticket's lines plus an
        ignored event at 'now' for a never-opened ticket: that ticket's row is unchanged, the other is omitted."""
        rng = random.Random(5)
        for _ in range(300):
            ev = _structured(rng)
            now = max(t for t, _, _ in ev)
            full = {r["ticket_id"]: r for r in impl(_lines(ev))}
            for tid in full:
                alone = impl(_lines([e for e in ev if e[1] == tid]) + [f"{now},__never_opened__,PAUSE"])
                assert alone == [full[tid]]

    def test_breach_is_strictly_greater_than_the_limit(self, impl):
        """'Exactly 14,400,000 ms does not breach.'"""
        assert impl(["0,A,OPEN", f"{LIMIT},A,CLOSE"])[0]["breached"] is False
        assert impl(["0,A,OPEN", f"{LIMIT + 1},A,CLOSE"])[0]["breached"] is True
        assert impl(["0,A,OPEN", f"{LIMIT + 1},B,PAUSE"])[0]["breached"] is True  # open tickets too

    def test_output_contract(self, impl):
        """List of dicts, exactly four keys with exact types, sorted by code-point ticket_id."""
        rng = random.Random(6)
        for _ in range(200):
            out = impl(_lines(_structured(rng)))
            assert type(out) is list
            assert [r["ticket_id"] for r in out] == sorted(r["ticket_id"] for r in out)
            for r in out:
                assert set(r) == {"ticket_id", "used_ms", "breached", "status"}
                assert type(r["used_ms"]) is int and type(r["breached"]) is bool and r["status"] in ("open", "closed")

    # Transition-table properties. After `T,X,CLOSE` the ticket is CLOSED (or was never opened); after `T,X,PAUSE`
    # it is PAUSED, CLOSED or never opened. Either way it is not RUNNING, so a later 'now' must not move it.
    GHOST = "__never_opened__"

    @staticmethod
    def _row(impl, lines, tid):
        return next((r for r in impl(lines) if r["ticket_id"] == tid), None)

    def test_paused_or_closed_ticket_does_not_depend_on_now(self, impl):
        """'Time spent PAUSED or CLOSED never counts.' / 'A ticket still PAUSED counts only up to its pause.'"""
        rng = random.Random(7)
        for _ in range(150):
            ev = _lines(_structured(rng))
            t = 10_001
            for tid in TICKETS:
                for last in ("PAUSE", "CLOSE"):
                    base = ev + [f"{t},{tid},{last}"]
                    later = base + [f"{t + rng.randint(1, 10**6)},{self.GHOST},PAUSE"]
                    assert self._row(impl, base, tid) == self._row(impl, later, tid)

    def test_closed_ticket_ignores_pause_resume_and_close(self, impl):
        """Table column CLOSED: PAUSE, RESUME and CLOSE are 'ignored ... no effect'."""
        rng = random.Random(8)
        for _ in range(150):
            ev = _lines(_structured(rng)) + []
            t, d = 10_001, rng.randint(1, 10**6)
            for tid in TICKETS:
                closed = ev + [f"{t},{tid},CLOSE"]
                expect = self._row(impl, closed + [f"{t + 1 + d},{self.GHOST},PAUSE"], tid)
                for e in ("PAUSE", "RESUME", "CLOSE"):
                    got = self._row(impl, closed + [f"{t + 1},{tid},{e}", f"{t + 1 + d},{self.GHOST},PAUSE"], tid)
                    assert got == expect, (tid, e)

    def test_open_resets_and_reopen_continues_after_close(self, impl):
        """Table column CLOSED: OPEN -> 'used time resets to 0'; REOPEN -> 'used time continues from its total'."""
        rng = random.Random(9)
        for _ in range(150):
            ev = _lines(_structured(rng))
            t, d = 10_001, rng.randint(1, 10**6)
            for tid in TICKETS:
                closed = ev + [f"{t},{tid},CLOSE"]
                before = self._row(impl, closed, tid)
                tail = f"{t + 1 + d},{self.GHOST},PAUSE"
                opened = self._row(impl, closed + [f"{t + 1},{tid},OPEN", tail], tid)
                assert (opened["used_ms"], opened["status"]) == (d, "open")
                reopened = self._row(impl, closed + [f"{t + 1},{tid},REOPEN", tail], tid)
                if before is None:
                    assert reopened is None  # REOPEN on NOT_OPENED is ignored
                else:
                    assert (reopened["used_ms"], reopened["status"]) == (before["used_ms"] + d, "open")


def test_brute_force_matches_the_specs_own_example():
    assert brute_force(["100,A,OPEN", "400,A,CLOSE"]) == \
        [{"ticket_id": "A", "used_ms": 300, "breached": False, "status": "closed"}]


def _grader_mutants():
    MUTANTS = _pilot_grader_mutants()
    source = (SLA / "reference.py").read_text(encoding="utf-8")
    for name, edits in MUTANTS.items():
        mutated = source
        for old, new in edits:
            mutated = mutated.replace(old, new)
        ns: dict = {}
        exec(compile(mutated, name, "exec"), ns)  # frozen reference + grader's own edits, not model output
        yield name, ns["compute_sla"]


def test_metamorphic_properties_alone_catch_every_hand_written_bug():
    """No expected values and no oracle: the spec-derived properties by themselves must reject every grader bug."""
    props = [n for n in dir(TestMetamorphic) if n.startswith("test_")]
    for name, fn in _grader_mutants():
        caught = []
        for p in props:
            try:
                getattr(TestMetamorphic(), p)(fn)
            except Exception:
                caught.append(p)
        assert caught, f"no metamorphic property rejects {name}"


def test_brute_force_catches_every_hand_written_bug_in_the_grader():
    """The third oracle is only useful if it disagrees with wrong implementations: every grade.py mutant of
    reference.py must disagree with brute force on some fuzz stream."""
    MUTANTS = _pilot_grader_mutants()
    source = (SLA / "reference.py").read_text(encoding="utf-8")
    streams = _cases(42, 400) + [["0,A,OPEN", f"{LIMIT},A,CLOSE"], ["3,T2,OPEN", "1,T10,OPEN"],
                                 ["0,A,OPEN", "5,A,PAUSE", "9,A,OPEN"], ["1.5,A,OPEN", "3,A,CLOSE"]]
    for name, edits in MUTANTS.items():
        mutated = source
        for old, new in edits:
            mutated = mutated.replace(old, new)
        ns: dict = {}
        exec(compile(mutated, name, "exec"), ns)  # frozen reference + grader's own edits, not model output
        fn = ns["compute_sla"]

        def differs(s):
            try:
                got = fn(list(s))
            except Exception:
                return True
            return type(got) is not list or got != brute_force(s)

        assert any(differs(s) for s in streams), f"brute force cannot distinguish {name}"
