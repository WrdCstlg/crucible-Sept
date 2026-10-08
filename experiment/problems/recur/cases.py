"""Cases for Problem 15. Stdlib only (copied into the sandbox like every cases.py).

Cases with "spec_expected" were worked out by hand from SPEC.md; the build fails if the reference disagrees.
Weekday anchors used in the derivations: 0001-01-01 Mon, 1997-08-05 Tue, 2024-01-01 Mon, 2026-01-01 Thu,
2026-03-01 Sun, 2026 month starts: Feb Sun, Mar Sun, Apr Wed, May Fri, Jun Mon, Jul Wed, Aug Sat, Sep Tue, Oct Thu,
Nov Sun, Dec Tue; 2027-01-01 Fri, 2029-01-01 Mon; 9999-12-31 Fri.
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


def ev(start, rule=None, exdates=(), rdates=()):
    return {"start": start, "rule": rule, "exdates": list(exdates), "rdates": list(rdates)}


def case(cid, title, event, lo, hi, expected=None):
    c = {"id": cid, "title": title, "args": [event, lo, hi]}
    if expected is not None:
        c["spec_expected"] = expected
    return c


def ok(*items):
    return {"ok": True, "occurrences": list(items)}


BAD_RULE = {"ok": False, "error": "bad_rule"}
BAD_DT = {"ok": False, "error": "bad_datetime"}
MAR_LO, MAR_HI = "2026-03-01T00:00", "2026-04-01T00:00"
Y26_LO, Y26_HI = "2026-01-01T00:00", "2027-01-01T00:00"


def public():
    return [
        case("P1", "BYSETPOS picks the last weekday of each month",
             ev("2026-01-30T09:00", "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1;COUNT=4"), Y26_LO, Y26_HI,
             ok("2026-01-30T09:00", "2026-02-27T09:00", "2026-03-31T09:00", "2026-04-30T09:00")),
        case("P2", "WKST decides which days share a week; INTERVAL=2",
             ev("1997-08-05T09:00", "FREQ=WEEKLY;INTERVAL=2;COUNT=4;BYDAY=TU,SU;WKST=SU"),
             "1997-01-01T00:00", "1998-01-01T00:00",
             ok("1997-08-05T09:00", "1997-08-17T09:00", "1997-08-19T09:00", "1997-08-31T09:00")),
        case("P3", "day 31 skipped in short months; UNTIL inclusive; exdate and rdate",
             ev("2026-01-31T08:00", "FREQ=MONTHLY;UNTIL=2026-07-31T08:00", ["2026-05-31T08:00"],
                ["2026-02-28T08:00"]), "2026-02-01T00:00", "2026-08-01T00:00",
             ok("2026-02-28T08:00", "2026-03-31T08:00", "2026-07-31T08:00")),
        case("P4", "an ordinal is not allowed with WEEKLY",
             ev("2026-01-05T10:00", "FREQ=WEEKLY;BYDAY=1MO"), "2026-01-01T00:00", "2026-02-01T00:00", BAD_RULE),
    ]


def hand():
    feb29_1896 = [f"{y}-02-29T12:00" for y in range(1896, 2005, 4) if y != 1900]   # 1900 is not a leap year
    return [
        # start Wed Mar 4; week Mar 2-8: Mon Mar 2 is before the start; then Mon Mar 9, Mon Mar 16 -> COUNT 3
        case("H01", "the start is the first occurrence even when it does not match the rule",
             ev("2026-03-04T18:30", "FREQ=WEEKLY;BYDAY=MO;COUNT=3"), MAR_LO, MAR_HI,
             ok("2026-03-04T18:30", "2026-03-09T18:30", "2026-03-16T18:30")),
        # series Mar 2,3,4,5 (COUNT 4, start included); remove Mar 2 and Mar 4; 08:00 matches nothing
        case("H02", "COUNT is applied before EXDATE removal; an excluded start still counts",
             ev("2026-03-02T07:00", "FREQ=DAILY;COUNT=4", ["2026-03-02T07:00", "2026-03-04T07:00",
                                                           "2026-03-05T08:00"]), MAR_LO, MAR_HI,
             ok("2026-03-03T07:00", "2026-03-05T07:00")),
        # series Mar 10, 12, 14; rdates add Mar 1 (before the start), Mar 12 (duplicate), Mar 20 (not counted)
        case("H03", "RDATEs are added, deduplicated, not counted, and may precede the start",
             ev("2026-03-10T09:00", "FREQ=DAILY;INTERVAL=2;COUNT=3", [],
                ["2026-03-12T09:00", "2026-03-01T09:00", "2026-03-20T09:00", "2026-03-12T09:00"]),
             "2026-03-01T00:00", "2026-03-31T00:00",
             ok("2026-03-01T09:00", "2026-03-10T09:00", "2026-03-12T09:00", "2026-03-14T09:00",
                "2026-03-20T09:00")),
        case("H04", "UNTIL is inclusive",
             ev("2026-03-02T10:00", "FREQ=DAILY;UNTIL=2026-03-05T10:00"), MAR_LO, MAR_HI,
             ok("2026-03-02T10:00", "2026-03-03T10:00", "2026-03-04T10:00", "2026-03-05T10:00")),
        case("H05", "UNTIL compares the time too: one minute early excludes that day",
             ev("2026-03-02T10:00", "FREQ=DAILY;UNTIL=2026-03-05T09:59"), MAR_LO, MAR_HI,
             ok("2026-03-02T10:00", "2026-03-03T10:00", "2026-03-04T10:00")),
        case("H06", "a start later than UNTIL is still an occurrence",
             ev("2026-03-10T10:00", "FREQ=DAILY;UNTIL=2026-03-01T00:00"), MAR_LO, MAR_HI,
             ok("2026-03-10T10:00")),
        # day 31 exists in Jan, Mar, May, Jul, Aug
        case("H07", "MONTHLY from the 31st skips short months instead of clamping",
             ev("2026-01-31T08:00", "FREQ=MONTHLY;COUNT=5"), Y26_LO, Y26_HI,
             ok("2026-01-31T08:00", "2026-03-31T08:00", "2026-05-31T08:00", "2026-07-31T08:00",
                "2026-08-31T08:00")),
        case("H08", "YEARLY from Feb 29: leap years only (1900 is not one, 2000 is)",
             ev("1896-02-29T12:00", "FREQ=YEARLY;INTERVAL=4"), "1890-01-01T00:00", "2005-01-01T00:00",
             ok(*feb29_1896)),
        # first Monday of 2026 is Jan 5 (day 5); +19 weeks = day 138 = May 18. 2027: Jan 4 (day 4) + 133 = day 137 =
        # May 17. The start Jan 1 2026 (a Thursday) is entry 1.
        case("H09", "YEARLY ordinal BYDAY without BYMONTH counts within the year",
             ev("2026-01-01T09:00", "FREQ=YEARLY;BYDAY=20MO;COUNT=3"), Y26_LO, "2030-01-01T00:00",
             ok("2026-01-01T09:00", "2026-05-18T09:00", "2027-05-17T09:00")),
        # March 2026: Sundays 1, 8 -> 2SU = Mar 8; Mar 31 is Tue -> -1MO = Mar 30. November: Nov 1 Sun -> Nov 8;
        # Nov 30 is Mon.
        case("H10", "YEARLY ordinal BYDAY with BYMONTH counts within each month",
             ev("2026-01-01T09:00", "FREQ=YEARLY;BYMONTH=3,11;BYDAY=2SU,-1MO;COUNT=5"), Y26_LO, Y26_HI,
             ok("2026-01-01T09:00", "2026-03-08T09:00", "2026-03-30T09:00", "2026-11-08T09:00",
                "2026-11-30T09:00")),
        # weeks Thu-Wed: period 0 = Feb 26 - Mar 4 (Feb 26, Mar 2 before the start; Mar 4 is the start),
        # period 2 = Mar 12-18 (Thu 12, Mon 16, Wed 18), period 4 = Mar 26 - Apr 1 (Thu 26, Mon 30, ...)
        case("H11", "WKST=TH with INTERVAL=2 changes which days share a week",
             ev("2026-03-04T12:00", "FREQ=WEEKLY;INTERVAL=2;WKST=TH;BYDAY=MO,WE,TH;COUNT=6"), MAR_LO,
             "2026-05-01T00:00",
             ok("2026-03-04T12:00", "2026-03-12T12:00", "2026-03-16T12:00", "2026-03-18T12:00",
                "2026-03-26T12:00", "2026-03-30T12:00")),
        # March: positions 1,2 = Mar 2, Mar 3, both before the start. April: Apr 1 (Wed), Apr 2. May: May 1 (Fri), May 4
        case("H12", "BYSETPOS counts candidates that lie before the start",
             ev("2026-03-04T09:00", "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=1,2;COUNT=5"), MAR_LO,
             "2026-06-01T00:00",
             ok("2026-03-04T09:00", "2026-04-01T09:00", "2026-04-02T09:00", "2026-05-01T09:00",
                "2026-05-04T09:00")),
        # March's last weekday is Tue Mar 31, after UNTIL, so March gives nothing (not Fri Mar 20)
        case("H13", "BYSETPOS is applied before UNTIL",
             ev("2026-01-30T09:00", "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1;UNTIL=2026-03-20T09:00"),
             Y26_LO, Y26_HI, ok("2026-01-30T09:00", "2026-02-27T09:00")),
        case("H14", "DAILY periods hold one candidate: BYSETPOS=2 selects nothing",
             ev("2026-03-02T08:00", "FREQ=DAILY;BYDAY=MO,WE;BYSETPOS=2"), MAR_LO, "2026-03-15T00:00",
             ok("2026-03-02T08:00")),
        # Jan: -31 = Jan 1 (the start), -1 = Jan 31; Feb: Feb 28 only; Mar: Mar 1, Mar 31; Apr: Apr 30
        case("H15", "negative BYMONTHDAY counts back from each month's end; -31 needs a 31-day month",
             ev("2026-01-01T00:00", "FREQ=MONTHLY;BYMONTHDAY=-1,-31;COUNT=6"), Y26_LO, Y26_HI,
             ok("2026-01-01T00:00", "2026-01-31T00:00", "2026-02-28T00:00", "2026-03-01T00:00",
                "2026-03-31T00:00", "2026-04-30T00:00")),
        # Fridays the 13th in 2026: Feb, Mar, Nov
        case("H16", "MONTHLY BYMONTHDAY and BYDAY intersect",
             ev("2026-01-01T20:00", "FREQ=MONTHLY;BYMONTHDAY=13;BYDAY=FR;COUNT=4"), Y26_LO, Y26_HI,
             ok("2026-01-01T20:00", "2026-02-13T20:00", "2026-03-13T20:00", "2026-11-13T20:00")),
        case("H17", "YEARLY with BYMONTHDAY but no BYMONTH covers every month",
             ev("2026-01-15T10:00", "FREQ=YEARLY;BYMONTHDAY=15;COUNT=4"), Y26_LO, "2030-01-01T00:00",
             ok("2026-01-15T10:00", "2026-02-15T10:00", "2026-03-15T10:00", "2026-04-15T10:00")),
        # BYMONTHDAY defaults to 30: no Feb 30 ever
        case("H18", "YEARLY with BYMONTH only uses the start's day of month",
             ev("2026-01-30T10:00", "FREQ=YEARLY;BYMONTH=2,3;COUNT=4"), Y26_LO, "2030-01-01T00:00",
             ok("2026-01-30T10:00", "2026-03-30T10:00", "2027-03-30T10:00", "2028-03-30T10:00")),
        case("H19", "the range includes its start and excludes its end",
             ev("2026-03-02T10:00", "FREQ=DAILY;COUNT=5"), "2026-03-03T10:00", "2026-03-05T10:00",
             ok("2026-03-03T10:00", "2026-03-04T10:00")),
        case("H20", "range_end before range_start gives an empty list",
             ev("2026-03-02T10:00", "FREQ=DAILY;COUNT=5"), "2026-03-05T10:00", "2026-03-03T10:00", ok()),
        case("H21", "the series ends with year 9999 even if COUNT is not reached",
             ev("9995-06-15T12:00", "FREQ=YEARLY;COUNT=10"), "9990-01-01T00:00", "9999-12-31T23:59",
             ok("9995-06-15T12:00", "9996-06-15T12:00", "9997-06-15T12:00", "9998-06-15T12:00",
                "9999-06-15T12:00")),
        # weeks Mon-Sun: Nov 29 - Dec 5 -> last of (Mon 29, Fri 3, Sun 5) = Dec 5, ... last week Dec 27 - Jan 2
        # holds only Mon 27 and Fri 31 (10000-01-02 does not exist) -> Dec 31
        case("H22", "the last week of the calendar has only its existing days",
             ev("9999-12-01T07:00", "FREQ=WEEKLY;BYDAY=MO,FR,SU;BYSETPOS=-1"), "9999-12-01T00:00",
             "9999-12-31T23:59",
             ok("9999-12-01T07:00", "9999-12-05T07:00", "9999-12-12T07:00", "9999-12-19T07:00",
                "9999-12-26T07:00", "9999-12-31T07:00")),
        # week 0 (Sun 0000-12-31 does not exist): Mon 1, Tue 2, Wed 3 -> 2nd = Jan 2. Week 1: Sun 7, Mon 8 -> Jan 8.
        # Week 2: Sun 14, Mon 15 -> Jan 15
        case("H23", "the first week of the calendar has only its existing days",
             ev("0001-01-01T10:00", "FREQ=WEEKLY;WKST=SU;BYDAY=SU,MO,TU,WE;BYSETPOS=2;COUNT=4"),
             "0001-01-01T00:00", "0001-02-01T00:00",
             ok("0001-01-01T10:00", "0001-01-02T10:00", "0001-01-08T10:00", "0001-01-15T10:00")),
        # used years are 2024 + 7k; in [9000, 9100) these are 9003, 9010, ..., 9094; leap among them: 9024, 9052, 9080
        case("H24", "a range thousands of years after the start (YEARLY, INTERVAL=7, Feb 29)",
             ev("2024-02-29T06:00", "FREQ=YEARLY;INTERVAL=7"), "9000-01-01T00:00", "9100-01-01T00:00",
             ok("9024-02-29T06:00", "9052-02-29T06:00", "9080-02-29T06:00")),
        # month index 2026*12+0 = 24312; 4000*12+0 = 48000; 48000-24312 = 23688 = 3 mod 5, so used months of 4000 are
        # index 48002 (March) and 48007 (August); both have a 31st
        case("H25", "a range thousands of years after the start (MONTHLY, INTERVAL=5, day 31)",
             ev("2026-01-31T08:00", "FREQ=MONTHLY;INTERVAL=5"), "4000-01-01T00:00", "4001-01-01T00:00",
             ok("4000-03-31T08:00", "4000-08-31T08:00")),
        case("H26", "an EXDATE removes an RDATE too and must match the time exactly",
             ev("2026-03-02T09:00", None, ["2026-03-03T09:00", "2026-03-02T09:01"],
                ["2026-03-03T09:00", "2026-03-04T09:00"]), MAR_LO, MAR_HI,
             ok("2026-03-02T09:00", "2026-03-04T09:00")),
        # Mondays: Jan 5,12,19,26; Feb 2..23; Mar 2..30 (5th = Mar 30); Apr 6..27; May 4..25; Jun 1..29 (5th = Jun 29)
        case("H27", "MONTHLY BYDAY=5MO only in months with five Mondays",
             ev("2026-01-05T10:00", "FREQ=MONTHLY;BYDAY=5MO;COUNT=3"), Y26_LO, Y26_HI,
             ok("2026-01-05T10:00", "2026-03-30T10:00", "2026-06-29T10:00")),
        # used weeks: Mar 16-22 (all March), Mar 30 - Apr 5 (Mon Mar 30 is March; Thu Apr 2, Sat Apr 4), Apr 13-19
        case("H28", "WEEKLY BYMONTH filters each day of a week that straddles two months",
             ev("2026-03-16T10:00", "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,TH,SA;BYMONTH=4;COUNT=4"), MAR_LO,
             "2026-06-01T00:00",
             ok("2026-03-16T10:00", "2026-04-02T10:00", "2026-04-04T10:00", "2026-04-13T10:00")),
        # used days: Jan 30, Feb 2, 5, ..., 26, Mar 1, 4, ..., 31, Apr 3; days 1-3 of a month among them: Feb 2, Mar 1, Apr 3
        case("H29", "DAILY INTERVAL counts days from the start; BYMONTHDAY filters",
             ev("2026-01-30T06:00", "FREQ=DAILY;INTERVAL=3;BYMONTHDAY=1,2,3;COUNT=4"), Y26_LO, Y26_HI,
             ok("2026-01-30T06:00", "2026-02-02T06:00", "2026-03-01T06:00", "2026-04-03T06:00")),
        case("H30", "BYSETPOS: overlapping positions select once, positions past the end select nothing",
             ev("2026-03-02T10:00", "FREQ=MONTHLY;BYMONTHDAY=2;BYSETPOS=1,-1,5;COUNT=3"), MAR_LO, "2026-06-01T00:00",
             ok("2026-03-02T10:00", "2026-04-02T10:00", "2026-05-02T10:00")),
        # 53 Mondays only in 2024 (leap, starts Mon) and 2029 (starts Mon); -53MO of 2024 is the start itself
        case("H31", "YEARLY 53MO and -53MO exist only in years with 53 Mondays",
             ev("2024-01-01T09:00", "FREQ=YEARLY;BYDAY=53MO,-53MO;COUNT=4"), "2024-01-01T00:00",
             "2030-01-01T00:00",
             ok("2024-01-01T09:00", "2024-12-30T09:00", "2029-01-01T09:00", "2029-12-31T09:00")),
        # Dec 20 2026 is a Sunday; Tuesdays Dec 22, Dec 29; 2027-01-05
        case("H32", "YEARLY with a bare BYDAY and no BYMONTH means every such weekday of the year",
             ev("2026-12-20T10:00", "FREQ=YEARLY;BYDAY=TU;COUNT=4"), Y26_LO, "2028-01-01T00:00",
             ok("2026-12-20T10:00", "2026-12-22T10:00", "2026-12-29T10:00", "2027-01-05T10:00")),
        # weeks Wed-Tue: Feb 25 - Mar 3 (Fri Feb 27 first, before the start), Mar 4-10 (Fri 6 first), Mar 11-17 (Fri 13)
        case("H33", "WKST changes what BYSETPOS counts even with INTERVAL=1",
             ev("2026-03-02T10:00", "FREQ=WEEKLY;WKST=WE;BYDAY=MO,FR;BYSETPOS=1;COUNT=3"), MAR_LO, MAR_HI,
             ok("2026-03-02T10:00", "2026-03-06T10:00", "2026-03-13T10:00")),
        case("H34", "COUNT=1 keeps only the start; RDATEs are still added",
             ev("2026-03-02T10:00", "FREQ=DAILY;COUNT=1", [], ["2026-03-05T10:00"]), MAR_LO, MAR_HI,
             ok("2026-03-02T10:00", "2026-03-05T10:00")),
        # second Tuesdays: Jan 13 (the start), Feb 10, Mar 10; '+' signs are valid
        case("H35", "explicit + signs; an ordinal BYDAY limits BYMONTHDAY in MONTHLY",
             ev("2026-01-13T18:00", "FREQ=MONTHLY;BYDAY=+2TU;BYMONTHDAY=+8,+9,+10,+11,+12,+13,+14;COUNT=3"),
             Y26_LO, Y26_HI, ok("2026-01-13T18:00", "2026-02-10T18:00", "2026-03-10T18:00")),
        # the first Monday of a year is a 1st only when Jan 1 is a Monday: 2029, then 2035 (2030 Tue, 2031 Wed,
        # 2032 Thu, 2033 Sat, 2034 Sun, 2035 Mon). Counting in months instead would give Jun 1 2026.
        case("H36", "YEARLY ordinal BYDAY limiting BYMONTHDAY counts in the year without BYMONTH",
             ev("2026-01-01T09:00", "FREQ=YEARLY;BYMONTHDAY=1;BYDAY=1MO;COUNT=3"), Y26_LO, "2040-01-01T00:00",
             ok("2026-01-01T09:00", "2029-01-01T09:00", "2035-01-01T09:00")),
        case("H37", "bad_datetime is checked before bad_rule",
             ev("2026-03-02T10:00", "FREQ=DAILY;COUNT=0", ["2026-02-29T10:00"]), MAR_LO, MAR_HI, BAD_DT),
        case("H38", "datetime digits must be ASCII", ev("2026-03-02T10:00", "FREQ=DAILY;COUNT=2"), MAR_LO,
             "２026-04-01T00:00", BAD_DT),
        case("H39", "datetime separator T is case-sensitive",
             ev("2026-03-02T10:00", "FREQ=DAILY;COUNT=2", [], ["2026-03-05t10:00"]), MAR_LO, MAR_HI, BAD_DT),
        case("H40", "year 0000 is not a datetime", ev("0000-12-31T10:00", None), MAR_LO, MAR_HI, BAD_DT),
        case("H41", "hour 24 is not a datetime", ev("2026-03-02T10:00", None, ["2026-03-02T24:00"]), MAR_LO,
             MAR_HI, BAD_DT),
        case("H42", "BYSETPOS is fine with any BY part written (DAILY, BYMONTH)",
             ev("2026-03-02T10:00", "FREQ=DAILY;BYSETPOS=1;BYMONTH=3;COUNT=2"), MAR_LO, MAR_HI,
             ok("2026-03-02T10:00", "2026-03-03T10:00")),
        # default BYDAY=MO; week Sun Mar 1 - Sat Mar 7 holds Mon Mar 2 only (the start); next Mon Mar 9
        case("H43", "WEEKLY BYSETPOS with BYMONTH written and the default weekday",
             ev("2026-03-02T10:00", "FREQ=WEEKLY;WKST=SU;BYMONTH=3;BYSETPOS=-1;COUNT=2"), MAR_LO, MAR_HI,
             ok("2026-03-02T10:00", "2026-03-09T10:00")),
        case("H44", "DAILY BYMONTHDAY=+31: the non-matching start, then Mar 31",
             ev("2026-03-02T10:00", "FREQ=DAILY;BYMONTHDAY=+31;COUNT=2"), MAR_LO, MAR_HI,
             ok("2026-03-02T10:00", "2026-03-31T10:00")),
        case("H45", "INTERVAL=100000 is valid (only the start in range)",
             ev("2026-03-02T10:00", "FREQ=YEARLY;INTERVAL=100000"), MAR_LO, MAR_HI, ok("2026-03-02T10:00")),
        case("H46", "no rule: the start outside the range, an RDATE inside it",
             ev("2026-02-27T10:00", None, [], ["2026-03-03T10:00"]), MAR_LO, MAR_HI, ok("2026-03-03T10:00")),
        # COUNT=3 ends on Mar 4; nothing is left in a range a year later
        case("H47", "COUNT exhausted before a later range",
             ev("2026-03-02T10:00", "FREQ=DAILY;COUNT=3"), "2027-03-01T00:00", "2027-04-01T00:00", ok()),
    ] + rule_validation()


def rule_validation():
    bad = [
        ("V01", "leading zero in INTERVAL", "FREQ=DAILY;INTERVAL=02"),
        ("V02", "a part repeated", "FREQ=DAILY;COUNT=3;FREQ=DAILY"),
        ("V03", "COUNT together with UNTIL", "FREQ=DAILY;COUNT=3;UNTIL=2026-03-10T00:00"),
        ("V04", "ordinal 0", "FREQ=MONTHLY;BYDAY=0MO"),
        ("V05", "BYSETPOS without another BY part", "FREQ=MONTHLY;BYSETPOS=1"),
        ("V06", "BYMONTHDAY with WEEKLY", "FREQ=WEEKLY;BYMONTHDAY=1"),
        ("V07", "ordinal with DAILY", "FREQ=DAILY;BYDAY=-1FR"),
        ("V08", "trailing semicolon", "FREQ=DAILY;"),
        ("V09", "UNTIL is not a real date", "FREQ=DAILY;UNTIL=2026-02-30T00:00"),
        ("V10", "unsupported part", "FREQ=DAILY;BYHOUR=9"),
        ("V11", "FREQ missing", "COUNT=2"),
        ("V12", "ordinal 54", "FREQ=YEARLY;BYDAY=54MO"),
        ("V13", "BYMONTHDAY -0", "FREQ=MONTHLY;BYMONTHDAY=-0"),
        ("V14", "empty list item", "FREQ=MONTHLY;BYDAY=MO,,TU"),
        ("V15", "lower-case keyword", "FREQ=DAILY;WKST=mo"),
        ("V16", "sign on an unsigned value", "FREQ=DAILY;COUNT=+3"),
        ("V17", "empty rule", ""),
        ("V18", "trailing space", "FREQ=DAILY;COUNT=3 "),
        ("V19", "INTERVAL above 100000", "FREQ=DAILY;INTERVAL=100001"),
        ("V20", "BYMONTHDAY 32", "FREQ=MONTHLY;BYMONTH=1;BYSETPOS=1;BYMONTHDAY=32"),
        ("V21", "two '=' in a part", "FREQ=DAILY;COUNT==3"),
        ("V22", "unsupported FREQ", "FREQ=HOURLY"),
        ("V23", "sign without digits in BYDAY", "FREQ=MONTHLY;BYDAY=+MO"),
        ("V24", "ordinal with WEEKLY even when written +1", "FREQ=WEEKLY;BYDAY=+1MO,TU"),
        ("V25", "COUNT with UNTIL, in any order", "UNTIL=2026-03-03T10:00;FREQ=DAILY;COUNT=1"),
    ]
    return [case(cid, f"invalid rule: {title}", ev("2026-03-02T10:00", rule), MAR_LO, MAR_HI, BAD_RULE)
            for cid, title, rule in bad]


# ── Generated cases ─────────────────────────────────────────────────────────
MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
WD = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def mlen(y, m):
    return 29 if m == 2 and leap(y) else MONTH_DAYS[m - 1]


def dt(y, mo, d, h, mi):
    return f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}"


def add_days(y, mo, d, n):
    """Calendar arithmetic without datetime (kept simple: steps one month at a time)."""
    while n > 0:
        left = mlen(y, mo) - d
        if n <= left:
            return y, mo, d + n
        n -= left + 1
        y, mo, d = (y + 1, 1, 1) if mo == 12 else (y, mo + 1, 1)
    while n < 0:
        if -n < d:
            return y, mo, d + n
        n += d
        y, mo = (y - 1, 12) if mo == 1 else (y, mo - 1)
        d = mlen(y, mo)
    return y, mo, d


def clamp_year(y):
    return max(1, min(9999, y))


def sub(r, k, pool):
    """k distinct items of pool in pool order (deterministic)."""
    idx = sorted({r.below(len(pool)) for _ in range(k)})
    return [pool[i] for i in idx]


def byday_list(r, ordinals):
    items = []
    for _ in range(1 + r.below(3)):
        code = r.pick(WD)
        if ordinals and r.chance(2, 3):
            items.append(f"{r.pick(ordinals)}{code}")
        else:
            items.append(code)
    return ",".join(items)


def random_rule(r, freq, sy, smo, sd, sh, smi):
    parts = [f"FREQ={freq}"]
    has_by = False
    if r.chance(1, 2):
        parts.append(f"INTERVAL={r.pick([1, 2, 2, 3, 4, 5, 7, 12])}")
    if freq == "WEEKLY" and r.chance(1, 2):
        parts.append(f"WKST={r.pick(WD)}")
    elif r.chance(1, 10):
        parts.append(f"WKST={r.pick(WD)}")
    if r.chance(1, 3) or (freq == "YEARLY" and r.chance(1, 3)):
        parts.append("BYMONTH=" + ",".join(str(m) for m in sub(r, 1 + r.below(3), [1, 2, 3, 4, 6, 9, 11, 12])))
        has_by = True
    if freq != "WEEKLY" and r.chance(2, 5):
        parts.append("BYMONTHDAY=" + ",".join(str(v) for v in
                                               sub(r, 1 + r.below(3), [1, 2, 13, 15, 28, 29, 30, 31, -1, -2, -29,
                                                                       -30, -31])))
        has_by = True
    if r.chance(1, 2) or freq == "WEEKLY" and r.chance(1, 2):
        if freq in ("DAILY", "WEEKLY"):
            parts.append("BYDAY=" + byday_list(r, None))
        elif freq == "MONTHLY":
            parts.append("BYDAY=" + byday_list(r, [1, 2, 3, 4, 5, -1, -2, -5, "+1"]))
        else:
            parts.append("BYDAY=" + byday_list(r, [1, 2, 3, 5, -1, -2, 10, 20, 52, 53, -53]))
        has_by = True
    if has_by and r.chance(2, 5):
        parts.append("BYSETPOS=" + ",".join(str(v) for v in sub(r, 1 + r.below(2), [1, 2, 3, -1, -2, 5, 10])))
    end = r.below(3)
    if end == 0:
        parts.append(f"COUNT={r.pick([1, 2, 3, 5, 8, 13, 30])}")
    elif end == 1:
        span = {"DAILY": 40, "WEEKLY": 200, "MONTHLY": 900, "YEARLY": 5000}[freq]
        uy, um, ud = add_days(sy, smo, sd, r.below(span) - span // 10)
        if r.chance(1, 2):                              # often exactly at an instance's time of day
            parts.append("UNTIL=" + dt(uy, um, ud, sh, smi))
        else:
            parts.append("UNTIL=" + dt(uy, um, ud, r.pick([0, 9, 10, 23]), r.pick([0, 0, 30, 59])))
    head, tail = parts[0], parts[1:]
    for i in range(len(tail) - 1, 0, -1):
        j = r.below(i + 1)
        tail[i], tail[j] = tail[j], tail[i]
    pos = r.below(len(tail) + 1)
    return ";".join(tail[:pos] + [head] + tail[pos:])


BREAK_RULE = [
    lambda s: s.replace("FREQ=", "freq="),
    lambda s: s + ";",
    lambda s: s + ";INTERVAL=0",
    lambda s: s + ";INTERVAL=01",
    lambda s: s + ";COUNT=3;UNTIL=2030-01-01T00:00" if "COUNT" not in s and "UNTIL" not in s else s + ";COUNT=4",
    lambda s: s + ";BYSETPOS=1" if "BY" not in s else s + ";BYSETPOS=0",
    lambda s: s + ";BYDAY=MO;BYDAY=TU",
    lambda s: s + ";BYDAY=1MO" if "WEEKLY" in s or "DAILY" in s else s + ";BYDAY=0MO",
    lambda s: s + ";BYMONTHDAY=1" if "WEEKLY" in s else s + ";BYMONTHDAY=32",
    lambda s: s.replace(";", "; ", 1) if ";" in s else s + "; COUNT=2",
    lambda s: s + ";BYMONTH=0",
    lambda s: s + ";UNTIL=2030-02-29T00:00" if "COUNT" not in s else s + ";BYYEARDAY=1",
]


def random_event(r, i):
    freq = r.pick(["DAILY", "WEEKLY", "MONTHLY", "YEARLY"])
    sy = r.pick([1, 2, 1896, 1899, 1900, 1999, 2000, 2023, 2024, 2025, 2026, 2026, 2027, 2099, 2100, 2400, 9998,
                 9999])
    smo = r.pick([1, 2, 2, 3, 4, 6, 8, 11, 12])
    sd = r.pick([1, 1, 15, 28, 29, 30, 31, 31, r.below(28) + 1])
    sd = min(sd, mlen(sy, smo))
    sh, smi = r.pick([0, 8, 9, 12, 23]), r.pick([0, 30, 45, 59])
    start = dt(sy, smo, sd, sh, smi)
    rule = None if r.chance(1, 20) else random_rule(r, freq, sy, smo, sd, sh, smi)
    unit = {"DAILY": 1, "WEEKLY": 7, "MONTHLY": 30, "YEARLY": 365}[freq]
    # range: usually around the start; sometimes far later (only without COUNT, as the size limits require)
    far = rule is not None and "COUNT" not in rule and r.chance(1, 4)
    if far:
        ly = clamp_year(sy + r.pick([50, 400, 1234, 3000, 7999]))
        lo_y, lo_m, lo_d = ly, r.pick([1, 2, 6, 12]), 1
    else:
        lo_y, lo_m, lo_d = add_days(sy, smo, sd, -r.pick([0, 0, 1, 3, 40]))
        if lo_y < 1:
            lo_y, lo_m, lo_d = 1, 1, 1
    hi_y, hi_m, hi_d = add_days(lo_y, lo_m, lo_d, unit * r.pick([10, 30, 60, 120]))
    if hi_y > 9999:
        hi_y, hi_m, hi_d = 9999, 12, 31
    lo = dt(lo_y, lo_m, lo_d, r.pick([0, 0, sh]), r.pick([0, smi]))
    hi = dt(hi_y, hi_m, hi_d, *r.pick([(0, 0), (23, 59), (sh, smi)]))
    if sy >= 9998 and r.chance(1, 2):
        hi = "9999-12-31T23:59"
    exdates, rdates = [], []
    for _ in range(r.below(4)):
        if freq in ("MONTHLY", "YEARLY") and r.chance(1, 2):     # same day of month, some periods later
            k = 1 + r.below(6)
            mi = sy * 12 + smo - 1 + (k if freq == "MONTHLY" else 12 * k)
            y, m, d = mi // 12, mi % 12 + 1, sd
            if y > 9999 or d > mlen(y, m):
                continue
        else:
            y, m, d = add_days(sy, smo, sd, r.below(unit * 6))
        if y <= 9999:
            exdates.append(dt(y, m, d, sh, smi if r.chance(5, 6) else (smi + 1) % 60))
    if r.chance(1, 5):
        exdates.append(start)
    for _ in range(r.below(3)):
        y, m, d = add_days(sy, smo, sd, r.below(unit * 8) - unit)
        if 1 <= y <= 9999:
            rdates.append(dt(y, m, d, r.pick([sh, 7]), smi))
    if r.chance(1, 8):
        rdates.append(start)
    if rule is not None and r.chance(3, 25):
        rule = r.pick(BREAK_RULE)(rule)
    elif r.chance(1, 30):
        rdates.append(r.pick(["2026-02-29T10:00", "2026-03-02 10:00", "2026-3-02T10:00", "2026-03-02T10:60"]))
    return ev(start, rule, exdates, rdates), lo, hi


def step_periods(freq, y, m, d, k):
    """The start's date moved k periods on (MONTHLY/YEARLY keep the day; None if that day does not exist)."""
    if freq == "DAILY":
        return add_days(y, m, d, k)
    if freq == "WEEKLY":
        return add_days(y, m, d, 7 * k)
    mi = y * 12 + m - 1 + (k if freq == "MONTHLY" else 12 * k)
    y2, m2 = mi // 12, mi % 12 + 1
    return (y2, m2, d) if 1 <= y2 <= 9999 and d <= mlen(y2, m2) else None


def focused_event(r):
    """Events built around one trap each, with random parameters."""
    kind = r.below(7)
    freq = r.pick(["DAILY", "WEEKLY", "MONTHLY", "YEARLY"])
    y, m = r.pick([1999, 2000, 2024, 2026, 2027]), 1 + r.below(12)
    d = min(r.pick([1, 15, 28, 29, 30, 31, 1 + r.below(28)]), mlen(y, m))
    h, mi = r.pick([(9, 0), (18, 30), (0, 0), (23, 59)])
    start = dt(y, m, d, h, mi)
    lo = dt(*add_days(y, m, d, -r.below(5)), 0, 0)
    hi = dt(*add_days(y, m, d, {"DAILY": 60, "WEEKLY": 400, "MONTHLY": 1500, "YEARLY": 12000}[freq]), 0, 0)
    exdates = []
    if kind == 0:      # UNTIL exactly on a (likely) instance
        tgt = step_periods(freq, y, m, d, 1 + r.below(8)) or add_days(y, m, d, 1)
        rule = f"FREQ={freq};UNTIL={dt(*tgt, h, mi)}" + r.pick(["", ";INTERVAL=1", ";BYMONTH=" + str(tgt[1])])
    elif kind == 1:    # range end exactly on a (likely) instance
        tgt = step_periods(freq, y, m, d, 1 + r.below(8)) or add_days(y, m, d, 1)
        rule = f"FREQ={freq};COUNT={r.pick([5, 10, 40])}"
        hi = dt(*tgt, h, mi)
    elif kind == 2:    # BYSETPOS with UNTIL inside a period
        f2 = r.pick(["WEEKLY", "MONTHLY", "YEARLY"])
        days = r.pick(["MO,TU,WE,TH,FR", "SA,SU", "MO,WE,FR", "TU,TH"])
        extra = ";BYMONTH=" + str(1 + r.below(12)) if f2 == "YEARLY" else ""
        u = add_days(y, m, d, r.below({"WEEKLY": 30, "MONTHLY": 200, "YEARLY": 1500}[f2]))
        rule = (f"FREQ={f2};BYDAY={days}{extra};BYSETPOS={r.pick(['-1', '-2', '2', '-1,1', '3'])};"
                f"UNTIL={dt(*u, r.pick([h, 12]), mi)}")
    elif kind == 3:    # the calendar's last weeks / months
        y, m = 9999, r.pick([11, 12])
        d = 1 + r.below(28)
        start = dt(y, m, d, h, mi)
        lo, hi = dt(9999, m, 1, 0, 0), "9999-12-31T23:59"
        f2 = r.pick(["WEEKLY", "WEEKLY", "DAILY", "MONTHLY"])
        days = r.pick(["MO,FR,SU", "TH,FR,SA,SU", "FR", "SA,SU", "MO,TU,WE,TH,FR"])
        if f2 == "MONTHLY":
            days = r.pick(["-1FR,-1SA", "5FR,-1SU", "MO,FR"])
        rule = f"FREQ={f2};BYDAY={days};BYSETPOS={r.pick(['-1', '-2', '1,-1', '2'])};WKST={r.pick(WD)}"
    elif kind == 4:    # UNTIL before the start
        u = add_days(y, m, d, -1 - r.below(40))
        rule = f"FREQ={freq};UNTIL={dt(*u, h, mi)}" + r.pick(["", ";BYDAY=MO,TU,WE,TH,FR,SA,SU"])
    elif kind == 5:    # BYSETPOS while the start lies inside the first period
        f2 = r.pick(["WEEKLY", "MONTHLY", "YEARLY"])
        days = r.pick(["MO,TU,WE,TH,FR", "SA,SU", "MO,WE,FR", "TU"])
        rule = (f"FREQ={f2};BYDAY={days};BYSETPOS={r.pick(['1', '2', '1,2', '-3', '1,-1'])};"
                f"COUNT={r.pick([3, 6, 12])}" + (f";WKST={r.pick(WD)}" if f2 == "WEEKLY" else ""))
    else:              # YEARLY ordinals with and without BYMONTH
        ords = ",".join(f"{r.pick([1, 2, 3, -1, -2, 5, 10, 20, -20])}{r.pick(WD)}" for _ in range(1 + r.below(2)))
        rule = f"FREQ=YEARLY;BYDAY={ords};COUNT={r.pick([4, 8])}"
        if r.chance(1, 2):
            rule += ";BYMONTH=" + ",".join(str(x) for x in sub(r, 1 + r.below(3), list(range(1, 13))))
        hi = dt(y + 30, 1, 1, 0, 0)
    if r.chance(1, 4):
        exdates.append(start)
    return ev(start, rule, exdates, []), lo, hi


def random_cases():
    res = []
    for i in range(150):
        r = SplitMix(150000 + i)
        event, lo, hi = random_event(r, i)
        res.append({"id": f"R{i + 1:03d}", "title": "random event", "args": [event, lo, hi]})
    for i in range(70):
        r = SplitMix(160000 + i)
        event, lo, hi = focused_event(r)
        res.append({"id": f"R{i + 151:03d}", "title": "random event around one trap", "args": [event, lo, hi]})
    return res


def hidden():
    return hand() + random_cases()


# ── Stress ──────────────────────────────────────────────────────────────────
S1_RULE = ("FREQ=DAILY;BYMONTH=1,2,3,4,5,6,7,8,9,10,11,12;BYMONTHDAY=1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,"
           "-12,-11,-10,-9,-8,-7,-6,-5,-4,-3,-2,-1;BYDAY=MO,TU,WE,TH,FR,SA;BYSETPOS=-1")
S2_RULE = ("FREQ=YEARLY;BYDAY=" + ",".join(f"1{d},-1{d},3{d}" for d in WD)
           + ";BYMONTH=1,2,3,4,5,6,7,8,9,10,11,12;BYSETPOS=3,-3,7,-7,50,100;COUNT=59000")


def stress():
    return [
        {"id": "S1", "title": "no COUNT: dense DAILY rule from 0001-01-01, range in the last century", "seed": 151,
         "start": "0001-01-01T06:15", "rule": S1_RULE, "range": ["9900-01-01T00:00", "9999-12-31T23:59"],
         "n_dates": 1000},
        {"id": "S2", "title": "COUNT 59000: YEARLY with 21 ordinal BYDAY entries and BYSETPOS from year 1",
         "seed": 152, "start": "0001-01-01T09:00", "rule": S2_RULE,
         "range": ["9000-01-01T00:00", "9999-12-31T23:59"], "n_dates": 1000},
        {"id": "S3", "title": "COUNT 40000: dense DAILY rule with BYSETPOS over five centuries", "seed": 153,
         "start": "9460-01-01T06:30", "rule": "FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR;BYMONTH=1,4,7,10;BYSETPOS=-1;COUNT=40000",
         "range": ["9800-01-01T00:00", "9999-12-31T23:59"], "n_dates": 1000},
    ]


def stress_args(case):
    r = SplitMix(case["seed"])
    lo_y = int(case["range"][0][:4])
    hh, mm = int(case["start"][11:13]), int(case["start"][14:16])
    exdates, rdates = [], []
    for k in range(case["n_dates"]):
        y = lo_y + r.below(9999 - lo_y + 1)
        m = 1 + r.below(12)
        d = 1 + r.below(mlen(y, m))
        exdates.append(dt(y, m, d, hh, mm))
        y = lo_y + r.below(9999 - lo_y + 1)
        m = 1 + r.below(12)
        d = 1 + r.below(mlen(y, m))
        rdates.append(dt(y, m, d, r.pick([hh, 12]), mm))
    return [ev(case["start"], case["rule"], exdates, rdates), case["range"][0], case["range"][1]]
