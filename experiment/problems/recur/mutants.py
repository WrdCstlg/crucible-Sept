"""Planted misreadings of SPEC.md for Problem 15. Each must be caught by at least one non-public case."""

SELECT = "            days = select(days, r[\"bysetpos\"])"
FOUND = "    found = (set(series) | set(rdates)) - set(exdates)"
ROOM = "        room = None if rule[\"count\"] is None else rule[\"count\"] - 1"
CALL = "        series += rule_instances(rule, start, lo, hi, room)"
SCOPE = "    r[\"month_scope\"] = r[\"freq\"] == \"MONTHLY\" or r[\"bymonth\"] is not None"

MUTANTS = {
    "M01 start is an occurrence only when it matches the rule": [
        ("    series = [start]\n", "    series = [] if event[\"rule\"] is not None else [start]\n"),
        ("            if t <= start:", "            if t < start:"),
        (ROOM, "        room = rule[\"count\"]"),
    ],
    "M02 COUNT does not include the start": [
        (ROOM, "        room = rule[\"count\"]"),
    ],
    "M03 excluded entries do not use up COUNT": [
        (CALL, "        skip = set(exdates)\n        if room is not None and start in skip:\n            room += 1\n"
               "        series += rule_instances(rule, start, lo, hi, room, skip)"),
        ("def rule_instances(r, start, range_start, range_end, room):",
         "def rule_instances(r, start, range_start, range_end, room, skip=frozenset()):"),
        ("            out.append(t)\n", "            if t in skip:\n                continue\n            out.append(t)\n"),
    ],
    "M04 UNTIL is exclusive": [
        ("            if until is not None and t > until:", "            if until is not None and t >= until:"),
    ],
    "M05 the start is dropped when it is later than UNTIL": [
        (CALL, "        if rule[\"until\"] is not None and start > rule[\"until\"]:\n            series = []\n" + CALL),
    ],
    "M06 RDATEs before the start are dropped": [
        (FOUND, "    found = (set(series) | {t for t in rdates if t >= start}) - set(exdates)"),
    ],
    "M07 missing month days are clamped into the month": [
        ("        if v > 0 and v <= length:\n            out.append(a + v - 1)",
         "        if v > 0:\n            out.append(a + min(v, length) - 1)"),
        ("        elif v < 0 and -v <= length:\n            out.append(a + length + v)",
         "        elif v < 0:\n            out.append(a + max(length + v, 0))"),
    ],
    "M08 YEARLY ordinals count in the year even with BYMONTH": [
        (SCOPE, "    r[\"month_scope\"] = r[\"freq\"] == \"MONTHLY\""),
    ],
    "M09 YEARLY ordinals always count in the month": [
        (SCOPE, "    r[\"month_scope\"] = True"),
        ("    if r[\"bymonth\"] is None and r[\"bymonthday\"] is None:\n"
         "        return sorted(set(byday_expand(r[\"byday\"], ya, yb)))",
         "    if False:\n        return []"),
    ],
    "M10 BYSETPOS applied after dropping days before the start": [
        (SELECT, "            days = select([o for o in days if o * 1440 + tod >= start], r[\"bysetpos\"])"),
    ],
    "M11 BYSETPOS applied after UNTIL": [
        (SELECT, "            days = select([o for o in days if until is None or o * 1440 + tod <= until], "
                 "r[\"bysetpos\"])"),
    ],
    "M12 WKST ignored: weeks always run Monday to Sunday": [
        ("    w0 = so - (weekday(so) - r[\"wkst\"]) % 7", "    w0 = so - weekday(so)"),
        ("        o = w + (wd - r[\"wkst\"]) % 7", "        o = w + wd"),
    ],
    "M13 BYSETPOS ignored for DAILY": [
        ("        if r[\"bysetpos\"] is not None:\n" + SELECT,
         "        if r[\"bysetpos\"] is not None and freq != \"DAILY\":\n" + SELECT),
    ],
    "M14 MONTHLY default day of month applied even with BYDAY": [
        ("    if r[\"freq\"] == \"MONTHLY\" and r[\"bymonthday\"] is None and r[\"byday\"] is None:",
         "    if r[\"freq\"] == \"MONTHLY\" and r[\"bymonthday\"] is None:"),
    ],
    "M15 YEARLY BYMONTHDAY without BYMONTH kept to the start's month": [
        ("        r[\"bymonthday\"] = [d.day]\n        if r[\"bymonth\"] is None:\n            r[\"bymonth\"] = [d.month]",
         "        r[\"bymonthday\"] = [d.day]\n"
         "    if r[\"freq\"] == \"YEARLY\" and r[\"bymonth\"] is None and r[\"byday\"] is None:\n"
         "        r[\"bymonth\"] = [d.month]"),
    ],
    "M16 range end is inclusive": [
        ("fmt(t) for t in sorted(found) if lo <= t < hi", "fmt(t) for t in sorted(found) if lo <= t <= hi"),
        ("            if t >= range_end:", "            if t > range_end:"),
        ("        if first * 1440 + tod >= range_end or", "        if first * 1440 + tod > range_end or"),
    ],
    "M17 EXDATE does not remove RDATEs": [
        (FOUND, "    found = (set(series) - set(exdates)) | set(rdates)"),
    ],
    "M18 leading zeros accepted in integers": [
        ("    if not ascii_digits(s) or s[0] == \"0\":", "    if not ascii_digits(s) or int(s) == 0:"),
    ],
    "M19 COUNT together with UNTIL accepted": [
        ("    if \"FREQ\" not in raw or (\"COUNT\" in raw and \"UNTIL\" in raw):", "    if \"FREQ\" not in raw:"),
    ],
    "M20 a week running past 9999-12-31 is dropped": [
        ("            return None if w > MAXORD else (w, weekly(r, w))",
         "            return None if w + 6 > MAXORD else (w, weekly(r, w))"),
    ],
}
