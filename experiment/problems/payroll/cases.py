"""Cases for Problem 10. Stdlib only (copied into the sandbox like every cases.py).

Cases with "spec_expected" were worked out by hand from SPEC.md; the build fails if the reference disagrees.
"""


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


def literal_week(start, R, O, D, N, rp, op, dp, mp):
    """Expected week record with every pay figure written out by hand."""
    return {"week_start": start, "regular_minutes": R, "overtime_minutes": O, "double_minutes": D,
            "meal_penalties": N, "regular_pay": rp, "overtime_pay": op, "double_pay": dp, "meal_pay": mp,
            "total_pay": rp + op + dp + mp}


def case(cid, title, punches, rate, weeks=None, ignored=None):
    c = {"id": cid, "title": title, "args": [punches, rate]}
    if weeks is not None:
        c["spec_expected"] = {"weeks": weeks, "ignored": ignored}
    return c


def day(d, a, b, d2=None):
    return [f"2026-03-{d:02d} {a}", f"2026-03-{(d2 or d):02d} {b}"]


def public():
    return [
        case("P1", "rounding, daily overtime, meal penalty", [["2026-03-02 08:07", "2026-03-02 18:08"]], 2000,
             [literal_week("2026-03-02", 480, 135, 0, 1, 16000, 6750, 0, 2000)], []),
        case("P2", "midnight shift, overlap, invalid, empty",
             [["2026-03-08 22:00", "2026-03-09 03:00"], ["2026-03-09 02:00", "2026-03-09 06:00"],
              ["2026-03-09 25:00", "2026-03-09 26:00"], ["2026-03-09 09:00", "2026-03-09 09:05"]], 1500,
             [literal_week("2026-03-02", 300, 0, 0, 0, 7500, 0, 0, 0)], [1, 2, 3]),
        case("P3", "weekly overtime", [day(d, "09:00", "18:00") for d in range(2, 7)] + [day(7, "09:00", "15:00")],
             1000, [literal_week("2026-03-02", 2400, 660, 0, 6, 40000, 16500, 0, 6000)], []),
        case("P4", "seventh day", [day(d, "09:00", "13:00") for d in range(2, 8)] + [day(8, "08:00", "18:00")], 1200,
             [literal_week("2026-03-02", 1440, 480, 120, 1, 28800, 14400, 4800, 1200)], []),
    ]


def hand():
    return [
        case("H01", "7-minute rule at both boundaries",
             [day(2, "09:07", "09:52"), day(2, "10:08", "10:38"), day(2, "11:22", "11:23")], 600,
             [literal_week("2026-03-02", 90, 0, 0, 0, 900, 0, 0, 0)], []),
        case("H02", "rounding moves a start into the next day and the next week",
             [day(2, "23:53", "02:00", 3), day(8, "23:55", "00:20", 9)], 600,
             [literal_week("2026-03-02", 120, 0, 0, 0, 1200, 0, 0, 0),
              literal_week("2026-03-09", 15, 0, 0, 0, 150, 0, 0, 0)], []),
        case("H03", "invalid timestamps",
             [["2026-02-29 09:00", "2026-02-29 10:00"], ["2026-3-02 09:00", "2026-03-02 10:00"],
              ["2026-03-02T09:00", "2026-03-02 10:00"], ["2026-03-02 09:00", "2026-03-02 09:00"],
              ["2026-03-02 10:00", "2026-03-02 09:00"], ["\uff12026-03-02 09:00", "2026-03-02 10:00"],
              ["2026-03-02 09:60", "2026-03-02 10:00"], ["2028-02-29 09:00", "2028-02-29 10:00"]], 600,
             [literal_week("2028-02-28", 60, 0, 0, 0, 600, 0, 0, 0)], [0, 1, 2, 3, 4, 5, 6]),
        case("H04", "overlaps are dropped, not merged; touching is fine",
             [day(2, "09:00", "12:00"), day(2, "11:00", "13:00"), day(2, "12:05", "14:00"), day(2, "13:00", "13:30"),
              day(2, "15:01", "15:07")], 600,
             [literal_week("2026-03-02", 300, 0, 0, 0, 3000, 0, 0, 0)], [1, 3, 4]),
        case("H05", "sorting ties: duplicates and equal starts (shorter end first)",
             [day(3, "09:00", "10:00"), day(3, "09:00", "10:00"), day(2, "09:00", "09:30"), day(4, "09:00", "11:00"),
              day(4, "09:00", "09:30")], 600,
             [literal_week("2026-03-02", 120, 0, 0, 0, 1200, 0, 0, 0)], [1, 3]),
        case("H06", "double time after 12 hours", [day(3, "06:00", "20:00")], 1001,
             [literal_week("2026-03-02", 480, 240, 120, 1, 8008, 6006, 4004, 1001)], []),
        case("H07", "pay rounded once per week, not per day", [day(2, "09:00", "09:15"), day(3, "09:00", "09:15")], 1001,
             [literal_week("2026-03-02", 30, 0, 0, 0, 501, 0, 0, 0)], []),
        case("H08", "overtime pay rounds half up", [day(2, "09:00", "17:15")], 1004,
             [literal_week("2026-03-02", 480, 15, 0, 1, 8032, 377, 0, 1004)], []),
        case("H09", "weekly cap after daily overtime and a split day",
             [day(d, "08:00", "18:00") for d in range(2, 6)] + [day(6, "08:00", "12:00"), day(6, "12:30", "16:30"),
                                                               day(7, "10:00", "12:00")], 600,
             [literal_week("2026-03-02", 2400, 600, 0, 4, 24000, 9000, 0, 2400)], []),
        case("H10", "no seventh-day rule with a day off",
             [day(d, "09:00", "13:00") for d in (2, 3, 5, 6, 7)] + [day(8, "08:00", "18:00")], 1200,
             [literal_week("2026-03-02", 1680, 120, 0, 1, 33600, 3600, 0, 1200)], []),
        case("H11", "seventh day after the weekly cap",
             [day(d, "08:00", "17:00") for d in range(2, 8)] + [day(8, "09:00", "12:00")], 600,
             [literal_week("2026-03-02", 2400, 1020, 0, 6, 24000, 15300, 0, 3600)], []),
        case("H12", "Sunday night shift into Monday stays in Sunday's week", [day(8, "18:00", "08:00", 9)], 600,
             [literal_week("2026-03-02", 480, 240, 120, 1, 4800, 3600, 2400, 600)], []),
        case("H13", "no punches", [], 600, [], []),
        case("H14", "meal penalty needs one shift over 300 minutes",
             [day(2, "09:00", "14:00"), day(3, "09:00", "14:15"), day(4, "08:00", "12:40"), day(4, "13:00", "17:40")],
             600, [literal_week("2026-03-02", 1095, 90, 0, 1, 10950, 1350, 0, 600)], []),
        case("H15", "weeks sorted; a week with only ignored punches is not listed",
             [day(16, "09:00", "10:00"), day(2, "09:00", "09:30"), day(9, "09:00", "09:00")], 600,
             [literal_week("2026-03-02", 30, 0, 0, 0, 300, 0, 0, 0),
              literal_week("2026-03-16", 60, 0, 0, 0, 600, 0, 0, 0)], [2]),
        case("H16", "seven consecutive days across two weeks is not a seventh day",
             [day(d, "09:00", "10:00") for d in range(4, 11)], 600,
             [literal_week("2026-03-02", 300, 0, 0, 0, 3000, 0, 0, 0),
              literal_week("2026-03-09", 120, 0, 0, 0, 1200, 0, 0, 0)], []),
        case("H17", "a day with two long shifts earns one penalty",
             [day(2, "00:00", "06:00"), day(2, "12:00", "18:00")], 600,
             [literal_week("2026-03-02", 480, 240, 0, 1, 4800, 3600, 0, 600)], []),
        case("H18", "seventh day: short week, long Sunday",
             [day(d, "09:00", "10:00") for d in range(2, 8)] + [day(8, "08:00", "17:00")], 600,
             [literal_week("2026-03-02", 360, 480, 60, 1, 3600, 7200, 1200, 600)], []),
    ]


# ── Random timesheets ───────────────────────────────────────────────────────
RATES = [600, 1000, 1001, 1004, 1337, 2000, 4999]
BAD = ["2026-02-30 09:00", "2026-03-02 24:00", "2026-03-02 9:00", "2026-03-02  09:00", "", "2026/03/02 09:00",
       "2026-13-01 09:00", "2026-03-02 09:5a"]


def fmt(minute_of_epoch):
    """Minutes since 2026-03-01 00:00 (a Sunday) -> timestamp string (March/April 2026 only)."""
    d, rem = divmod(minute_of_epoch, 1440)
    month, dom = (3, 1 + d) if d < 31 else (4, d - 30)
    return f"2026-{month:02d}-{dom:02d} {rem // 60:02d}:{rem % 60:02d}"


def random_punches(r, n_days, density):
    punches = []
    for d in range(n_days):
        if not r.chance(density, 10):
            continue
        start = d * 1440 + r.pick([0, 360, 420, 480, 540, 600, 780, 1080, 1320, 1400]) + r.below(15)
        for _ in range(1 + r.below(2)):
            length = r.pick([5, 30, 120, 240, 299, 301, 315, 420, 480, 495, 540, 600, 720, 735, 840])
            length += r.below(15) - 7
            if length < 1:
                length = 1
            punches.append([fmt(start), fmt(start + length)])
            start += length + r.pick([-60, 0, 7, 15, 30, 45, 60])
            if start < 0:
                start = 0
    if r.chance(1, 3):
        i = r.below(len(punches) + 1)
        punches.insert(i, [r.pick(BAD), fmt(r.below(n_days * 1440))])
    if punches and r.chance(1, 4):
        punches.append(list(r.pick(punches)))
    # shuffle (Fisher-Yates with the version-independent PRNG)
    for i in range(len(punches) - 1, 0, -1):
        j = r.below(i + 1)
        punches[i], punches[j] = punches[j], punches[i]
    return punches


def random_cases():
    res = []
    for i in range(100):
        r = SplitMix(88000 + i)
        n_days = r.pick([3, 7, 9, 15, 22])
        res.append({"id": f"R{i + 1:03d}", "title": "random timesheet",
                    "args": [random_punches(r, n_days, r.pick([5, 8, 10])), r.pick(RATES)]})
    return res


def hidden():
    return hand() + random_cases()


def stress():
    return []


def stress_args(case):
    raise ValueError("Problem 10 has no stress cases")
