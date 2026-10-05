"""Generates the frozen test set for experiment/bizsla/SPEC.md.

    python experiment/bizsla/generate_cases.py            # writes public/generated cases + FROZEN.json
    python experiment/bizsla/generate_cases.py --check    # verifies files match FROZEN.json (no writes)

Layers:
  public   the 4 SPEC.md examples (shown to every arm; arm B uses them as acceptance cases)
  hand     hand_cases.json: expected values derived by hand from the spec, not by code (hidden)
  edge     targeted boundaries (hidden)
  random / holiday / churn   seeded random streams (hidden)
  medium   up to ~2,000 lines over ~6 weeks (hidden)
  stress   seeded generators (200,000 lines, spans to 10^9 minutes); lines are regenerated at grading time with a
           version-independent PRNG and only the SHA-256 of the expected output is stored (hidden)

Every non-stress expected value is computed by reference.py AND brute_force.py; generation aborts on any
disagreement, and on any hand case where either oracle disagrees with the hand-derived value. Stress expectations
come from reference.py alone (brute force is infeasible there); its counting function is checked separately by
property tests (tests/test_bizsla_oracles.py).
"""
import argparse
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import brute_force  # noqa: E402
import reference  # noqa: E402

PRIOS = ["P1", "P2", "P3", "P4"]
EVENTS = ["OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN"]
FROZEN_FILES = ["SPEC.md", "hand_cases.json", "public_cases.json", "generated_cases.json", "stress_cases.json",
                "reference.py", "brute_force.py", "generate_cases.py"]


def canonical_digest(result) -> str:
    return hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ── Version-independent PRNG for stress inputs (splitmix64) ─────────────────
class SplitMix:
    def __init__(self, seed: int):
        self.s = seed & 0xFFFFFFFFFFFFFFFF

    def next(self) -> int:
        self.s = (self.s + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.s
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)

    def below(self, n: int) -> int:
        return self.next() % n


def _ev(r: SplitMix, open_bias: int = 3) -> str:
    k = r.below(len(EVENTS) + open_bias)
    ev = EVENTS[k] if k < len(EVENTS) else "OPEN"
    return f"{ev},{PRIOS[r.below(4)]}" if ev in ("OPEN", "PRIORITY") else ev


def stress_lines(spec: dict) -> list:
    """Deterministic for a given spec on any Python version."""
    r = SplitMix(spec["seed"])
    kind = spec["kind"]
    out = []
    if kind == "wide":            # many lines, many tickets, huge span, many holidays
        for _ in range(spec["lines"]):
            out.append(f"{r.below(spec['span'])},T{r.below(spec['tickets'])},{_ev(r)}")
        for _ in range(spec["holidays"]):
            out.insert(r.below(len(out) + 1), f"{r.below(spec['span'])},*,HOLIDAY")
    elif kind == "sparse":        # few lines, enormous gaps: minute-by-minute counting cannot finish
        for i in range(spec["lines"]):
            out.append(f"{r.below(spec['span'])},S{i % spec['tickets']},{_ev(r, open_bias=1)}")
        for t in range(spec["tickets"]):
            out.insert(0, f"{r.below(1000)},S{t},OPEN,{PRIOS[r.below(4)]}")
    elif kind == "dense":         # many tickets packed into a few weeks: per-ticket-per-minute work explodes
        for _ in range(spec["lines"]):
            out.append(f"{r.below(spec['span'])},D{r.below(spec['tickets'])},{_ev(r)}")
    elif kind == "toggle":        # one ticket, a long PAUSE/RESUME history
        out.append(f"0,X,OPEN,P4")
        m = 0
        for i in range(spec["lines"]):
            m += 1 + r.below(spec["gap"])
            out.append(f"{m},X,{'PAUSE' if i % 2 == 0 else 'RESUME'}")
        out.reverse()             # arrival order is the reverse of time order
    else:
        raise ValueError(kind)
    return out


STRESS = [
    {"id": "S01", "kind": "wide", "seed": 11, "lines": 200_000, "tickets": 5_000, "holidays": 20_000,
     "span": 1_000_000_000, "title": "200k lines, 5k tickets, 20k holidays, span 10^9"},
    {"id": "S02", "kind": "sparse", "seed": 12, "lines": 60, "tickets": 6, "span": 1_000_000_000,
     "title": "60 lines spread over 10^9 minutes"},
    {"id": "S03", "kind": "dense", "seed": 13, "lines": 200_000, "tickets": 50_000, "span": 40_320,
     "title": "200k lines, 50k tickets in 4 weeks"},
    {"id": "S04", "kind": "toggle", "seed": 14, "lines": 150_000, "gap": 900,
     "title": "one ticket, 150k pause/resume toggles, reverse arrival"},
]


# ── Small cases ─────────────────────────────────────────────────────────────
def random_stream(rng: random.Random, *, span, n, ids, holidays=(0, 2), noise=0.1, prio_bias=0) -> list:
    base = rng.choice([0, 500, 1019, 4000, 6700, 7200])
    out = []
    for _ in range(n):
        m = base + rng.randint(0, span)
        ev = rng.choice(EVENTS + ["OPEN"] + ["PRIORITY"] * prio_bias)
        line = f"{m},{rng.choice(ids)},{ev}" + (f",{rng.choice(PRIOS)}" if ev in ("OPEN", "PRIORITY") else "")
        if rng.random() < noise:
            line = rng.choice([line.lower(), line + ",X", line.replace(",", ";", 1), f" {line} ",
                               f"0{line}", line.replace(str(m), f"{m}.0", 1), f"{m},*,{ev}", ""])
        out.append(line)
    for _ in range(rng.randint(*holidays)):
        out.insert(rng.randint(0, len(out)), f"{max(0, base + rng.randint(-1440, span + 2880))},*,HOLIDAY")
    return out


def edge_cases() -> list:
    E = []
    add = lambda title, lines: E.append({"title": title, "lines": lines})  # noqa: E731
    for o in (539, 540, 1019, 1020):
        for c in (1019, 1020, 1021, 1980):
            if c > o:
                add(f"open {o} close {c}", [f"{o},A,OPEN,P1", f"{c},A,CLOSE"])
    add("open and close in the same minute", ["600,A,OPEN,P1", "600,A,CLOSE"])
    add("close then open in the same minute resets", ["540,A,OPEN,P1", "900,A,CLOSE", "900,A,OPEN,P2", "960,A,PAUSE"])
    add("open on Saturday, close Monday", ["7300,A,OPEN,P2", "10700,A,CLOSE"])
    add("Friday holiday across a breach", ["6000,*,HOLIDAY", "4800,A,OPEN,P1", "11000,A,CLOSE"])
    add("every event on NOT_OPENED is ignored", ["600,A,PRIORITY,P1", "610,A,PAUSE", "620,A,RESUME", "630,A,CLOSE",
                                                 "640,A,REOPEN", "700,B,OPEN,P1"])
    add("second OPEN while running is ignored", ["540,A,OPEN,P1", "600,A,OPEN,P4", "900,A,PAUSE"])
    add("RESUME while running, REOPEN while paused are ignored",
        ["540,A,OPEN,P2", "600,A,RESUME", "660,A,PAUSE", "700,A,REOPEN", "800,A,RESUME", "860,A,CLOSE"])
    add("PAUSE on closed, CLOSE on closed ignored", ["540,A,OPEN,P3", "600,A,CLOSE", "700,A,PAUSE", "800,A,CLOSE",
                                                     "900,A,REOPEN", "960,A,CLOSE"])
    add("priority churn below and above used", ["540,A,OPEN,P4", "1000,A,PRIORITY,P3", "1010,A,PRIORITY,P1",
                                                "1015,A,PRIORITY,P4", "2100,A,CLOSE"])
    add("breach exactly at a REOPEN minute", ["540,A,OPEN,P1", "780,A,CLOSE", "1980,A,REOPEN", "1981,A,CLOSE"])
    add("P4 limit crossed after five days", ["540,A,OPEN,P4", "6779,A,PAUSE", "10620,A,RESUME", "10700,A,CLOSE"])
    add("P3 limit crossed after three days", ["540,A,OPEN,P3", "4860,A,PAUSE", "4900,B,OPEN,P1"])
    add("holiday on every weekday of week 0", [f"{d * 1440 + 3},*,HOLIDAY" for d in range(5)] +
        ["540,A,OPEN,P1", "10700,A,CLOSE"])
    add("duplicate identical lines", ["540,A,OPEN,P1", "540,A,OPEN,P1", "600,A,PAUSE", "600,A,PAUSE",
                                      "700,A,RESUME", "700,A,RESUME", "800,A,CLOSE"])
    add("many tickets, one minute", [f"540,T{i},OPEN,P{1 + i % 4}" for i in range(12)] + ["1020,T3,CLOSE"])
    add("tab and space trimming", ["\t540,A,OPEN,P1\t", "600 ,A ,CLOSE"])
    add("unicode and comma-in-id lines are handled", ["540,Ä,OPEN,P1", "540,é,OPEN,P2", "600,a,b,CLOSE"])
    add("large gap (8 weeks)", ["540,A,OPEN,P4", "60000,B,OPEN,P1", "40000,A,PAUSE"])
    add("priority raise at the breach minute after a night", ["540,A,OPEN,P2", "1981,A,PRIORITY,P4", "2100,A,CLOSE"])
    add("priority raise at the breach minute after a weekend", ["6660,A,OPEN,P1", "10740,A,PRIORITY,P2",
                                                                "10800,A,CLOSE"])
    add("mixed-case event names are malformed", ["540,A,OPEN,P1", "600,A,close", "660,A,Pause", "700,A,CLOSE"])
    add("ticket '*' cannot open", ["540,*,OPEN,P1", "600,*,CLOSE", "540,A,OPEN,P1", "560,*,PAUSE"])
    return E


def build_generated() -> list:
    cases = [{"id": f"E{i + 1:02d}", "layer": "edge", **c} for i, c in enumerate(edge_cases())]
    rng = random.Random(20261005)
    for i in range(80):
        cases.append({"id": f"R{i + 1:03d}", "layer": "random", "title": "random",
                      "lines": random_stream(rng, span=rng.choice([600, 3000, 12000, 25000]), n=rng.randint(1, 20),
                                             ids=rng.sample(["A", "B", "C", "t1", "T10"], rng.randint(1, 3)))})
    for i in range(40):
        cases.append({"id": f"HOL{i + 1:02d}", "layer": "holiday", "title": "holiday-heavy random",
                      "lines": random_stream(rng, span=rng.choice([12000, 25000]), n=rng.randint(4, 16),
                                             ids=["A", "B"], holidays=(3, 10))})
    for i in range(40):
        cases.append({"id": f"CH{i + 1:02d}", "layer": "churn", "title": "priority churn random",
                      "lines": random_stream(rng, span=rng.choice([3000, 12000]), n=rng.randint(6, 24),
                                             ids=["A", "B", "C"], prio_bias=4)})
    for i in range(6):
        cases.append({"id": f"M{i + 1:02d}", "layer": "medium", "title": "medium (brute-force checked)",
                      "lines": random_stream(rng, span=40_000, n=2_000, ids=[f"T{j}" for j in range(40)],
                                             holidays=(5, 20), noise=0.05)})
    return cases


def public_cases() -> list:
    ex = [
        ["540,A,OPEN,P2", "600,A,CLOSE"],
        ["6720,B,OPEN,P1", "10680,B,PAUSE"],
        ["540,C,OPEN,P1", "900,C,CLOSE"],
        ["540,D,OPEN,P3", "2040,D,PAUSE", "open,D,RESUME", "2100,D,RESUME,P1", "5,*,HOLIDAY"],
    ]
    return [{"id": f"PUB{i + 1}", "layer": "public", "title": f"SPEC example {i + 1}", "lines": l} for i, l in
            enumerate(ex)]


def label(cases: list) -> list:
    for c in cases:
        ref, bf = reference.compute_sla(list(c["lines"])), brute_force.compute_sla(list(c["lines"]))
        if ref != bf:
            raise SystemExit(f"ORACLES DISAGREE on {c['id']}: reference={ref} brute_force={bf}")
        c["expected"] = ref
    return cases


def verify_hand() -> None:
    for c in json.loads((HERE / "hand_cases.json").read_text(encoding="utf-8")):
        for name, f in (("reference", reference.compute_sla), ("brute_force", brute_force.compute_sla)):
            got = f(list(c["lines"]))
            if got != c["expected"]:
                raise SystemExit(f"{name} disagrees with hand-derived {c['id']} ({c['title']}): {got}")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check() -> bool:
    frozen = json.loads((HERE / "FROZEN.json").read_text(encoding="utf-8"))
    bad = [f for f in FROZEN_FILES if sha(HERE / f) != frozen["sha256"].get(f)]
    print("[pass] bizsla frozen set matches FROZEN.json" if not bad else f"[FAIL] bizsla files changed: {bad}")
    return not bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        sys.exit(0 if check() else 1)
    verify_hand()
    pub = label(public_cases())
    gen = label(build_generated())
    stress = []
    for s in STRESS:
        result = reference.compute_sla(stress_lines(s))
        stress.append({**s, "layer": "stress", "expected_sha256": canonical_digest(result),
                       "expected_count": len(result)})
    dump = lambda p, obj: (HERE / p).write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n",  # noqa: E731
                                                encoding="utf-8")
    dump("public_cases.json", pub)
    dump("generated_cases.json", gen)
    dump("stress_cases.json", stress)
    frozen = {"frozen_at": datetime.now(timezone.utc).isoformat(),
              "sha256": {f: sha(HERE / f) for f in FROZEN_FILES}}
    (HERE / "FROZEN.json").write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")
    layers = {}
    for c in gen:
        layers[c["layer"]] = layers.get(c["layer"], 0) + 1
    print(f"public {len(pub)}, hand {len(json.loads((HERE / 'hand_cases.json').read_text(encoding='utf-8')))}, "
          f"generated {layers}, stress {len(stress)}; oracles agree on every non-stress case")


if __name__ == "__main__":
    main()
