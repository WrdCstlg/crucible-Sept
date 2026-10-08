import bisect
import collections
import datetime


def _is_valid_date(d):
    if not isinstance(d, str) or len(d) != 10:
        return False
    if d[4] != '-' or d[7] != '-':
        return False
    for i in (0, 1, 2, 3, 5, 6, 8, 9):
        if not ('0' <= d[i] <= '9'):
            return False
    try:
        y, m, day = int(d[:4]), int(d[5:7]), int(d[8:10])
        if not (1 <= y <= 9999):
            return False
        datetime.date(y, m, day)
        return True
    except ValueError:
        return False


def _parse_valid_timestamp(ts):
    if not isinstance(ts, str) or len(ts) != 16:
        return None
    if ts[10] != ' ' or ts[13] != ':':
        return None
    for i in (11, 12, 14, 15):
        if not ('0' <= ts[i] <= '9'):
            return None
    if not _is_valid_date(ts[:10]):
        return None
    try:
        y, m, day = int(ts[:4]), int(ts[5:7]), int(ts[8:10])
        h, mn = int(ts[11:13]), int(ts[14:16])
        if not (0 <= h <= 23 and 0 <= mn <= 59):
            return None
        return datetime.datetime(y, m, day, h, mn)
    except ValueError:
        return None


def _get_shift_dates(start_dt, end_dt):
    d1 = start_dt.date()
    d2 = end_dt.date()
    if d1 == d2:
        return (d1,)
    if end_dt.time() == datetime.time(0, 0):
        return (d1,)
    return (d1, d2)


class _Shift:
    __slots__ = ('id', 'start', 'end', 'skill', 'need', 'needs_senior', 'length', 'dates', 'week')

    def __init__(self, s_id, start_dt, end_dt, skill, need, needs_senior):
        self.id = s_id
        self.start = start_dt
        self.end = end_dt
        self.skill = skill
        self.need = need
        self.needs_senior = needs_senior
        self.length = int((end_dt - start_dt).total_seconds() // 60)
        self.dates = _get_shift_dates(start_dt, end_dt)
        self.week = start_dt.date() - datetime.timedelta(days=start_dt.weekday())


def make_roster(staff, shifts, rules):
    # 1. Validation: Staff
    ignored_staff_indices = set()
    initial_valid_staff = []

    for idx, r in enumerate(staff):
        if not isinstance(r, dict):
            ignored_staff_indices.add(idx)
            continue
        if not all(k in r for k in ("id", "skills", "max_minutes_week", "unavailable", "senior")):
            ignored_staff_indices.add(idx)
            continue

        r_id = r["id"]
        if not (isinstance(r_id, str) and len(r_id) > 0):
            ignored_staff_indices.add(idx)
            continue

        r_skills = r["skills"]
        if not (isinstance(r_skills, list) and all(isinstance(s, str) for s in r_skills)):
            ignored_staff_indices.add(idx)
            continue

        r_max = r["max_minutes_week"]
        if not (type(r_max) is int and r_max >= 0):
            ignored_staff_indices.add(idx)
            continue

        r_unav = r["unavailable"]
        if not (isinstance(r_unav, list) and all(_is_valid_date(d) for d in r_unav)):
            ignored_staff_indices.add(idx)
            continue

        r_sen = r["senior"]
        if type(r_sen) is not bool:
            ignored_staff_indices.add(idx)
            continue

        initial_valid_staff.append((idx, r))

    staff_id_counts = collections.Counter(r["id"] for _, r in initial_valid_staff)
    valid_staff_records = []
    for idx, r in initial_valid_staff:
        if staff_id_counts[r["id"]] > 1:
            ignored_staff_indices.add(idx)
        else:
            valid_staff_records.append(r)

    # 1. Validation: Shifts
    ignored_shift_indices = set()
    initial_valid_shifts = []

    for idx, r in enumerate(shifts):
        if not isinstance(r, dict):
            ignored_shift_indices.add(idx)
            continue
        if not all(k in r for k in ("id", "start", "end", "skill", "need", "needs_senior")):
            ignored_shift_indices.add(idx)
            continue

        r_id = r["id"]
        if not (isinstance(r_id, str) and len(r_id) > 0):
            ignored_shift_indices.add(idx)
            continue

        start_dt = _parse_valid_timestamp(r["start"])
        end_dt = _parse_valid_timestamp(r["end"])
        if start_dt is None or end_dt is None or end_dt <= start_dt:
            ignored_shift_indices.add(idx)
            continue

        duration = int((end_dt - start_dt).total_seconds() // 60)
        if duration > 1440:
            ignored_shift_indices.add(idx)
            continue

        r_skill = r["skill"]
        if not isinstance(r_skill, str):
            ignored_shift_indices.add(idx)
            continue

        r_need = r["need"]
        if not (type(r_need) is int and r_need >= 1):
            ignored_shift_indices.add(idx)
            continue

        r_sen = r["needs_senior"]
        if type(r_sen) is not bool:
            ignored_shift_indices.add(idx)
            continue

        initial_valid_shifts.append((idx, r, start_dt, end_dt))

    shift_id_counts = collections.Counter(r["id"] for _, r, _, _ in initial_valid_shifts)
    valid_shift_objects = []
    for idx, r, start_dt, end_dt in initial_valid_shifts:
        if shift_id_counts[r["id"]] > 1:
            ignored_shift_indices.add(idx)
        else:
            valid_shift_objects.append(_Shift(
                r["id"], start_dt, end_dt, r["skill"], r["need"], r["needs_senior"]
            ))

    ignored_out = {
        "staff": sorted(ignored_staff_indices),
        "shifts": sorted(ignored_shift_indices)
    }

    valid_staff_ids = {r["id"] for r in valid_staff_records}

    # If no valid shifts: empty roster with ok: True
    if not valid_shift_objects:
        return {
            "ok": True,
            "assignments": {},
            "minutes": {sid: 0 for sid in valid_staff_ids},
            "ignored": ignored_out
        }

    # Pre-process staff data
    staff_skills = {}
    staff_max_week = {}
    staff_unavail = {}
    staff_is_senior = {}

    for r in valid_staff_records:
        sid = r["id"]
        staff_skills[sid] = set(r["skills"])
        staff_max_week[sid] = r["max_minutes_week"]
        staff_unavail[sid] = {
            datetime.date(int(d[:4]), int(d[5:7]), int(d[8:10])) for d in r["unavailable"]
        }
        staff_is_senior[sid] = r["senior"]

    # Rules
    min_rest_minutes = rules["min_rest_minutes"]
    max_consecutive_days = rules["max_consecutive_days"]

    forbidden_with = collections.defaultdict(set)
    for p in rules.get("forbidden_pairs", []):
        id1, id2 = p[0], p[1]
        if id1 in valid_staff_ids and id2 in valid_staff_ids and id1 != id2:
            forbidden_with[id1].add(id2)
            forbidden_with[id2].add(id1)

    # Sort shifts ascending by (start, end, id)
    valid_shift_objects.sort(key=lambda s: (s.start, s.end, s.id))

    # Precompute eligible staff per shift (sorted by staff ID)
    shift_eligible = {}
    for s in valid_shift_objects:
        s_dates_set = set(s.dates)
        s_len = s.length
        s_skill = s.skill
        s_needs_senior = s.needs_senior
        s_need = s.need

        cands = []
        for sid in valid_staff_ids:
            if s_skill not in staff_skills[sid]:
                continue
            if s_dates_set & staff_unavail[sid]:
                continue
            if staff_max_week[sid] < s_len:
                continue
            if s_need == 1 and s_needs_senior and not staff_is_senior[sid]:
                continue
            cands.append(sid)

        cands.sort()
        shift_eligible[s.id] = cands

    # Create sorted slots: (shift, seat)
    slots = []
    for s in valid_shift_objects:
        for seat in range(s.need):
            slots.append((s, seat))

    num_slots = len(slots)

    # Search tracking state
    current_assignments = {s.id: [] for s in valid_shift_objects}
    week_staff_minutes = collections.defaultdict(dict)
    staff_total_minutes = {sid: 0 for sid in valid_staff_ids}
    staff_shifts = collections.defaultdict(list)
    staff_last_shift = {sid: None for sid in valid_staff_ids}
    staff_work_days = collections.defaultdict(dict)

    def check_consecutive_days(p_id, shift_dates):
        if len(shift_dates) == 2 and max_consecutive_days == 1:
            return False
        p_days = staff_work_days[p_id]
        if all(d in p_days for d in shift_dates):
            return True

        curr_date = shift_dates[-1]
        run = 0
        while True:
            if curr_date in p_days or curr_date in shift_dates:
                run += 1
                if run > max_consecutive_days:
                    return False
                curr_date -= datetime.timedelta(days=1)
            else:
                break
        return True

    def get_candidates(shift, seat):
        base_cands = shift_eligible[shift.id]
        if seat > 0:
            min_id = current_assignments[shift.id][-1]
            idx = bisect.bisect_right(base_cands, min_id)
            cands = base_cands[idx:]
        else:
            cands = list(base_cands)

        w_map = week_staff_minutes.get(shift.week)
        if w_map:
            cands.sort(key=lambda p: (w_map.get(p, 0), p))
        return cands

    # Iterative DFS stack
    # Stack entries: [shift, seat, cands, cand_idx]
    first_shift, first_seat = slots[0]
    stack = [[first_shift, first_seat, get_candidates(first_shift, first_seat), 0]]
    depth = 0

    while depth < num_slots:
        frame = stack[depth]
        shift, seat, cands, cand_idx = frame

        found = False
        while cand_idx < len(cands):
            p = cands[cand_idx]
            cand_idx += 1
            frame[3] = cand_idx

            # Rule 4: Weekly cap
            w = week_staff_minutes[shift.week].get(p, 0)
            if w + shift.length > staff_max_week[p]:
                continue

            # Rules 2 & 3: Overlap & Rest
            last_s = staff_last_shift[p]
            if last_s is not None:
                td = shift.start - last_s.end
                diff_m = td.days * 1440 + td.seconds // 60
                if diff_m < min_rest_minutes:
                    continue

            # Rule 5: Consecutive days
            if not check_consecutive_days(p, shift.dates):
                continue

            # Rule 7: Forbidden pairs (same shift)
            if seat > 0:
                p_forbid = forbidden_with[p]
                if any(q in p_forbid for q in current_assignments[shift.id]):
                    continue

            # Rule 8: Senior requirement (checked on last seat of shift)
            if shift.needs_senior and seat == shift.need - 1:
                if not staff_is_senior[p] and not any(staff_is_senior[q] for q in current_assignments[shift.id]):
                    continue

            # Candidate is acceptable! Apply assignment
            current_assignments[shift.id].append(p)
            week_staff_minutes[shift.week][p] = w + shift.length
            staff_total_minutes[p] += shift.length
            staff_shifts[p].append(shift)
            staff_last_shift[p] = shift

            p_wd = staff_work_days[p]
            for d in shift.dates:
                p_wd[d] = p_wd.get(d, 0) + 1

            found = True
            break

        if found:
            depth += 1
            if depth == num_slots:
                break
            next_shift, next_seat = slots[depth]
            stack.append([next_shift, next_seat, get_candidates(next_shift, next_seat), 0])
        else:
            # Backtrack
            stack.pop()
            depth -= 1
            if depth < 0:
                break

            prev_shift = slots[depth][0]
            p = current_assignments[prev_shift.id].pop()
            week_staff_minutes[prev_shift.week][p] -= prev_shift.length
            if week_staff_minutes[prev_shift.week][p] == 0:
                del week_staff_minutes[prev_shift.week][p]

            staff_total_minutes[p] -= prev_shift.length
            staff_shifts[p].pop()
            staff_last_shift[p] = staff_shifts[p][-1] if staff_shifts[p] else None

            p_wd = staff_work_days[p]
            for d in prev_shift.dates:
                p_wd[d] -= 1
                if p_wd[d] == 0:
                    del p_wd[d]

    if depth == num_slots:
        return {
            "ok": True,
            "assignments": current_assignments,
            "minutes": {sid: staff_total_minutes[sid] for sid in valid_staff_ids},
            "ignored": ignored_out
        }
    else:
        return {
            "ok": False,
            "assignments": {},
            "minutes": {sid: 0 for sid in valid_staff_ids},
            "ignored": ignored_out
        }