from datetime import datetime, timedelta
from fractions import Fraction

_ASCII_DIGITS = set("0123456789")


def _parse_timestamp(s):
    if not isinstance(s, str) or len(s) != 16:
        return None
    if s[4] != "-" or s[7] != "-" or s[10] != " " or s[13] != ":":
        return None
    digit_indices = (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15)
    if not all(s[i] in _ASCII_DIGITS for i in digit_indices):
        return None
    year = int(s[0:4])
    month = int(s[5:7])
    day = int(s[8:10])
    hour = int(s[11:13])
    minute = int(s[14:16])
    if year < 1 or year > 9999:
        return None
    if hour < 0 or hour > 23:
        return None
    if minute < 0 or minute > 59:
        return None
    try:
        return datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def _round_timestamp(dt):
    q = dt.minute % 15
    if q <= 7:
        return dt - timedelta(minutes=q)
    else:
        return dt + timedelta(minutes=(15 - q))


def _round_half_up(val: Fraction) -> int:
    return (2 * val.numerator + val.denominator) // (2 * val.denominator)


def compute_pay(punches, rate):
    ignored = []
    valid_punches = []

    # Step 1: Parse & Step 2: Round
    for idx, punch in enumerate(punches):
        if not (isinstance(punch, (list, tuple)) and len(punch) == 2):
            ignored.append(idx)
            continue

        in_str, out_str = punch[0], punch[1]
        in_dt = _parse_timestamp(in_str)
        out_dt = _parse_timestamp(out_str)

        if in_dt is None or out_dt is None or out_dt <= in_dt:
            ignored.append(idx)
            continue

        rin = _round_timestamp(in_dt)
        rout = _round_timestamp(out_dt)

        if rout <= rin:
            ignored.append(idx)
            continue

        valid_punches.append(
            {
                "index": idx,
                "rounded_in": rin,
                "rounded_out": rout,
                "length": int((rout - rin).total_seconds() // 60),
            }
        )

    # Step 3: Overlaps
    valid_punches.sort(key=lambda p: (p["rounded_in"], p["rounded_out"], p["index"]))

    shifts = []
    last_out = None
    for p in valid_punches:
        if last_out is None or p["rounded_in"] >= last_out:
            shifts.append(p)
            last_out = p["rounded_out"]
        else:
            ignored.append(p["index"])

    ignored.sort()

    if not shifts:
        return {"weeks": [], "ignored": ignored}

    # Step 4: Days & Step 5: Weeks
    shifts_by_date = {}
    for s in shifts:
        s_date = s["rounded_in"].date()
        shifts_by_date.setdefault(s_date, []).append(s)

    week_starts = set()
    for s_date in shifts_by_date:
        monday = s_date - timedelta(days=s_date.weekday())
        week_starts.add(monday)

    sorted_week_starts = sorted(week_starts)
    weeks_output = []

    for monday in sorted_week_starts:
        days_in_week = [monday + timedelta(days=i) for i in range(7)]
        worked_per_day = [
            sum(s["length"] for s in shifts_by_date.get(d, []))
            for d in days_in_week
        ]

        # Step 6: Daily classification
        is_seventh_day = all(w > 0 for w in worked_per_day)
        daily_classifications = []
        for i in range(7):
            w = worked_per_day[i]
            if i == 6 and is_seventh_day:
                d_reg = 0
                d_ot = min(w, 480)
                d_dt = max(0, w - 480)
            else:
                d_reg = min(w, 480)
                d_ot = min(max(0, w - 480), 240)
                d_dt = max(0, w - 720)
            daily_classifications.append((d_reg, d_ot, d_dt))

        # Step 7: Weekly overtime
        running_reg = 0
        week_reg = 0
        week_ot = 0
        week_dt = 0
        for i in range(7):
            d_reg, d_ot, d_dt = daily_classifications[i]
            if running_reg + d_reg <= 2400:
                reg = d_reg
                ot = d_ot
                running_reg += d_reg
            else:
                reg = max(0, 2400 - running_reg)
                ot = d_ot + (d_reg - reg)
                running_reg = 2400
            dt = d_dt

            week_reg += reg
            week_ot += ot
            week_dt += dt

        # Step 8: Meal penalty
        week_penalties = 0
        for d in days_in_week:
            d_shifts = shifts_by_date.get(d, [])
            if any(s["length"] > 300 for s in d_shifts):
                week_penalties += 1

        # Step 9: Pay
        reg_pay = _round_half_up(Fraction(week_reg * rate, 60))
        ot_pay = _round_half_up(Fraction(week_ot * rate * 3, 120))
        dt_pay = _round_half_up(Fraction(week_dt * rate * 2, 60))
        meal_pay = week_penalties * rate
        total_pay = reg_pay + ot_pay + dt_pay + meal_pay

        weeks_output.append(
            {
                "week_start": monday.strftime("%Y-%m-%d"),
                "regular_minutes": week_reg,
                "overtime_minutes": week_ot,
                "double_minutes": week_dt,
                "meal_penalties": week_penalties,
                "regular_pay": reg_pay,
                "overtime_pay": ot_pay,
                "double_pay": dt_pay,
                "meal_pay": meal_pay,
                "total_pay": total_pay,
            }
        )

    return {"weeks": weeks_output, "ignored": ignored}