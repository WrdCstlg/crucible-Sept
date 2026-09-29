"""Builds the generated test layers for the SLA pilot and freezes the test set.

Layer 1 (hand_cases.json, written by the user) is the ground truth. This script:
  1. checks both reference oracles pass every hand case (stops otherwise);
  2. builds Layer 2: one targeted edge case per spec rule, each with an expected value
     computed by hand in this file; both oracles must reproduce it exactly;
  3. builds Layer 3: seeded random mixes and large stress streams, expected values from
     oracle #1, which oracle #2 must match exactly;
  4. writes generated_cases.json and FROZEN.json (SHA-256 of spec, cases and oracles).

Nothing here is ever shown to the models under test.
"""
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import reference  # noqa: E402
import reference_intervals  # noqa: E402

LIMIT = 14_400_000
HOUR = 3_600_000


def row(ticket_id, used_ms, status):
    return {"ticket_id": ticket_id, "used_ms": used_ms, "breached": used_ms > LIMIT, "status": status}


# Layer 2: one targeted case per rule. The expected values below were computed by hand.
EDGE_CASES = [
    ("E01", "Empty stream returns []", [], []),
    ("E02", "Only malformed lines returns []", ["", "   ", "abc", "1,2", "1,T1,OPEN,"], []),
    ("E03", "Open ticket at exactly the limit at end of stream does not breach",
     ["0,T1,OPEN", "14400000,T2,OPEN"], [row("T1", 14_400_000, "open"), row("T2", 0, "open")]),
    ("E04", "Open ticket 1 ms over the limit at end of stream breaches",
     ["0,T1,OPEN", "14400001,T2,OPEN"], [row("T1", 14_400_001, "open"), row("T2", 0, "open")]),
    ("E05", "RESUME on a closed ticket is ignored (clock must not restart)",
     ["0,T1,OPEN", "1000,T1,CLOSE", "2000,T1,RESUME", "9000,T2,OPEN"], [row("T1", 1000, "closed"), row("T2", 0, "open")]),
    ("E06", "PAUSE on a closed ticket is ignored; a later REOPEN runs, not paused",
     ["0,T1,OPEN", "1000,T1,CLOSE", "2000,T1,PAUSE", "3000,T1,REOPEN", "5000,T1,CLOSE"], [row("T1", 3000, "closed")]),
    ("E07", "OPEN on a closed ticket resets used time to zero",
     ["0,T1,OPEN", "20000000,T1,CLOSE", "21000000,T1,OPEN", "21000500,T1,CLOSE"], [row("T1", 500, "closed")]),
    ("E08", "REOPEN while running or paused is ignored",
     ["0,T1,OPEN", "1000,T1,REOPEN", "2000,T1,PAUSE", "3000,T1,REOPEN", "4000,T1,RESUME", "6000,T1,CLOSE"],
     [row("T1", 4000, "closed")]),
    ("E09", "OPEN while running does not reset; OPEN while paused does not resume",
     ["0,T1,OPEN", "5000,T1,OPEN", "6000,T1,PAUSE", "7000,T1,OPEN", "9000,T1,CLOSE"], [row("T1", 6000, "closed")]),
    ("E10", "Out-of-order arrival is sorted by timestamp",
     ["3000,T1,CLOSE", "0,T1,OPEN", "2000,T1,RESUME", "1000,T1,PAUSE"], [row("T1", 2000, "closed")]),
    ("E11", "Events earlier than the first OPEN are ignored even if they arrive later",
     ["1000,T1,PAUSE", "500,T1,CLOSE", "2000,T1,OPEN", "3000,T1,CLOSE"], [row("T1", 1000, "closed")]),
    ("E12", "Tie: PAUSE then RESUME at the same ms nets zero paused time",
     ["0,T1,OPEN", "1000,T1,PAUSE", "1000,T1,RESUME", "3000,T1,CLOSE"], [row("T1", 3000, "closed")]),
    ("E13", "Tie: RESUME then PAUSE at the same ms leaves the ticket paused",
     ["0,T1,OPEN", "1000,T1,RESUME", "1000,T1,PAUSE", "3000,T2,OPEN"], [row("T1", 1000, "open"), row("T2", 0, "open")]),
    ("E14", "Tie: CLOSE+REOPEN vs REOPEN+CLOSE at the same ms depends on arrival order",
     ["0,T1,OPEN", "1000,T1,CLOSE", "1000,T1,REOPEN", "0,T2,OPEN", "1000,T2,REOPEN", "1000,T2,CLOSE", "5000,T3,OPEN"],
     [row("T1", 5000, "open"), row("T2", 1000, "closed"), row("T3", 0, "open")]),
    ("E15", "A malformed line with a huge timestamp must not move now",
     ["0,T1,OPEN", "99999999999,T2", "99999999999,T2,OPEN,extra", "1000,T3,OPEN"], [row("T1", 1000, "open"), row("T3", 0, "open")]),
    ("E16", "Malformed variants are all ignored",
     ["0,T1,OPEN", "1000.0,T1,CLOSE", "+2000,T1,CLOSE", "-5,T1,CLOSE", "3000,T1,close", "4000,,CLOSE", "5000,T1,CLOSE,",
      "1e3,T1,CLOSE", "6000 T1 CLOSE", "", "7000,T2,OPEN"], [row("T1", 7000, "open"), row("T2", 0, "open")]),
    ("E17", "Leading zeros and whitespace-padded fields are well-formed",
     ["007,T1,OPEN", "  0000000107 ,  T1 ,  CLOSE  "], [row("T1", 100, "closed")]),
    ("E18", "A well-formed but invalid event still sets now",
     ["0,T1,OPEN", "20000000,T9,CLOSE"], [row("T1", 20_000_000, "open")]),
    ("E19", "Sort is code-point order and ticket IDs are case-sensitive",
     ["0,T2,OPEN", "0,T10,OPEN", "0,t1,OPEN", "0,T1,OPEN", "10,T2,CLOSE", "20,T10,CLOSE", "30,t1,CLOSE", "40,T1,CLOSE"],
     [row("T1", 40, "closed"), row("T10", 20, "closed"), row("T2", 10, "closed"), row("t1", 30, "closed")]),
    ("E20", "A paused ticket at end of stream counts only up to its pause",
     ["0,T1,OPEN", "1000,T1,PAUSE", "50000000,T2,OPEN"], [row("T1", 1000, "open"), row("T2", 0, "open")]),
    ("E21", "Closed while paused, then REOPEN runs from the REOPEN",
     ["0,T1,OPEN", "1000,T1,PAUSE", "2000,T1,CLOSE", "3000,T1,REOPEN", "3500,T1,CLOSE"], [row("T1", 1500, "closed")]),
    ("E22", "After an OPEN reset, a later REOPEN continues from the reset total",
     ["0,T1,OPEN", "10000,T1,CLOSE", "20000,T1,OPEN", "21000,T1,CLOSE", "22000,T1,REOPEN", "23000,T1,CLOSE"],
     [row("T1", 2000, "closed")]),
    ("E23", "Breach accumulated across a REOPEN cycle",
     ["0,T1,OPEN", "7200000,T1,CLOSE", "8000000,T1,REOPEN", "15200001,T1,CLOSE"], [row("T1", 14_400_001, "closed")]),
    ("E24", "Now is the largest timestamp, not the timestamp of the last line to arrive",
     ["0,T1,OPEN", "9000,T2,OPEN", "1000,T3,OPEN"], [row("T1", 9000, "open"), row("T2", 0, "open"), row("T3", 8000, "open")]),
]


def ticket_ids(rng, k):
    style = rng.random()
    if style < 0.70:
        return f"T{k}"
    if style < 0.85:
        return f"t{k}"
    return f"TK-{k:05d}"


def gap(rng):
    r = rng.random()
    if r < 0.06:
        return 0  # exact tie with the previous event of this ticket
    if r < 0.20:
        return rng.randint(1, 1000)
    if r < 0.70:
        return rng.randint(60_000, 90 * 60_000)
    return rng.randint(HOUR, 5 * HOUR)


def ticket_events(rng, tid, start):
    """Yields (timestamp, line) for one ticket's lifecycle, deliberately including invalid events."""
    t = start
    kind = rng.random()
    if kind < 0.05:  # never opened: only invalid events
        for _ in range(rng.randint(1, 3)):
            t += gap(rng)
            yield t, f"{t},{tid},{rng.choice(['PAUSE', 'RESUME', 'CLOSE', 'REOPEN'])}"
        return
    if kind < 0.13:  # engineered boundary: running total of exactly LIMIT-1, LIMIT or LIMIT+1
        target = LIMIT + rng.choice([-1, 0, 1])
        yield t, f"{t},{tid},OPEN"
        remaining = target
        while remaining > 0:
            run = remaining if rng.random() < 0.4 else rng.randint(1, remaining)
            t += run
            remaining -= run
            if remaining > 0:
                yield t, f"{t},{tid},PAUSE"
                t += rng.randint(1, 2 * HOUR)
                yield t, f"{t},{tid},RESUME"
        yield t, f"{t},{tid},CLOSE"
        return

    state = "NOT_OPENED"
    if rng.random() < 0.08:  # an event before the ticket is opened
        yield t, f"{t},{tid},{rng.choice(['PAUSE', 'CLOSE', 'RESUME'])}"
        t += gap(rng)
    yield t, f"{t},{tid},OPEN"
    state = "RUNNING"
    for _ in range(rng.randint(1, 9)):
        t += gap(rng)
        invalid = rng.random() < 0.15
        if state == "RUNNING":
            ev = rng.choice(["OPEN", "RESUME", "REOPEN"]) if invalid else rng.choice(["PAUSE", "PAUSE", "CLOSE"])
            state = {"PAUSE": "PAUSED", "CLOSE": "CLOSED"}.get(ev, state)
        elif state == "PAUSED":
            ev = rng.choice(["PAUSE", "OPEN", "REOPEN"]) if invalid else rng.choice(["RESUME", "RESUME", "CLOSE"])
            state = {"RESUME": "RUNNING", "CLOSE": "CLOSED"}.get(ev, state)
        else:  # CLOSED
            ev = rng.choice(["PAUSE", "RESUME", "CLOSE"]) if invalid else rng.choice(["REOPEN", "REOPEN", "OPEN"])
            state = "RUNNING" if ev in ("REOPEN", "OPEN") else state
        yield t, f"{t},{tid},{ev}"
        if state == "CLOSED" and rng.random() < 0.5:
            return


MALFORMED = [
    lambda ts, tid, ev: f"{ts}.0,{tid},{ev}",
    lambda ts, tid, ev: f"+{ts},{tid},{ev}",
    lambda ts, tid, ev: f"{ts},{tid},{ev.lower()}",
    lambda ts, tid, ev: f"{ts},,{ev}",
    lambda ts, tid, ev: f"{ts},{tid},{ev},",
    lambda ts, tid, ev: f"{ts},{tid}",
    lambda ts, tid, ev: f"{ts} {tid} {ev}",
    lambda ts, tid, ev: f"{ts},{tid},{ev}D",
    lambda ts, tid, ev: "",
    lambda ts, tid, ev: "   ",
    lambda ts, tid, ev: f"# comment {ts}",
]


def stream(seed, n_tickets, horizon_hours=72, malformed_rate=0.03, shuffle_window=6):
    rng = random.Random(seed)
    base = 1_700_000_000_000
    timed = []
    for k in range(n_tickets):
        tid = ticket_ids(rng, k)
        start = base + rng.randint(0, horizon_hours * HOUR)
        timed.extend(ticket_events(rng, tid, start))
    timed.sort(key=lambda p: p[0])
    lines = [line for _, line in timed]
    # out-of-order arrival: local shuffles inside small windows
    for i in range(0, len(lines), shuffle_window):
        if rng.random() < 0.5:
            window = lines[i:i + shuffle_window]
            rng.shuffle(window)
            lines[i:i + shuffle_window] = window
    # well-formed but unusual formatting: whitespace padding and leading zeros
    for i, line in enumerate(lines):
        if rng.random() < 0.03:
            ts, tid, ev = line.split(",")
            lines[i] = f"  {'00' + ts if rng.random() < 0.5 else ts} , {tid} ,{ev}  "
    # malformed lines, some carrying timestamps far beyond any valid one (must not move now)
    huge = base + horizon_hours * HOUR * 50
    for _ in range(max(1, int(len(lines) * malformed_rate))):
        ts, tid, ev = timed[rng.randrange(len(timed))][1].split(",")
        if rng.random() < 0.3:
            ts = str(huge + rng.randint(0, HOUR))
        lines.insert(rng.randrange(len(lines) + 1), rng.choice(MALFORMED)(ts, tid, ev))
    return lines


def main():
    hand = json.loads((HERE / "hand_cases.json").read_text(encoding="utf-8"))
    oracles = {"reference": reference.compute_sla, "reference_intervals": reference_intervals.compute_sla}

    for case in hand:
        for name, fn in oracles.items():
            got = fn(list(case["lines"]))
            if got != case["expected"]:
                sys.exit(f"STOP: {name} fails hand case {case['id']}: expected {case['expected']}, got {got}")
    print(f"both oracles pass all {len(hand)} hand cases")

    generated = []
    for cid, title, lines, expected in EDGE_CASES:
        for name, fn in oracles.items():
            got = fn(list(lines))
            if got != expected:
                sys.exit(f"STOP: {name} disagrees with hand-computed {cid}: expected {expected}, got {got}")
        generated.append({"id": cid, "layer": "edge", "title": title, "author": "harness (Claude), hand-computed",
                          "lines": lines, "expected": expected})
    print(f"both oracles match all {len(EDGE_CASES)} hand-computed edge cases")

    specs = [(f"R{i}", f"Random mix #{i}: 8 tickets", 100 + i, 8) for i in range(1, 7)]
    specs += [("S1", "Stress: 60 tickets", 11, 60), ("S2", "Stress: 600 tickets", 22, 600),
              ("S3", "Stress: 6000 tickets", 33, 6000)]
    for cid, title, seed, n in specs:
        lines = stream(seed, n)
        a = oracles["reference"](list(lines))
        b = oracles["reference_intervals"](list(lines))
        if a != b:
            sys.exit(f"STOP: oracles disagree on {cid}")
        breached = sum(r["breached"] for r in a)
        exact = sum(r["used_ms"] == LIMIT for r in a)
        print(f"{cid}: {len(lines):>6} lines, {len(a):>5} tickets in output, {breached} breached, {exact} at exactly the limit")
        generated.append({"id": cid, "layer": "stress" if cid.startswith("S") else "random",
                          "title": title, "author": f"harness (Claude), seeded generator seed={seed}",
                          "lines": lines, "expected": a})

    out = HERE / "generated_cases.json"
    out.write_text(json.dumps(generated), encoding="utf-8")

    frozen = {"frozen_at": datetime.now(timezone.utc).isoformat(), "sha256": {}}
    for name in ["SPEC.md", "hand_cases.json", "generated_cases.json", "reference.py", "reference_intervals.py", "generate_cases.py"]:
        frozen["sha256"][name] = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
    (HERE / "FROZEN.json").write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    print(f"wrote {len(generated)} generated cases and FROZEN.json")


if __name__ == "__main__":
    main()
