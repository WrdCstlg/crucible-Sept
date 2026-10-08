"""Reference for Problem 13 (shift rostering with backtracking). Stdlib only, deterministic, iterative search.

Times are minutes since 0001-01-01 00:00 (date.toordinal() * 1440 + minute of day); day numbers are date ordinals,
and ordinal 1 (0001-01-01) is a Monday, so the week of day d is (d - 1) // 7.
"""
from bisect import bisect_right
from datetime import date

DIGITS = frozenset("0123456789")
STAFF_KEYS = ("id", "skills", "max_minutes_week", "unavailable", "senior")
SHIFT_KEYS = ("id", "start", "end", "skill", "need", "needs_senior")


def parse_date(s):
    """'YYYY-MM-DD' -> date ordinal, or None."""
    if type(s) is not str or len(s) != 10 or s[4] != "-" or s[7] != "-":
        return None
    y, mo, d = s[0:4], s[5:7], s[8:10]
    if not (set(y) <= DIGITS and set(mo) <= DIGITS and set(d) <= DIGITS):
        return None
    try:
        return date(int(y), int(mo), int(d)).toordinal()
    except ValueError:
        return None


def parse_time(s):
    """'YYYY-MM-DD HH:MM' -> absolute minute, or None."""
    if type(s) is not str or len(s) != 16 or s[10] != " " or s[13] != ":":
        return None
    day = parse_date(s[:10])
    hh, mm = s[11:13], s[14:16]
    if day is None or not (set(hh) <= DIGITS and set(mm) <= DIGITS):
        return None
    h, m = int(hh), int(mm)
    if h > 23 or m > 59:
        return None
    return day * 1440 + h * 60 + m


def check_staff(rec):
    if type(rec) is not dict or any(k not in rec for k in STAFF_KEYS):
        return None
    sid, skills, cap, unavailable, senior = (rec[k] for k in STAFF_KEYS)
    if type(sid) is not str or sid == "":
        return None
    if type(skills) is not list or any(type(x) is not str for x in skills):
        return None
    if type(cap) is not int or cap < 0:
        return None
    if type(unavailable) is not list:
        return None
    days = set()
    for d in unavailable:
        n = parse_date(d)
        if n is None:
            return None
        days.add(n)
    if type(senior) is not bool:
        return None
    return {"id": sid, "skills": set(skills), "cap": cap, "unavailable": days, "senior": senior}


def check_shift(rec):
    if type(rec) is not dict or any(k not in rec for k in SHIFT_KEYS):
        return None
    sid, start, end, skill, need, needs_senior = (rec[k] for k in SHIFT_KEYS)
    if type(sid) is not str or sid == "":
        return None
    a, b = parse_time(start), parse_time(end)
    if a is None or b is None or b <= a or b - a > 1440:
        return None
    if type(skill) is not str:
        return None
    if type(need) is not int or need < 1:
        return None
    if type(needs_senior) is not bool:
        return None
    first_day, last_day = a // 1440, (b - 1) // 1440
    return {"id": sid, "start": a, "end": b, "length": b - a, "skill": skill, "need": need,
            "needs_senior": needs_senior, "first_day": first_day, "last_day": last_day,
            "week": (first_day - 1) // 7}


def drop_duplicates(records, ignored):
    """records: [(input index, parsed)]. Every record whose id occurs more than once is ignored."""
    count = {}
    for _, r in records:
        count[r["id"]] = count.get(r["id"], 0) + 1
    kept = []
    for i, r in records:
        if count[r["id"]] > 1:
            ignored.append(i)
        else:
            kept.append(r)
    return kept


def make_roster(staff, shifts, rules):
    ignored_staff, ignored_shifts = [], []
    parsed = []
    for i, rec in enumerate(staff):
        p = check_staff(rec)
        if p is None:
            ignored_staff.append(i)
        else:
            parsed.append((i, p))
    people = drop_duplicates(parsed, ignored_staff)
    parsed = []
    for i, rec in enumerate(shifts):
        s = check_shift(rec)
        if s is None:
            ignored_shifts.append(i)
        else:
            parsed.append((i, s))
    jobs = drop_duplicates(parsed, ignored_shifts)
    ignored = {"staff": sorted(ignored_staff), "shifts": sorted(ignored_shifts)}

    # People are numbered in id order, so comparing numbers compares ids.
    people.sort(key=lambda p: p["id"])
    ids = [p["id"] for p in people]
    rank = {pid: q for q, pid in enumerate(ids)}
    caps = [p["cap"] for p in people]
    unavailable = [p["unavailable"] for p in people]
    senior = [p["senior"] for p in people]
    by_skill = {}
    for q, p in enumerate(people):
        for sk in sorted(p["skills"]):
            by_skill.setdefault(sk, []).append(q)
    enemies = [set() for _ in people]
    for a, b in rules["forbidden_pairs"]:
        if a in rank and b in rank and a != b:
            enemies[rank[a]].add(rank[b])
            enemies[rank[b]].add(rank[a])
    min_rest = rules["min_rest_minutes"]
    max_run = rules["max_consecutive_days"]

    jobs.sort(key=lambda s: (s["start"], s["end"], s["id"]))
    slots = [(s, k) for s in jobs for k in range(s["need"])]
    n = len(slots)

    ends = [[] for _ in people]         # end times of each person's shifts, in the order placed (also time order)
    week_minutes = [{} for _ in people]
    worked = [{} for _ in people]       # day -> number of the person's shifts on it
    seats = {s["id"]: [] for s in jobs}
    seniors_on = {s["id"]: 0 for s in jobs}

    def candidates(i):
        s, k = slots[i]
        pool = by_skill.get(s["skill"], [])
        if k > 0:
            pool = pool[bisect_right(pool, seats[s["id"]][-1]):]
        week = s["week"]
        return sorted(pool, key=lambda q: week_minutes[q].get(week, 0))   # stable: ties stay in id order

    def fits(q, s, k):
        d0, d1 = s["first_day"], s["last_day"]
        off = unavailable[q]
        if any(d in off for d in range(d0, d1 + 1)):
            return False
        mine = ends[q]
        if mine:
            last_end = mine[-1]
            if last_end > s["start"]:
                return False
            if s["start"] - last_end < min_rest:
                return False
        if week_minutes[q].get(s["week"], 0) + s["length"] > caps[q]:
            return False
        days = worked[q]
        run = d1 - d0 + 1
        x = d0 - 1
        while x in days:
            run += 1
            x -= 1
        x = d1 + 1
        while x in days:
            run += 1
            x += 1
        if run > max_run:
            return False
        here = seats[s["id"]]
        if enemies[q] and any(r in enemies[q] for r in here):
            return False
        if k == s["need"] - 1 and s["needs_senior"] and not senior[q] and seniors_on[s["id"]] == 0:
            return False
        return True

    def place(q, s):
        seats[s["id"]].append(q)
        seniors_on[s["id"]] += senior[q]
        ends[q].append(s["end"])
        wm = week_minutes[q]
        wm[s["week"]] = wm.get(s["week"], 0) + s["length"]
        days = worked[q]
        for d in range(s["first_day"], s["last_day"] + 1):
            days[d] = days.get(d, 0) + 1

    def unplace(q, s):
        seats[s["id"]].pop()
        seniors_on[s["id"]] -= senior[q]
        ends[q].pop()
        week_minutes[q][s["week"]] -= s["length"]
        days = worked[q]
        for d in range(s["first_day"], s["last_day"] + 1):
            days[d] -= 1
            if days[d] == 0:
                del days[d]

    ok = True
    if n:
        lists, nxt, chosen = [None] * n, [0] * n, [0] * n
        lists[0] = candidates(0)
        i = 0
        while True:
            s, k = slots[i]
            lst, j = lists[i], nxt[i]
            placed = False
            while j < len(lst):
                q = lst[j]
                j += 1
                if fits(q, s, k):
                    place(q, s)
                    placed = True
                    break
            nxt[i] = j
            if placed:
                chosen[i] = q
                i += 1
                if i == n:
                    break
                lists[i] = candidates(i)
                nxt[i] = 0
            else:
                i -= 1
                if i < 0:
                    ok = False
                    break
                unplace(chosen[i], slots[i][0])

    minutes = {pid: 0 for pid in ids}
    assignments = {}
    if ok:
        for s in jobs:
            assignments[s["id"]] = [ids[q] for q in seats[s["id"]]]
            for q in seats[s["id"]]:
                minutes[ids[q]] += s["length"]
    return {"ok": ok, "assignments": assignments, "minutes": minutes, "ignored": ignored}
