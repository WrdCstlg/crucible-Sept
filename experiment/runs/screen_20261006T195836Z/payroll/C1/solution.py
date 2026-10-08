from datetime import date

_DIGITS = "0123456789"
_DIGIT_POSITIONS = (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15)


def _parse(s):
    """Parse 'YYYY-MM-DD HH:MM' into absolute minutes (date ordinal * 1440 + minute of day).

    Returns None if the timestamp is invalid.
    """
    if not isinstance(s, str) or len(s) != 16:
        return None
    if s[4] != "-" or s[7] != "-" or s[10] != " " or s[13] != ":":
        return None
    for i in _DIGIT_POSITIONS:
        if s[i] not in _DIGITS:
            return None
    y = int(s[0:4])
    mo = int(s[5:7])
    d = int(s[8:10])
    h = int(s[11:13])
    mi = int(s[14:16])
    if h > 23 or mi > 59:
        return None
    try:
        ordn = date(y, mo, d).toordinal()
    except (ValueError, OverflowError):
        return None
    return ordn * 1440 + h * 60 + mi


def _round_quarter(t):
    q = t % 15
    if q <= 7:
        return t - q
    return t + (15 - q)


def _half_up_div(n, d):
    # n >= 0, d > 0: round n/d half up
    return (2 * n + d) // (2 * d)


def compute_pay(punches, rate):
    ignored = []
    candidates = []  # (rin, rout, idx)

    for idx, punch in enumerate(punches):
        try:
            if len(punch) != 2:
                ignored.append(idx)
                continue
            s_in, s_out = punch[0], punch[1]
        except TypeError:
            ignored.append(idx)
            continue
        t_in = _parse(s_in)
        t_out = _parse(s_out)
        if t_in is None or t_out is None or t_out <= t_in:
            ignored.append(idx)
            continue
        r_in = _round_quarter(t_in)
        r_out = _round_quarter(t_out)
        if r_out <= r_in:
            ignored.append(idx)
            continue
        candidates.append((r_in, r_out, idx))

    candidates.sort()
    shifts = []
    last_out = None
    for r_in, r_out, idx in candidates:
        if last_out is None or r_in >= last_out:
            shifts.append((r_in, r_out))
            last_out = r_out
        else:
            ignored.append(idx)

    # Days: ordinal -> worked minutes, meal flag
    day_worked = {}
    day_meal = {}
    for r_in, r_out in shifts:
        day = r_in // 1440
        length = r_out - r_in
        day_worked[day] = day_worked.get(day, 0) + length
        if length > 300:
            day_meal[day] = True
        else:
            day_meal.setdefault(day, False)

    # Weeks: Monday ordinal -> list of day ordinals
    weeks = {}
    for day in day_worked:
        monday = day - ((day - 1) % 7)  # ordinal 1 (0001-01-01) is a Monday
        weeks.setdefault(monday, []).append(day)

    result_weeks = []
    for monday in sorted(weeks):
        all_seven = all(day_worked.get(monday + k, 0) > 0 for k in range(7))
        R = O = D = 0
        N = 0
        running_regular = 0
        for k in range(7):
            day = monday + k
            w = day_worked.get(day, 0)
            if w <= 0:
                continue
            if k == 6 and all_seven:
                reg = 0
                ot = min(w, 480)
                dt = max(w - 480, 0)
            else:
                reg = min(w, 480)
                ot = min(max(w - 480, 0), 240)
                dt = max(w - 720, 0)
            # weekly overtime
            allowed = max(2400 - running_regular, 0)
            if reg > allowed:
                ot += reg - allowed
                reg = allowed
            running_regular += reg
            R += reg
            O += ot
            D += dt
            if day_meal.get(day, False):
                N += 1

        regular_pay = _half_up_div(R * rate, 60)
        overtime_pay = _half_up_div(O * rate * 3, 120)
        double_pay = _half_up_div(D * rate * 2, 60)
        meal_pay = N * rate
        total_pay = regular_pay + overtime_pay + double_pay + meal_pay

        md = date.fromordinal(monday)
        week_start = "%04d-%02d-%02d" % (md.year, md.month, md.day)
        result_weeks.append({
            "week_start": week_start,
            "regular_minutes": R,
            "overtime_minutes": O,
            "double_minutes": D,
            "meal_penalties": N,
            "regular_pay": regular_pay,
            "overtime_pay": overtime_pay,
            "double_pay": double_pay,
            "meal_pay": meal_pay,
            "total_pay": total_pay,
        })

    ignored.sort()
    return {"weeks": result_weeks, "ignored": ignored}