"""Cases for Problem 13 (shift rostering with backtracking). Stdlib only (copied into the sandbox like every cases.py).

Cases with "spec_expected" were worked out by hand from SPEC.md; the build fails if the reference disagrees.
Dates used by the hand cases: 2026-03-02 is a Monday, 2026-03-08 a Sunday, 2026-03-09 the next Monday.
"""
from datetime import date, timedelta


class SplitMix:
    """Version-independent PRNG (the sandbox and the host may run different Python versions)."""

    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFFFFFFFFFF

    def next(self):
        self.s = (self.s + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.s
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)

    def below(self, n):
        return self.next() % n

    def pick(self, seq):
        return seq[self.below(len(seq))]

    def chance(self, num, den):
        return self.below(den) < num


# ── Builders ────────────────────────────────────────────────────────────────
def P(i, skills=("x",), cap=2400, off=(), senior=False):
    return {"id": i, "skills": list(skills), "max_minutes_week": cap, "unavailable": list(off), "senior": senior}


def S(i, start, end, skill="x", need=1, senior=False):
    return {"id": i, "start": start, "end": end, "skill": skill, "need": need, "needs_senior": senior}


def R(rest=0, run=7, pairs=()):
    return {"min_rest_minutes": rest, "max_consecutive_days": run, "forbidden_pairs": [list(p) for p in pairs]}


def out(ok, assignments, minutes, ig_staff=(), ig_shifts=()):
    return {"ok": ok, "assignments": assignments, "minutes": minutes,
            "ignored": {"staff": list(ig_staff), "shifts": list(ig_shifts)}}


def case(cid, title, staff, shifts, rules, expected=None):
    c = {"id": cid, "title": title, "args": [staff, shifts, rules]}
    if expected is not None:
        c["spec_expected"] = expected
    return c


D = "2026-03-"


# ── Public: the four SPEC.md examples (built with the same helpers as the spec text) ──
def ex_person(i, skills, off=(), senior=False):
    return {"id": i, "skills": skills, "max_minutes_week": 2400, "unavailable": list(off), "senior": senior}


def ex_shift(i, start, end, skill, need=1, senior=False):
    return {"id": i, "start": start, "end": end, "skill": skill, "need": need, "needs_senior": senior}


def ex_rules(rest=0, run=7, pairs=()):
    return {"min_rest_minutes": rest, "max_consecutive_days": run, "forbidden_pairs": [list(p) for p in pairs]}


def public():
    person, shift, rules = ex_person, ex_shift, ex_rules
    return [
        case("P1", "load order, ids compared as strings, increasing seat ids",
             [person(i, ["med"]) for i in ["s1", "s2", "s10"]],
             [shift("d1", "2026-03-02 09:00", "2026-03-02 17:00", "med", 2),
              shift("d2", "2026-03-03 09:00", "2026-03-03 17:00", "med", 2),
              shift("d3", "2026-03-04 09:00", "2026-03-04 13:00", "med")], rules(),
             {"ok": True, "assignments": {"d1": ["s1", "s10"], "d2": ["s1", "s2"], "d3": ["s10"]},
              "minutes": {"s1": 960, "s10": 720, "s2": 480}, "ignored": {"staff": [], "shifts": []}}),
        case("P2", "rest across midnight, senior on the last seat, backtracking into an earlier shift",
             [person("ann", ["er"], senior=True), person("bob", ["er"]), person("cat", ["er"])],
             [shift("sun", "2026-03-08 22:00", "2026-03-09 06:00", "er"),
              shift("mon", "2026-03-09 18:00", "2026-03-09 23:00", "er", 2, senior=True)], rules(rest=780),
             {"ok": True, "assignments": {"sun": ["bob"], "mon": ["ann", "cat"]},
              "minutes": {"ann": 300, "bob": 480, "cat": 300}, "ignored": {"staff": [], "shifts": []}}),
        case("P3", "dates a shift is on, availability, consecutive days, no roster",
             [person("kim", ["icu"]), person("lee", ["icu"], ["2026-03-03", "2026-03-05"])],
             [shift("a", "2026-03-02 16:00", "2026-03-03 00:00", "icu"),
              shift("b", "2026-03-03 16:00", "2026-03-04 00:00", "icu"),
              shift("c", "2026-03-04 22:00", "2026-03-05 06:00", "icu")], rules(run=2),
             {"ok": False, "assignments": {}, "minutes": {"kim": 0, "lee": 0},
              "ignored": {"staff": [], "shifts": []}}),
        case("P4", "ignored records, a forbidden pair, a valid person with no shifts",
             [person("amy", ["lab"], senior=True), person("ben", ["lab"], ["2026-02-30"]),
              person("cal", ["lab", "lab"]), person("dee", ["lab"]), person("dee", ["lab"], senior=True),
              person("eve", []), person("fay", ["lab"])],
             [shift("x1", "2026-03-02 08:00", "2026-03-02 12:00", "lab", 2),
              shift("x2", "2026-03-02 13:00", "2026-03-02 17:00", "lab", True),
              shift("x3", "2026-03-03 08:00", "2026-03-03 12:00", "lab", 2)],
             rules(pairs=[["cal", "amy"], ["ben", "cal"]]),
             {"ok": True, "assignments": {"x1": ["amy", "fay"], "x3": ["cal", "fay"]},
              "minutes": {"amy": 240, "cal": 240, "eve": 0, "fay": 480},
              "ignored": {"staff": [1, 3, 4], "shifts": [1]}}),
    ]

# ── Hand cases (each expected output derived from SPEC.md alone) ────────────
def hand():
    bad_staff = [
        P("ok1"),                                                     # 0 valid
        "z1",                                                         # 1 not a dict
        {"id": "z2", "skills": ["x"], "max_minutes_week": 600, "unavailable": []},   # 2 no "senior"
        P(""),                                                        # 3 empty id
        P(7),                                                         # 4 id not a string
        {**P("z5"), "skills": "x"},                                   # 5 skills not a list
        P("z6", skills=["x", 3]),                                     # 6 a skill that is not a string
        P("z7", cap=True),                                            # 7 bool is not an int
        P("z8", cap=480.0),                                           # 8 float cap
        P("z9", off=["2026-03-02", "2026-3-04"]),                     # 9 one bad date ignores the record
        P("z10", off=["2026-02-29"]),                                 # 10 2026 is not a leap year
        P("ok2", off=["2028-02-29"]),                                 # 11 valid (leap day)
        {**P("z12"), "senior": 1},                                    # 12 senior not a bool
        {**P("z13"), "unavailable": "2026-03-02"},                    # 13 unavailable not a list
        {**P("ok3"), "note": "extra keys are fine"},                  # 14 valid
        P("z15", off=["2026-03-02 "]),                                # 15 11 characters
        P("z16", off=["1900-02-29"]),                                 # 16 1900 is not a leap year
        P("ok4", off=["2000-02-29"]),                                 # 17 valid (2000 is a leap year)
    ]
    bad_shifts = [
        S("v1", D + "02 08:00", D + "02 12:00"),                      # 0 valid
        S("q1", D + "02 08:00", D + "02 12:00", need=0),              # 1 need 0
        S("q2", D + "02 08:00", D + "02 12:00", need=True),           # 2 bool need
        S("q3", D + "02 08:00", D + "02 12:00", need=1.0),            # 3 float need
        S("q4", D + "02 08:00", D + "02 12:00", senior="no"),         # 4 needs_senior not a bool
        S("q5", D + "02 24:00", D + "03 02:00"),                      # 5 hour 24
        S("q6", "2026-3-02 09:00", D + "02 12:00"),                   # 6 15 characters
        S("q7", "2026-03-02T09:00", D + "02 12:00"),                  # 7 T instead of space
        S("q8", D + "03 08:00", D + "04 08:01"),                      # 8 1441 minutes
        S("v2", D + "05 08:00", D + "06 08:00"),                      # 9 exactly 1440 minutes: valid
        S("q10", D + "02 08:00", D + "02 08:00"),                     # 10 end not later than start
        S("q11", D + "02 08:00", D + "02 12:00", skill=None),         # 11 skill not a string
        S("", D + "02 08:00", D + "02 12:00"),                        # 12 empty id
        {k: v for k, v in S("q13", D + "02 08:00", D + "02 12:00").items() if k != "needs_senior"},  # 13 key missing
        S("q14", "２026-03-02 09:00", D + "02 12:00"),            # 14 fullwidth digit
        ["v1", D + "02 08:00", D + "02 12:00"],                       # 15 not a dict
    ]
    return [
        case("H01", "W counts only the shift's own week (Sunday, then Monday)",
             [P("a"), P("b")], [S("sun", D + "08 09:00", D + "08 17:00"), S("mon", D + "09 09:00", D + "09 17:00")],
             R(), out(True, {"sun": ["a"], "mon": ["a"]}, {"a": 960, "b": 0})),
        # sunN belongs to the week of 03-02, so on Monday a still has W 0 and wins on id; a's cap of 480 is
        # spent in the earlier week, so monE's 240 minutes fit.
        case("H02", "an overnight Sunday shift belongs to its start week (order and cap)",
             [P("a", cap=480), P("b")],
             [S("sunN", D + "08 22:00", D + "09 06:00"), S("monE", D + "09 18:00", D + "09 22:00")],
             R(rest=600), out(True, {"sunN": ["a"], "monE": ["a"]}, {"a": 720, "b": 0})),
        case("H03", "a shift ending at exactly 00:00 is not on the next date",
             [P("a", off=[D + "03"]), P("b")], [S("late", D + "02 16:00", D + "03 00:00")],
             R(), out(True, {"late": ["a"]}, {"a": 480, "b": 0})),
        case("H04", "one minute past midnight puts a shift on the next date",
             [P("a", off=[D + "03"]), P("b")], [S("late", D + "02 16:00", D + "03 00:01")],
             R(), out(True, {"late": ["b"]}, {"a": 0, "b": 481})),
        # q -> a (03-02, 03-03). r: b unavailable, a would work 02-04 (3 > 2) -> back to q -> b. r -> a.
        case("H05", "an overnight shift counts on both dates for consecutive days",
             [P("a"), P("b", off=[D + "04"])],
             [S("q", D + "02 22:00", D + "03 06:00"), S("r", D + "04 08:00", D + "04 12:00")],
             R(run=2), out(True, {"q": ["b"], "r": ["a"]}, {"a": 240, "b": 480})),
        # sat, sun -> a. mon: a would make 07-08-09; b takes it. tue: a's run restarts (09 not worked by a).
        case("H06", "consecutive-day runs continue across the week boundary",
             [P("a"), P("b", off=[D + "07", D + "08"])],
             [S("sat", D + "07 09:00", D + "07 17:00"), S("sun", D + "08 09:00", D + "08 17:00"),
              S("mon", D + "09 09:00", D + "09 17:00"), S("tue", D + "10 09:00", D + "10 17:00")],
             R(run=2), out(True, {"sat": ["a"], "sun": ["a"], "mon": ["b"], "tue": ["a"]}, {"a": 1440, "b": 480})),
        case("H07", "rest exactly equal to the minimum is allowed (across midnight)",
             [P("a", skills=["x", "y"]), P("b")],
             [S("s1", D + "02 08:00", D + "02 16:00"), S("s2", D + "03 02:00", D + "03 06:00", skill="y")],
             R(rest=600), out(True, {"s1": ["a"], "s2": ["a"]}, {"a": 720, "b": 0})),
        case("H08", "one minute short of rest forces a backtrack into the earlier shift",
             [P("a", skills=["x", "y"]), P("b")],
             [S("s1", D + "02 08:00", D + "02 16:00"), S("s2", D + "03 01:59", D + "03 06:00", skill="y")],
             R(rest=600), out(True, {"s1": ["b"], "s2": ["a"]}, {"a": 241, "b": 480})),
        case("H09", "touching shifts do not overlap when min rest is 0",
             [P("a", skills=["x", "y"]), P("b")],
             [S("t1", D + "02 08:00", D + "02 12:00"), S("t2", D + "02 12:00", D + "02 16:00", skill="y")],
             R(), out(True, {"t1": ["a"], "t2": ["a"]}, {"a": 480, "b": 0})),
        case("H10", "the weekly cap is inclusive; a cap of 0 is valid",
             [P("a", cap=480), P("b", cap=0)],
             [S("w1", D + "02 08:00", D + "02 12:00"), S("w2", D + "03 08:00", D + "03 12:00")],
             R(), out(True, {"w1": ["a"], "w2": ["a"]}, {"a": 480, "b": 0})),
        # week of 03-02: 120 + 480 = 600; week of 03-09: 480. Splitting sunN at midnight would overload 03-09.
        case("H11", "an overnight shift's whole length counts in its start week (cap)",
             [P("a", cap=600)],
             [S("sat", D + "07 08:00", D + "07 10:00"), S("sunN", D + "08 20:00", D + "09 04:00"),
              S("mon", D + "09 12:00", D + "09 20:00")],
             R(), out(True, {"sat": ["a"], "sunN": ["a"], "mon": ["a"]}, {"a": 1080})),
        case("H12", "forbidden pairs are unordered",
             [P("a"), P("b"), P("c")], [S("f", D + "02 08:00", D + "02 12:00", need=2)],
             R(pairs=[["b", "a"]]), out(True, {"f": ["a", "c"]}, {"a": 240, "b": 0, "c": 240})),
        case("H13", "forbidden pairs only apply within one shift",
             [P("a"), P("b"), P("c")],
             [S("u1", D + "02 08:00", D + "02 12:00"), S("u2", D + "02 08:00", D + "02 12:00")],
             R(pairs=[["a", "b"]]), out(True, {"u1": ["a"], "u2": ["b"]}, {"a": 240, "b": 240, "c": 0})),
        case("H14", "the senior check is made on the last seat, not the first",
             [P("a"), P("b", senior=True), P("c")], [S("g", D + "02 08:00", D + "02 12:00", need=2, senior=True)],
             R(), out(True, {"g": ["a", "b"]}, {"a": 240, "b": 240, "c": 0})),
        # w2: [b, c] has no senior, c leaves no seat 1, so seat 0 falls back to a (W 120), then b.
        case("H15", "senior check fails until a lower-id senior with more minutes takes seat 0",
             [P("a", senior=True), P("b"), P("c")],
             [S("w1", D + "02 08:00", D + "02 10:00"), S("w2", D + "03 08:00", D + "03 10:00", need=2, senior=True)],
             R(), out(True, {"w1": ["a"], "w2": ["a", "b"]}, {"a": 240, "b": 120, "c": 0})),
        case("H16", "duplicate staff ids: every valid copy is ignored; an invalid copy does not count",
             [P("a"), P("a"), P("b", cap=-1), P("b"), P("c")], [S("h", D + "02 08:00", D + "02 12:00")],
             R(), out(True, {"h": ["b"]}, {"b": 240, "c": 0}, [0, 1, 2])),
        case("H17", "duplicate shift ids: all valid copies are ignored",
             [P("a")],
             [S("x", D + "02 08:00", D + "02 12:00"), S("x", D + "03 08:00", D + "03 12:00"),
              S("y", D + "02 12:00", D + "02 11:00"), S("y", D + "04 08:00", D + "04 12:00")],
             R(), out(True, {"y": ["a"]}, {"a": 240}, [], [0, 1, 2])),
        case("H18", "staff validation", bad_staff, [S("s", D + "02 08:00", D + "02 12:00", need=3)],
             R(), out(True, {"s": ["ok1", "ok2", "ok3"]}, {"ok1": 240, "ok2": 240, "ok3": 240, "ok4": 0},
                      [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 15, 16])),
        case("H19", "shift validation (1440 minutes is the longest valid shift)", [P("a")], bad_shifts,
             R(), out(True, {"v1": ["a"], "v2": ["a"]}, {"a": 1680}, [],
                      [1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15])),
        case("H20", "an unfillable later shift makes the whole call fail",
             [P("a"), P("b")],
             [S("s1", D + "02 08:00", D + "02 12:00"), S("s2", D + "03 08:00", D + "03 12:00", skill="z")],
             R(), out(False, {}, {"a": 0, "b": 0})),
        case("H21", "no valid shifts: ok with an empty roster",
             [P("a"), {**P("q"), "senior": "yes"}], [S("s", D + "02 08:00", D + "02 12:00", need=0)],
             R(), out(True, {}, {"a": 0}, [1], [0])),
        case("H22", "empty input", [], [], R(), out(True, {}, {})),
        case("H23", "slot order: equal starts, the shorter shift first",
             [P("a"), P("b")], [S("y", D + "02 08:00", D + "02 16:00"), S("z", D + "02 08:00", D + "02 12:00")],
             R(), out(True, {"z": ["a"], "y": ["b"]}, {"a": 240, "b": 480})),
        case("H24", "slot order: equal times, shift ids compared as strings",
             [P("a"), P("b")], [S("m9", D + "02 09:00", D + "02 10:00"), S("m10", D + "02 09:00", D + "02 10:00")],
             R(), out(True, {"m10": ["a"], "m9": ["b"]}, {"a": 60, "b": 60})),
        # s4: W is a 480, b 60, c 60 (minutes, not shift counts), so b wins on id.
        case("H25", "W is minutes in the week, not the number of shifts",
             [P("a"), P("b"), P("c")],
             [S("s1", D + "02 08:00", D + "02 16:00"), S("s2", D + "03 08:00", D + "03 09:00"),
              S("s3", D + "03 10:00", D + "03 11:00"), S("s4", D + "04 08:00", D + "04 09:00")],
             R(), out(True, {"s1": ["a"], "s2": ["b"], "s3": ["c"], "s4": ["b"]}, {"a": 480, "b": 120, "c": 60})),
        # p3 seat 0: b (W 0). Seat 1 may only use ids above "b": c (W 200), even though a has W 100.
        case("H26", "later seats take the lowest W among higher ids only",
             [P("a"), P("b", off=[D + "02"]), P("c")],
             [S("p1", D + "02 08:00", D + "02 09:40"), S("p2", D + "02 10:00", D + "02 13:20"),
              S("p3", D + "03 08:00", D + "03 12:00", need=2)],
             R(), out(True, {"p1": ["a"], "p2": ["c"], "p3": ["b", "c"]}, {"a": 100, "b": 240, "c": 440})),
        case("H27", "max_consecutive_days = 1 forbids every shift that is on two dates",
             [P("a"), P("b")], [S("n", D + "02 22:00", D + "03 02:00")],
             R(run=1), out(False, {}, {"a": 0, "b": 0})),
        case("H28", "skill names match exactly",
             [P("a", skills=["ICU"]), P("b", skills=["icu"])], [S("k", D + "02 08:00", D + "02 12:00", skill="icu")],
             R(), out(True, {"k": ["b"]}, {"a": 0, "b": 240})),
        case("H29", "a one-seat senior shift needs a senior in seat 0",
             [P("a"), P("b", senior=True)], [S("k", D + "02 08:00", D + "02 12:00", senior=True)],
             R(), out(True, {"k": ["b"]}, {"a": 0, "b": 240})),
        case("H30", "ids, not input order, break ties and order seats",
             [P("b"), P("a"), P("c")],
             [S("k", D + "02 08:00", D + "02 12:00"), S("m", D + "02 13:00", D + "02 15:00", need=2)],
             R(), out(True, {"k": ["a"], "m": ["b", "c"]}, {"a": 240, "b": 120, "c": 120})),
        case("H31", "rest applies between two shifts on the same date",
             [P("a", skills=["x", "y"]), P("b")],
             [S("t1", D + "02 08:00", D + "02 12:00"), S("t2", D + "02 13:00", D + "02 15:00", skill="y")],
             R(rest=120), out(True, {"t1": ["b"], "t2": ["a"]}, {"a": 120, "b": 240})),
        case("H32", "a run of exactly max_consecutive_days is allowed",
             [P("a")],
             [S("d1", D + "02 08:00", D + "02 12:00"), S("d2", D + "03 08:00", D + "03 12:00"),
              S("d3", D + "04 08:00", D + "04 12:00"), S("d5", D + "06 08:00", D + "06 12:00")],
             R(run=3), out(True, {"d1": ["a"], "d2": ["a"], "d3": ["a"], "d5": ["a"]}, {"a": 960})),
        case("H33", "a forbidden pair listed in id order still blocks the later seat",
             [P("a"), P("b"), P("c")], [S("f", D + "02 08:00", D + "02 12:00", need=2)],
             R(pairs=[["a", "b"]]), out(True, {"f": ["a", "c"]}, {"a": 240, "b": 0, "c": 240})),
        # string order: "s10" < "s2" < "s9"
        case("H34", "ids compare as strings: s10 sorts before s2 and s9",
             [P("s9"), P("s10"), P("s2")], [S("f", D + "02 08:00", D + "02 12:00", need=2)],
             R(), out(True, {"f": ["s10", "s2"]}, {"s10": 240, "s2": 240, "s9": 0})),
    ]


# ── Random small rosters (expected outputs come from the reference) ─────────
ID_POOL = ["a", "b", "c", "s1", "s2", "s9", "s10", "Z", "ab", "B"]
SHIFT_IDS = ["d1", "d2", "d9", "d10", "e", "E", "n1", "n10", "m", "w"]
STARTS = ["00:00", "06:00", "07:30", "08:00", "14:00", "16:00", "18:00", "20:00", "22:00", "23:00"]
LENGTHS = [60, 120, 240, 240, 360, 360, 480, 480, 480, 600, 1440]
CAPS = [0, 480, 960, 1200, 1440, 2400, 2400, 2400, 2400, 2400]
BAD_DATES = ["2026-02-29", "2026-3-05", "2026-03-05 ", "", "2026/03/05", "2026-13-01"]


def stamp(minute):
    """Minutes since 2026-03-05 00:00 (a Thursday) -> 'YYYY-MM-DD HH:MM'."""
    d, rem = divmod(minute, 1440)
    return f"{(date(2026, 3, 5) + timedelta(days=d)).isoformat()} {rem // 60:02d}:{rem % 60:02d}"


def day_str(d):
    return (date(2026, 3, 5) + timedelta(days=d)).isoformat()


def comb(n, k):
    if k > n:
        return 0
    num = den = 1
    for i in range(k):
        num *= n - i
        den *= i + 1
    return num // den


def random_instance(r, k):
    """k: knobs for one family of small rosters."""
    ids = list(ID_POOL)
    for i in range(len(ids) - 1, 0, -1):
        j = r.below(i + 1)
        ids[i], ids[j] = ids[j], ids[i]
    staff = []
    for pid in ids[:4 + r.below(k["staff"] - 3)]:
        skills = ["x"] if k["single"] else (["x"] if r.chance(19, 20) else []) + (["y"] if r.chance(1, 2) else [])
        off = sorted({day_str(r.below(k["days"])) for _ in range(r.below(2) + r.below(2))})
        staff.append(P(pid, skills, r.pick(CAPS), off, r.chance(*k["senior"])))
    if k["messy"]:
        for _ in range(1 + r.below(2)):
            kind = r.below(6)
            victim = dict(r.pick(staff))
            if kind == 0:
                staff.insert(r.below(len(staff) + 1), victim)                  # duplicate id
            elif kind == 1:
                staff.append({**victim, "id": victim["id"] + "!", "max_minutes_week": True})
            elif kind == 2:
                staff.append({**victim, "id": victim["id"] + "!", "unavailable": [r.pick(BAD_DATES)]})
            elif kind == 3:
                staff.append({**victim, "id": victim["id"] + "!", "senior": 0})
            elif kind == 4:
                staff.append({**victim, "id": victim["id"] + "!", "skills": "x"})
            else:
                staff.append({k2: v for k2, v in victim.items() if k2 != "unavailable"})   # invalid copy
    sids = list(SHIFT_IDS)
    for i in range(len(sids) - 1, 0, -1):
        j = r.below(i + 1)
        sids[i], sids[j] = sids[j], sids[i]
    shifts = []
    for sid in sids[:1 + r.below(k["shifts"])]:
        if shifts and r.chance(1, 4):
            other = r.pick(shifts)
            if r.chance(1, 2):                         # same start (and maybe end) as an earlier shift
                start, end = other["start"], other["end"] if r.chance(1, 2) else None
            else:                                      # starts exactly when an earlier shift ends
                start, end = other["end"], None
        else:
            h, m = r.pick(STARTS).split(":")
            a = r.below(k["days"]) * 1440 + int(h) * 60 + int(m)
            length = r.pick(LENGTHS)
            if a % 1440 >= 960 and r.chance(1, 3):
                length = 1440 - a % 1440           # ends at exactly 00:00
            if r.chance(1, 8):
                length += r.pick([-1, 1])
            start, end = stamp(a), stamp(a + length)
        if end is None:
            d, hm = start.split(" ")
            mins = (date.fromisoformat(d) - date(2026, 3, 5)).days * 1440 + int(hm[:2]) * 60 + int(hm[3:])
            end = stamp(mins + r.pick(LENGTHS))
        skill = "y" if not k["single"] and r.chance(1, 5) else "x"
        have = sum(1 for p in staff if type(p) is dict and type(p.get("skills")) is list and skill in p["skills"])
        need = 1 + r.below(max(1, min(3, have - 1))) if r.chance(*k["multi"]) else 1
        shifts.append(S(sid, start, end, skill, need, r.chance(*k["needs_senior"])))
    if k["messy"]:
        for _ in range(1 + r.below(2)):
            kind = r.below(5)
            victim = dict(r.pick(shifts))
            if kind == 0:
                shifts.insert(r.below(len(shifts) + 1), victim)                # duplicate id
            elif kind == 1:
                shifts.append({**victim, "id": victim["id"] + "!", "need": r.pick([0, True, 2.0])})
            elif kind == 2:
                shifts.append({**victim, "id": victim["id"] + "!", "end": victim["start"]})
            elif kind == 3:
                shifts.append({**victim, "id": victim["id"] + "!", "start": victim["start"].replace(" ", "T")})
            else:
                shifts.append({**victim, "id": victim["id"] + "!", "needs_senior": "yes"})
    pool = [p["id"] for p in staff if type(p) is dict and type(p.get("id")) is str] + ["ghost"]
    pairs = [[r.pick(pool), r.pick(pool)] for _ in range(r.below(k["pairs"]))]
    rules = R(r.pick(k["rests"]), r.pick(k["runs"]), pairs)
    return staff, shifts, rules


def search_bound(staff, shifts):
    """Upper bound on the number of complete rosters the search tree can hold."""
    total = 1
    for s in shifts:
        if type(s) is not dict or type(s.get("need")) is not int or s["need"] < 1:
            continue
        c = sum(1 for p in staff if type(p) is dict and type(p.get("skills")) is list and s["skill"] in p["skills"])
        total *= max(1, comb(c, s["need"]))
    return total


# Seeds for the last family, picked by running the specified search over seeds 5000-8999 and keeping instances
# that end with ok true after at least two backtracks (so the backtracking path is exercised, not just failure).
BACKTRACK_SEEDS = [5027, 5029, 5031, 5060, 5121, 5157, 5164, 5191, 5193, 5204, 5218, 5234, 5241, 5261, 5291, 5317, 5325,
                   5368, 5384, 5395, 5452, 5460, 5502, 5530, 5546, 5553, 5650, 5710, 5770, 5781]
BASE = {"days": 6, "staff": 6, "shifts": 6, "messy": False, "single": False, "senior": (1, 2), "needs_senior": (1, 4),
        "multi": (1, 2), "pairs": 3, "rests": [0, 0, 120, 240, 480, 600], "runs": [1, 2, 2, 3, 3, 4, 7, 7, 7]}
FAMILIES = [
    ("random roster around a week boundary", 50, {}),
    ("random roster with malformed records", 20, {"days": 5, "staff": 5, "shifts": 5, "messy": True}),
    ("random roster, one skill, nine days", 15, {"days": 9, "staff": 5, "shifts": 8, "single": True}),
    ("random roster that succeeds only after backtracking", 30,
     {"days": 4, "staff": 7, "shifts": 6, "senior": (1, 3), "needs_senior": (1, 2), "multi": (2, 3), "pairs": 4,
      "rests": [240, 480, 600, 720], "runs": [2, 3, 4], "seeds": BACKTRACK_SEEDS}),
]


def random_cases():
    res = []
    seed = 1300
    n = 0
    for title, count, knobs in FAMILIES:
        k = {**BASE, **knobs}
        made = 0
        while made < count:
            if "seeds" in k:
                r = SplitMix(k["seeds"][made])
            else:
                seed += 1
                r = SplitMix(seed)
            staff, shifts, rules = random_instance(r, k)
            if search_bound(staff, shifts) > 20000:
                if "seeds" in k:
                    raise ValueError(f"seed {k['seeds'][made]} exceeds the search bound")
                continue
            n += 1
            made += 1
            res.append({"id": f"R{n:03d}", "title": title, "args": [staff, shifts, rules]})
    return res

def hidden():
    return hand() + random_cases()


# ── Stress ──────────────────────────────────────────────────────────────────
SKILLS = ["icu", "er", "ward", "lab", "xray", "theatre", "rehab", "triage"]
PATTERNS = [("E", "07:00", 0, "15:00"), ("L", "15:00", 0, "23:00"), ("N", "23:00", 1, "07:00")]


def stress():
    return [
        {"id": "S1", "title": "a year of three-shift rosters: 280 staff, 7644 shifts, 19054 slots", "seed": 1,
         "days": 364, "skills": 7, "per_skill": 40, "off": 10, "senior_pct": 30, "needs": [1, 2, 2, 3, 3, 4],
         "ns_pct": 40, "pairs": 80, "rest": 600, "maxrun": 5},
        {"id": "S2", "title": "a year, dense senior needs and forbidden pairs: 288 staff, 26206 slots", "seed": 2,
         "days": 364, "skills": 8, "per_skill": 36, "off": 20, "senior_pct": 30, "needs": [2, 3, 3, 4],
         "ns_pct": 60, "pairs": 300, "rest": 660, "maxrun": 4},
        {"id": "S3", "title": "1000 staff, half a year, long candidate lists: 9794 slots", "seed": 3,
         "days": 182, "skills": 4, "per_skill": 250, "off": 20, "senior_pct": 10, "needs": [3, 4, 5, 6],
         "ns_pct": 90, "pairs": 500, "rest": 660, "maxrun": 4},
    ]


def stress_args(case):
    r = SplitMix(case["seed"])
    days, k, per = case["days"], case["skills"], case["per_skill"]
    skills = SKILLS[:k]
    base = date(2027, 1, 4)                      # a Monday
    total = k * per
    perm = list(range(total))
    for i in range(total - 1, 0, -1):
        j = r.below(i + 1)
        perm[i], perm[j] = perm[j], perm[i]
    staff = []
    for idx in range(total):
        sk = [skills[idx % k]]
        if r.chance(1, 4):
            other = r.pick(skills)
            if other not in sk:
                sk.append(other)
        off = sorted({(base + timedelta(days=r.below(days))).isoformat() for _ in range(case["off"])})
        staff.append({"id": f"n{perm[idx]}", "skills": sk, "max_minutes_week": r.pick([1920, 2400, 2400, 2880]),
                      "unavailable": off, "senior": r.chance(case["senior_pct"], 100)})
    shifts = []
    for d in range(days):
        day = base + timedelta(days=d)
        for sk in skills:
            for tag, t0, plus, t1 in PATTERNS:
                shifts.append({"id": f"{sk}-{d}-{tag}", "start": f"{day.isoformat()} {t0}",
                               "end": f"{(day + timedelta(days=plus)).isoformat()} {t1}", "skill": sk,
                               "need": r.pick(case["needs"]), "needs_senior": r.chance(case["ns_pct"], 100)})
    for i in range(len(shifts) - 1, 0, -1):
        j = r.below(i + 1)
        shifts[i], shifts[j] = shifts[j], shifts[i]
    pairs = [[f"n{r.below(total)}", f"n{r.below(total)}"] for _ in range(case["pairs"])]
    rules = {"min_rest_minutes": case["rest"], "max_consecutive_days": case["maxrun"], "forbidden_pairs": pairs}
    return [staff, shifts, rules]
