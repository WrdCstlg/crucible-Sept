"""Planted misreadings of SPEC.md for Problem 10. Each must be caught by at least one non-public case."""

MUTANTS = {
    "M01 plain nearest-quarter rounding (8 rounds down)": [
        ("    return base if q <= 7 else base + timedelta(minutes=15)",
         "    return base if q <= 8 else base + timedelta(minutes=15)"),
    ],
    "M02 day taken from the raw (unrounded) start": [
        ("        candidates.append((ra, rb, idx))", "        candidates.append((ra, rb, idx, a))"),
        ("    for ra, rb, idx in candidates:", "    for ra, rb, idx, a in candidates:"),
        ("        shifts.append((ra, rb))", "        shifts.append((ra, rb, a))"),
        ("    for ra, rb in shifts:\n        day = ra.date()", "    for ra, rb, a in shifts:\n        day = a.date()"),
    ],
    "M03 overlapping punches merged instead of dropped": [
        ("        if last_out is not None and ra < last_out:\n            ignored.append(idx)\n            continue\n"
         "        shifts.append((ra, rb))\n        last_out = rb",
         "        if last_out is not None and ra < last_out:\n            ignored.append(idx)\n"
         "            if rb > last_out:\n                shifts[-1] = (shifts[-1][0], rb)\n                last_out = rb\n"
         "            continue\n        shifts.append((ra, rb))\n        last_out = rb"),
    ],
    "M04 shift split at midnight": [
        ("    for ra, rb in shifts:\n        day = ra.date()\n        minutes = int((rb - ra).total_seconds() // 60)\n"
         "        worked[day] = worked.get(day, 0) + minutes",
         "    for ra, rb in shifts:\n        day = ra.date()\n        minutes = int((rb - ra).total_seconds() // 60)\n"
         "        cur = ra\n        while cur < rb:\n"
         "            nxt = min(rb, datetime(cur.year, cur.month, cur.day) + timedelta(days=1))\n"
         "            worked[cur.date()] = worked.get(cur.date(), 0) + int((nxt - cur).total_seconds() // 60)\n"
         "            cur = nxt"),
    ],
    "M05 weeks start on Sunday": [
        ("        weeks.setdefault(day - timedelta(days=day.weekday()), []).append(day)",
         "        weeks.setdefault(day - timedelta(days=(day.weekday() + 1) % 7), []).append(day)"),
    ],
    "M06 no seventh-day rule": [
        ("        seventh = all(worked.get(d, 0) > 0 for d in days)", "        seventh = False"),
    ],
    "M07 seventh day counted as all double time": [
        ("                reg, o, x = 0, min(w, 480), max(0, w - 480)", "                reg, o, x = 0, 0, w"),
    ],
    "M08 daily overtime counts toward the weekly 40": [
        ("        reg_total = ot = dt = 0", "        reg_total = ot = dt = counted = 0"),
        ("            allowed = max(0, 2400 - reg_total)\n            moved = max(0, reg - allowed)\n"
         "            reg_total += reg - moved",
         "            allowed = max(0, 2400 - counted)\n            moved = max(0, reg - allowed)\n"
         "            reg_total += reg - moved\n            counted += reg - moved + o + x"),
    ],
    "M09 meal penalty on total day minutes": [
        ("        if minutes > 300:\n            meal.add(day)", ""),
        ("    weeks = {}\n", "    meal = {d for d, w in worked.items() if w > 300}\n    weeks = {}\n"),
    ],
    "M10 meal penalty at 300 minutes or more": [
        ("        if minutes > 300:", "        if minutes >= 300:"),
    ],
    "M11 regular pay rounded per day": [
        ("        reg_total = ot = dt = 0", "        reg_total = ot = dt = 0\n        day_regs = []"),
        ("            reg_total += reg - moved\n", "            reg_total += reg - moved\n            day_regs.append(reg - moved)\n"),
        ("        regular_pay = half_up(reg_total * rate, 60)",
         "        regular_pay = sum(half_up(m * rate, 60) for m in day_regs)"),
    ],
    "M12 banker's rounding of pay": [
        ("    return (2 * num + den) // (2 * den)",
         "    q, r = divmod(num, den)\n    return q + (1 if 2 * r > den or (2 * r == den and q % 2) else 0)"),
    ],
    "M13 empty punches not reported as ignored": [
        ("        if rb <= ra:\n            ignored.append(idx)\n            continue",
         "        if rb <= ra:\n            continue"),
    ],
    "M14 a dropped punch still moves the overlap boundary": [
        ("        if last_out is not None and ra < last_out:\n            ignored.append(idx)\n            continue",
         "        if last_out is not None and ra < last_out:\n            ignored.append(idx)\n"
         "            last_out = rb\n            continue"),
    ],
    "M15 ties sorted by input index before end time": [
        ("    candidates.sort()", "    candidates.sort(key=lambda c: (c[0], c[2]))"),
    ],
    "M16 lenient timestamp parsing": [
        ("    if type(ts) is not str or len(ts) != 16 or ts[4] != \"-\" or ts[7] != \"-\" or ts[10] != \" \" or ts[13] != \":\":\n"
         "        return None",
         "    try:\n        return datetime.strptime(ts.strip(), \"%Y-%m-%d %H:%M\")\n    except (ValueError, TypeError):\n"
         "        return None"),
    ],
}
