"""Reference for Problem 10 (timesheet to payroll). Stdlib only; exact integer money."""
from datetime import date, datetime, timedelta

DIGITS = set("0123456789")


def parse(ts):
    if type(ts) is not str or len(ts) != 16 or ts[4] != "-" or ts[7] != "-" or ts[10] != " " or ts[13] != ":":
        return None
    parts = (ts[0:4], ts[5:7], ts[8:10], ts[11:13], ts[14:16])
    if not all(set(p) <= DIGITS for p in parts):
        return None
    y, mo, d, h, mi = (int(p) for p in parts)
    if h > 23 or mi > 59:
        return None
    try:
        return datetime(y, mo, d, h, mi)
    except ValueError:
        return None


def round_quarter(t):
    q = t.minute % 15
    base = t - timedelta(minutes=q)
    return base if q <= 7 else base + timedelta(minutes=15)


def half_up(num, den):
    """round(num / den) with halves going up, for num >= 0, den > 0."""
    return (2 * num + den) // (2 * den)


def compute_pay(punches, rate):
    ignored = []
    candidates = []
    for idx, pair in enumerate(punches):
        a, b = parse(pair[0]), parse(pair[1])
        if a is None or b is None or b <= a:
            ignored.append(idx)
            continue
        ra, rb = round_quarter(a), round_quarter(b)
        if rb <= ra:
            ignored.append(idx)
            continue
        candidates.append((ra, rb, idx))
    candidates.sort()
    shifts = []
    last_out = None
    for ra, rb, idx in candidates:
        if last_out is not None and ra < last_out:
            ignored.append(idx)
            continue
        shifts.append((ra, rb))
        last_out = rb

    worked, meal = {}, set()
    for ra, rb in shifts:
        day = ra.date()
        minutes = int((rb - ra).total_seconds() // 60)
        worked[day] = worked.get(day, 0) + minutes
        if minutes > 300:
            meal.add(day)

    weeks = {}
    for day in worked:
        weeks.setdefault(day - timedelta(days=day.weekday()), []).append(day)

    out = []
    for monday in sorted(weeks):
        days = [monday + timedelta(days=k) for k in range(7)]
        seventh = all(worked.get(d, 0) > 0 for d in days)
        reg_total = ot = dt = 0
        for d in days:
            w = worked.get(d, 0)
            if w == 0:
                continue
            if seventh and d == days[6]:
                reg, o, x = 0, min(w, 480), max(0, w - 480)
            else:
                reg, o, x = min(w, 480), min(max(0, w - 480), 240), max(0, w - 720)
            allowed = max(0, 2400 - reg_total)
            moved = max(0, reg - allowed)
            reg_total += reg - moved
            ot += o + moved
            dt += x
        penalties = sum(1 for d in days if d in meal)
        regular_pay = half_up(reg_total * rate, 60)
        overtime_pay = half_up(ot * rate * 3, 120)
        double_pay = half_up(dt * rate * 2, 60)
        meal_pay = penalties * rate
        out.append({"week_start": monday.isoformat(), "regular_minutes": reg_total, "overtime_minutes": ot,
                    "double_minutes": dt, "meal_penalties": penalties, "regular_pay": regular_pay,
                    "overtime_pay": overtime_pay, "double_pay": double_pay, "meal_pay": meal_pay,
                    "total_pay": regular_pay + overtime_pay + double_pay + meal_pay})
    return {"weeks": out, "ignored": sorted(ignored)}
