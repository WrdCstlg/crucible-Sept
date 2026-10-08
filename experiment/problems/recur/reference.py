"""Reference for Problem 15 (calendar recurrence expansion). Stdlib only.

A datetime is an int: day ordinal * 1440 + minute of the day (ordinal 1 is 0001-01-01, a Monday). Each used period's
candidates are built directly from the BY parts (never by testing every day of the period), and without COUNT the walk
starts at the used period holding range_start, so the work is bounded by the width of the range, not its distance
from the start.
"""
from datetime import date

MAXORD = date(9999, 12, 31).toordinal()
WEEKDAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
NAMES = ("FREQ", "INTERVAL", "COUNT", "UNTIL", "WKST", "BYMONTH", "BYMONTHDAY", "BYDAY", "BYSETPOS")
FREQS = ("DAILY", "WEEKLY", "MONTHLY", "YEARLY")
DIGITS = "0123456789"
MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def month_len(y, m):
    return 29 if m == 2 and is_leap(y) else MONTH_DAYS[m - 1]


def weekday(o):
    """Monday = 0 ... Sunday = 6, for any integer day ordinal."""
    return (o - 1) % 7


def ascii_digits(s):
    return s != "" and all(c in DIGITS for c in s)


# ── Parsing ─────────────────────────────────────────────────────────────────
def parse_dt(s):
    if len(s) != 16 or s[4] != "-" or s[7] != "-" or s[10] != "T" or s[13] != ":":
        return None
    fields = (s[0:4], s[5:7], s[8:10], s[11:13], s[14:16])
    if not all(ascii_digits(f) for f in fields):
        return None
    y, mo, d, h, mi = (int(f) for f in fields)
    if y < 1 or not 1 <= mo <= 12 or not 1 <= d <= month_len(y, mo) or h > 23 or mi > 59:
        return None
    return date(y, mo, d).toordinal() * 1440 + h * 60 + mi


def fmt(t):
    o, m = divmod(t, 1440)
    return f"{date.fromordinal(o).isoformat()}T{m // 60:02d}:{m % 60:02d}"


def unsigned(s, hi):
    """Unsigned integer 1..hi (no leading zero), else None."""
    if not ascii_digits(s) or s[0] == "0":
        return None
    v = int(s)
    return v if v <= hi else None


def signed(s, hi):
    """Signed integer 1..hi or -hi..-1, else None."""
    neg = s[:1] == "-"
    if s[:1] in ("+", "-"):
        s = s[1:]
    v = unsigned(s, hi)
    return None if v is None else (-v if neg else v)


def byday_item(x):
    if len(x) < 2 or x[-2:] not in WEEKDAYS:
        return None
    n = None
    if len(x) > 2:
        n = signed(x[:-2], 53)
        if n is None:
            return None
    return (n, WEEKDAYS.index(x[-2:]))


def parse_list(text, item):
    vals = [item(x) for x in text.split(",")]
    return None if None in vals else vals


def parse_rule(text):
    """Rule dict (keys are the lower-cased part names) or None if the rule is invalid."""
    raw = {}
    for part in text.split(";"):
        if part.count("=") != 1:
            return None
        name, value = part.split("=")
        if name not in NAMES or name in raw:
            return None
        raw[name] = value
    if "FREQ" not in raw or ("COUNT" in raw and "UNTIL" in raw):
        return None
    r = {"freq": raw["FREQ"] if raw["FREQ"] in FREQS else None, "interval": 1, "count": None, "until": None,
         "wkst": 0, "bymonth": None, "bymonthday": None, "byday": None, "bysetpos": None}
    if "INTERVAL" in raw:
        r["interval"] = unsigned(raw["INTERVAL"], 100000)
    if "COUNT" in raw:
        r["count"] = unsigned(raw["COUNT"], 1000000)
    if "UNTIL" in raw:
        r["until"] = parse_dt(raw["UNTIL"])
    if "WKST" in raw:
        r["wkst"] = WEEKDAYS.index(raw["WKST"]) if raw["WKST"] in WEEKDAYS else None
    if "BYMONTH" in raw:
        r["bymonth"] = parse_list(raw["BYMONTH"], lambda x: unsigned(x, 12))
    if "BYMONTHDAY" in raw:
        r["bymonthday"] = parse_list(raw["BYMONTHDAY"], lambda x: signed(x, 31))
    if "BYDAY" in raw:
        r["byday"] = parse_list(raw["BYDAY"], byday_item)
    if "BYSETPOS" in raw:
        r["bysetpos"] = parse_list(raw["BYSETPOS"], lambda x: signed(x, 366))
    for name in raw:
        if r[name.lower()] is None:
            return None
    if r["freq"] in ("DAILY", "WEEKLY") and r["byday"] is not None and any(n is not None for n, _ in r["byday"]):
        return None
    if r["freq"] == "WEEKLY" and r["bymonthday"] is not None:
        return None
    if r["bysetpos"] is not None and r["bymonth"] is None and r["bymonthday"] is None and r["byday"] is None:
        return None
    return r


# ── Candidates of one period ────────────────────────────────────────────────
def with_defaults(r, d):
    """Copy of rule r with the defaults taken from the start's date d."""
    r = dict(r)
    r["month_scope"] = r["freq"] == "MONTHLY" or r["bymonth"] is not None
    if r["freq"] == "WEEKLY" and r["byday"] is None:
        r["byday"] = [(None, d.weekday())]
    if r["freq"] == "MONTHLY" and r["bymonthday"] is None and r["byday"] is None:
        r["bymonthday"] = [d.day]
    if r["freq"] == "YEARLY" and r["bymonthday"] is None and r["byday"] is None:
        r["bymonthday"] = [d.day]
        if r["bymonth"] is None:
            r["bymonth"] = [d.month]
    return r


def nth_weekday(n, wd, a, b):
    """The n-th day with weekday wd in days a..b (n < 0: counted from b), or None."""
    if n > 0:
        o = a + (wd - weekday(a)) % 7 + 7 * (n - 1)
    else:
        o = b - (weekday(b) - wd) % 7 + 7 * (n + 1)
    return o if a <= o <= b else None


def byday_expand(byday, a, b):
    out = []
    for n, wd in byday:
        if n is None:
            out.extend(range(a + (wd - weekday(a)) % 7, b + 1, 7))
        else:
            o = nth_weekday(n, wd, a, b)
            if o is not None:
                out.append(o)
    return out


def byday_match(byday, o, a, b):
    w = weekday(o)
    for n, wd in byday:
        if wd == w and (n is None or nth_weekday(n, wd, a, b) == o):
            return True
    return False


def monthdays(bymonthday, a, length):
    """Days of the month starting at ordinal a (length days) named by BYMONTHDAY; missing ones are skipped."""
    out = []
    for v in bymonthday:
        if v > 0 and v <= length:
            out.append(a + v - 1)
        elif v < 0 and -v <= length:
            out.append(a + length + v)
    return out


def daily(r, o):
    d = date.fromordinal(o)
    if r["bymonth"] is not None and d.month not in r["bymonth"]:
        return []
    if r["bymonthday"] is not None and o not in monthdays(r["bymonthday"], o - d.day + 1, month_len(d.year, d.month)):
        return []
    if r["byday"] is not None and not byday_match(r["byday"], o, o, o):
        return []
    return [o]


def weekly(r, w):
    out = set()
    for _, wd in r["byday"]:
        o = w + (wd - r["wkst"]) % 7
        if 1 <= o <= MAXORD and (r["bymonth"] is None or date.fromordinal(o).month in r["bymonth"]):
            out.add(o)
    return sorted(out)


def in_month(r, y, m, ya, yb):
    """Candidates inside month (y, m) of a MONTHLY or YEARLY period; ya..yb is the year (the BYDAY scope when the
    ordinal counts in the year)."""
    a = date(y, m, 1).toordinal()
    length = month_len(y, m)
    sa, sb = (a, a + length - 1) if r["month_scope"] else (ya, yb)
    if r["bymonthday"] is None:
        return [o for o in byday_expand(r["byday"], sa, sb) if a <= o < a + length]
    days = monthdays(r["bymonthday"], a, length)
    if r["byday"] is not None:
        days = [o for o in days if byday_match(r["byday"], o, sa, sb)]
    return days


def monthly(r, y, m):
    if r["bymonth"] is not None and m not in r["bymonth"]:
        return []
    return sorted(set(in_month(r, y, m, None, None)))


def yearly(r, y):
    ya, yb = date(y, 1, 1).toordinal(), date(y, 12, 31).toordinal()
    if r["bymonth"] is None and r["bymonthday"] is None:
        return sorted(set(byday_expand(r["byday"], ya, yb)))
    days = []
    for m in (r["bymonth"] or range(1, 13)):
        days.extend(in_month(r, y, m, ya, yb))
    return sorted(set(days))


def select(days, positions):
    n = len(days)
    keep = set()
    for p in positions:
        i = p - 1 if p > 0 else n + p
        if 0 <= i < n:
            keep.add(days[i])
    return sorted(keep)


# ── The series ──────────────────────────────────────────────────────────────
def rule_instances(r, start, range_start, range_end, room):
    """Rule instances later than the start, ascending, up to `room` of them (None: no limit), stopping at UNTIL,
    range_end (nothing later can be returned) or the end of the calendar."""
    out = []
    if room == 0:
        return out
    so, tod = divmod(start, 1440)
    sd = date.fromordinal(so)
    r = with_defaults(r, sd)
    freq, step, until = r["freq"], r["interval"], r["until"]
    w0 = so - (weekday(so) - r["wkst"]) % 7
    m0 = sd.year * 12 + sd.month - 1

    def period(k):
        """(first day, sorted candidates) of period k, or None past the end of the calendar."""
        if freq == "DAILY":
            o = so + k
            return None if o > MAXORD else (o, daily(r, o))
        if freq == "WEEKLY":
            w = w0 + 7 * k
            return None if w > MAXORD else (w, weekly(r, w))
        if freq == "MONTHLY":
            y, m = divmod(m0 + k, 12)
            return None if y > 9999 else (date(y, m + 1, 1).toordinal(), monthly(r, y, m + 1))
        y = sd.year + k
        return None if y > 9999 else (date(y, 1, 1).toordinal(), yearly(r, y))

    k = 0
    if room is None and range_start > start:
        # Without COUNT a period's instances do not depend on earlier periods: start at the used period that
        # contains range_start.
        rd = date.fromordinal(range_start // 1440)
        p = {"DAILY": rd.toordinal() - so, "WEEKLY": (rd.toordinal() - w0) // 7,
             "MONTHLY": rd.year * 12 + rd.month - 1 - m0, "YEARLY": rd.year - sd.year}[freq]
        k = p // step * step
    while True:
        got = period(k)
        if got is None:
            return out
        first, days = got
        if first * 1440 + tod >= range_end or (until is not None and first * 1440 + tod > until):
            return out
        if r["bysetpos"] is not None:
            days = select(days, r["bysetpos"])
        for o in days:
            t = o * 1440 + tod
            if t <= start:
                continue
            if until is not None and t > until:
                return out
            if t >= range_end:
                return out
            out.append(t)
            if room is not None and len(out) == room:
                return out
        k += step


def occurrences(event, range_start, range_end):
    start = parse_dt(event["start"])
    lo, hi = parse_dt(range_start), parse_dt(range_end)
    exdates = [parse_dt(s) for s in event["exdates"]]
    rdates = [parse_dt(s) for s in event["rdates"]]
    if None in [start, lo, hi] + exdates + rdates:
        return {"ok": False, "error": "bad_datetime"}
    series = [start]
    if event["rule"] is not None:
        rule = parse_rule(event["rule"])
        if rule is None:
            return {"ok": False, "error": "bad_rule"}
        room = None if rule["count"] is None else rule["count"] - 1
        series += rule_instances(rule, start, lo, hi, room)
    found = (set(series) | set(rdates)) - set(exdates)
    return {"ok": True, "occurrences": [fmt(t) for t in sorted(found) if lo <= t < hi]}
