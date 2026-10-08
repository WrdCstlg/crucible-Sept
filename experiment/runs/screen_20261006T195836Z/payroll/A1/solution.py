from collections import defaultdict
from datetime import datetime, timedelta
from fractions import Fraction


def _parse_timestamp(s):
    if not isinstance(s, str) or len(s) != 16:
        return None
    if s[4] != "-" or s[7] != "-" or s[10] != " " or s[13] != ":":
        return None
    for i in (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15):
        if not ("0" <= s[i] <= "9"):
            return None
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _round_timestamp(dt: datetime) -> datetime:
    q = dt.minute % 15
    if q <= 7:
        return dt - timedelta(minutes=q)
    else:
        return dt + timedelta(minutes=15 - q)


def _round_half_up(val: Fraction) -> int:
    return (2 * val.numerator + val.denominator) // (2 * val.denominator)


def compute_pay(punches, rate):
    valid_punches = []

    # Step 1 & 2: Parse and Round
    for idx, punch in enumerate(punches):
        if not isinstance(punch, (list, tuple)) or len(punch) != 2:
            continue
        dt_in = _parse_timestamp(punch[0])
        dt_out = _parse_timestamp(punch[1])
        if dt_in is None or dt_out is None or dt_out <= dt_in:
            continue

        rnd_in = _round_timestamp(dt_in)
        rnd_out = _round_timestamp(dt_out)
        if rnd_out <= rnd_in:
            continue

        valid_punches.append((rnd_in, rnd_out, idx))

    # Step 3: Overlaps
    valid_punches.sort(key=lambda p: (p[0], p[1], p[2]))

    shifts = []
    last_kept_out = None
    for rnd_in, rnd_out, idx in valid_punches:
        if last_kept_out is None or rnd_in >= last_kept_out:
            shifts.append((rnd_in, rnd_out, idx))
            last_kept_out = rnd_out

    kept_indices = {s[2] for s in shifts}
    ignored = [i for i in range(len(punches)) if i not in kept_indices]

    # Step 4 & 5: Group shifts by week and day
    weeks_map = defaultdict(lambda: defaultdict(list))
    for rnd_in, rnd_out, _ in shifts:
        shift_date = rnd_in.date()
        week_monday = shift_date - timedelta(days=shift_date.weekday())
        weeks_map[week_monday][shift_date].append((rnd_in, rnd_out))

    weeks_result = []

    for week_monday in sorted(weeks_map.keys()):
        daily_shifts = []
        for d in range(7):
            cur_date = week_monday + timedelta(days=d)
            daily_shifts.append(weeks_map[week_monday].get(cur_date, []))

        # Shift lengths and meal penalties per day
        all_worked_minutes = []
        daily_meal_penalties = []
        for d in range(7):
            lengths = [
                int((s[1] - s[0]).total_seconds() // 60) for s in daily_shifts[d]
            ]
            all_worked_minutes.append(sum(lengths))
            daily_meal_penalties.append(1 if any(l > 300 for l in lengths) else 0)

        # Step 6: Daily classification
        is_seventh_day = all(w > 0 for w in all_worked_minutes)
        daily_reg = [0] * 7
        daily_ot = [0] * 7
        daily_dt = [0] * 7

        for d in range(7):
            w = all_worked_minutes[d]
            if d == 6 and is_seventh_day:
                daily_reg[d] = 0
                daily_ot[d] = min(w, 480)
                daily_dt[d] = max(0, w - 480)
            else:
                daily_reg[d] = min(w, 480)
                daily_ot[d] = max(0, min(w - 480, 240))
                daily_dt[d] = max(0, w - 720)

        # Step 7: Weekly overtime
        running_reg = 0
        for d in range(7):
            r = daily_reg[d]
            if running_reg + r <= 2400:
                running_reg += r
            else:
                keep = max(0, 2400 - running_reg)
                excess = r - keep
                daily_reg[d] = keep
                daily_ot[d] += excess
                running_reg = 2400

        # Minute totals
        r_total = sum(daily_reg)
        o_total = sum(daily_ot)
        d_total = sum(daily_dt)
        meal_total = sum(daily_meal_penalties)

        # Step 9: Pay
        reg_pay = _round_half_up(Fraction(r_total * rate, 60))
        ot_pay = _round_half_up(Fraction(o_total * rate, 40))
        dt_pay = _round_half_up(Fraction(d_total * rate, 30))
        meal_pay = meal_total * rate
        total_pay = reg_pay + ot_pay + dt_pay + meal_pay

        weeks_result.append(
            {
                "week_start": week_monday.strftime("%Y-%m-%d"),
                "regular_minutes": r_total,
                "overtime_minutes": o_total,
                "double_minutes": d_total,
                "meal_penalties": meal_total,
                "regular_pay": reg_pay,
                "overtime_pay": ot_pay,
                "double_pay": dt_pay,
                "meal_pay": meal_pay,
                "total_pay": total_pay,
            }
        )

    return {"weeks": weeks_result, "ignored": ignored}