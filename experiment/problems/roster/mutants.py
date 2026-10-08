"""Planted misreadings of SPEC.md for Problem 13. Each must be caught by at least one non-public case."""

MUTANTS = {
    "M01 load W counts minutes in every week, not the shift's week": [
        ("        return sorted(pool, key=lambda q: week_minutes[q].get(week, 0))",
         "        return sorted(pool, key=lambda q: sum(week_minutes[q].values()))"),
    ],
    "M02 candidates tried in id order only (no load order)": [
        ("        return sorted(pool, key=lambda q: week_minutes[q].get(week, 0))", "        return list(pool)"),
    ],
    "M03 later seats may take any unused person, not only higher ids": [
        ("            pool = pool[bisect_right(pool, seats[s[\"id\"]][-1]):]",
         "            pool = [q for q in pool if q not in seats[s[\"id\"]]]"),
    ],
    "M04 a shift is only on its start date": [
        ("    first_day, last_day = a // 1440, (b - 1) // 1440", "    first_day, last_day = a // 1440, a // 1440"),
    ],
    "M05 a shift ending at 00:00 is also on the date it ends": [
        ("    first_day, last_day = a // 1440, (b - 1) // 1440", "    first_day, last_day = a // 1440, b // 1440"),
    ],
    "M06 availability checked on the start date only": [
        ("        if any(d in off for d in range(d0, d1 + 1)):", "        if d0 in off:"),
    ],
    "M07 a shift belongs to the week of its end": [
        ("            \"week\": (first_day - 1) // 7}", "            \"week\": (b // 1440 - 1) // 7}"),
    ],
    "M08 the weekly cap is exclusive": [
        ("        if week_minutes[q].get(s[\"week\"], 0) + s[\"length\"] > caps[q]:",
         "        if week_minutes[q].get(s[\"week\"], 0) + s[\"length\"] >= caps[q]:"),
    ],
    "M09 rest must exceed the minimum": [
        ("            if s[\"start\"] - last_end < min_rest:", "            if s[\"start\"] - last_end <= min_rest:"),
    ],
    "M10 touching shifts count as overlapping": [
        ("            if last_end > s[\"start\"]:", "            if last_end >= s[\"start\"]:"),
    ],
    "M11 the consecutive-day limit is exclusive": [
        ("        if run > max_run:", "        if run >= max_run:"),
    ],
    "M12 consecutive-day runs restart each Monday": [
        ("        x = d0 - 1\n        while x in days:",
         "        x = d0 - 1\n        while x in days and (x - 1) // 7 == (d0 - 1) // 7:"),
        ("        x = d1 + 1\n        while x in days:",
         "        x = d1 + 1\n        while x in days and (x - 1) // 7 == (d1 - 1) // 7:"),
    ],
    "M13 forbidden pairs are ordered (first listed must be seated first)": [
        ("            enemies[rank[a]].add(rank[b])\n", ""),
    ],
    "M14 a needs_senior shift must have a senior in seat 0": [
        ("        if k == s[\"need\"] - 1 and s[\"needs_senior\"] and not senior[q] and seniors_on[s[\"id\"]] == 0:",
         "        if k == 0 and s[\"needs_senior\"] and not senior[q]:"),
    ],
    "M15 duplicate ids: the first record is kept": [
        ("    kept = []", "    kept, seen = [], set()"),
        ("        if count[r[\"id\"]] > 1:", "        if r[\"id\"] in seen:"),
        ("            kept.append(r)", "            kept.append(r)\n            seen.add(r[\"id\"])"),
    ],
    "M16 a bool is accepted where an int is required": [
        ("    if type(cap) is not int or cap < 0:", "    if not isinstance(cap, int) or cap < 0:"),
        ("    if type(need) is not int or need < 1:", "    if not isinstance(need, int) or need < 1:"),
    ],
    "M17 minutes lists only staff who hold a shift": [
        ("    minutes = {pid: 0 for pid in ids}", "    minutes = {}"),
        ("                minutes[ids[q]] += s[\"length\"]",
         "                minutes[ids[q]] = minutes.get(ids[q], 0) + s[\"length\"]"),
    ],
    "M18 slots ordered by start and shift id, ignoring the end": [
        ("    jobs.sort(key=lambda s: (s[\"start\"], s[\"end\"], s[\"id\"]))",
         "    jobs.sort(key=lambda s: (s[\"start\"], s[\"id\"]))"),
    ],
    "M19 input order instead of id order for ties and seats": [
        ("    people.sort(key=lambda p: p[\"id\"])", "    pass"),
    ],
    "M20 a bad unavailable date is skipped instead of ignoring the record": [
        ("        if n is None:\n            return None\n        days.add(n)",
         "        if n is not None:\n            days.add(n)"),
    ],
}
