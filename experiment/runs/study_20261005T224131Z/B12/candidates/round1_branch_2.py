from bisect import bisect_left, bisect_right
from collections import defaultdict

LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}

VALID_EVENTS_3 = {'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'}
VALID_EVENTS_4 = {'OPEN', 'PRIORITY'}
VALID_PRIORITIES = {'P1', 'P2', 'P3', 'P4'}


def _raw_business_minutes_before(t):
    if t <= 0:
        return 0
    weeks = t // 10080
    rem = t % 10080
    day = rem // 1440
    min_in_day = rem % 1440
    ans = weeks * 2400 + min(day, 5) * 480
    if day < 5:
        ans += max(0, min(min_in_day, 1020) - 540)
    return ans


def _count_business_minutes(t1, t2, holiday_list, holiday_set):
    if t1 >= t2:
        return 0
    raw = _raw_business_minutes_before(t2) - _raw_business_minutes_before(t1)
    if not holiday_set:
        return raw

    d_left = t1 // 1440
    d_right = t2 // 1440
    hol_overlap = 0

    if d_left == d_right:
        if d_left in holiday_set:
            h_start = d_left * 1440 + 540
            h_end = d_left * 1440 + 1020
            hol_overlap = max(0, min(t2, h_end) - max(t1, h_start))
    else:
        if d_left in holiday_set:
            h_start = d_left * 1440 + 540
            h_end = d_left * 1440 + 1020
            hol_overlap += max(0, min(t2, h_end) - max(t1, h_start))
        if d_right in holiday_set:
            h_start = d_right * 1440 + 540
            h_end = d_right * 1440 + 1020
            hol_overlap += max(0, min(t2, h_end) - max(t1, h_start))

        count = bisect_left(holiday_list, d_right) - bisect_right(holiday_list, d_left)
        if count > 0:
            hol_overlap += count * 480

    return raw - hol_overlap


def _find_breach_minute(run_start, run_end, target_needed, holiday_list, holiday_set):
    low = run_start + 1
    high = run_end
    while low < high:
        mid = (low + high) // 2
        if _count_business_minutes(run_start, mid, holiday_list, holiday_set) >= target_needed:
            high = mid
        else:
            low = mid + 1
    return low


def compute_sla(stream):
    holiday_days = set()
    ticket_events = []
    stream_idx = 0

    for line in stream:
        s = line.strip()
        parts = s.split(',')
        n = len(parts)
        if n not in (3, 4):
            continue

        f0 = parts[0].strip()
        if not (f0 and f0.isascii() and f0.isdigit()):
            continue
        minute = int(f0)

        f1 = parts[1].strip()
        if not f1:
            continue

        f2 = parts[2].strip()

        if n == 4:
            if f2 not in VALID_EVENTS_4:
                continue
            f3 = parts[3].strip()
            if f3 not in VALID_PRIORITIES:
                continue
            if f1 == '*':
                continue
            ticket_events.append((minute, stream_idx, f1, f2, f3))
            stream_idx += 1
        else:  # n == 3
            if f2 not in VALID_EVENTS_3:
                continue
            if f2 == 'HOLIDAY':
                if f1 != '*':
                    continue
                holiday_days.add(minute // 1440)
            else:
                if f1 == '*':
                    continue
                ticket_events.append((minute, stream_idx, f1, f2, None))
                stream_idx += 1

    if not ticket_events:
        return []

    now = max(ev[0] for ev in ticket_events)

    weekday_holidays = {d for d in holiday_days if d % 7 < 5}
    holiday_list = sorted(weekday_holidays)

    tickets_map = defaultdict(list)
    for minute, s_idx, ticket_id, event_type, priority in ticket_events:
        tickets_map[ticket_id].append((minute, s_idx, event_type, priority))

    result = []

    for ticket_id in sorted(tickets_map.keys()):
        raw_events = tickets_map[ticket_id]
        raw_events.sort(key=lambda x: (x[0], x[1]))

        events_by_minute = []
        for ev in raw_events:
            if not events_by_minute or events_by_minute[-1][0] != ev[0]:
                events_by_minute.append((ev[0], [(ev[2], ev[3])]))
            else:
                events_by_minute[-1][1].append((ev[2], ev[3]))

        state = 'NOT_OPENED'
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        had_valid_open = False
        last_m = None

        for m, m_events in events_by_minute:
            if state == 'RUNNING':
                biz = _count_business_minutes(last_m, m, holiday_list, weekday_holidays)
                if not breached:
                    lim = LIMITS[priority]
                    if used_minutes + biz > lim:
                        target = lim + 1 - used_minutes
                        ans_t = _find_breach_minute(last_m, m, target, holiday_list, weekday_holidays)
                        if ans_t < m:
                            breached = True
                            breached_at = ans_t
                used_minutes += biz

            last_m = m

            for ev_type, ev_prio in m_events:
                if ev_type == 'OPEN':
                    if state == 'NOT_OPENED':
                        state = 'RUNNING'
                        priority = ev_prio
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                    elif state == 'CLOSED':
                        state = 'RUNNING'
                        priority = ev_prio
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif ev_type == 'PRIORITY':
                    if state in ('RUNNING', 'PAUSED'):
                        priority = ev_prio
                elif ev_type == 'PAUSE':
                    if state == 'RUNNING':
                        state = 'PAUSED'
                elif ev_type == 'RESUME':
                    if state == 'PAUSED':
                        state = 'RUNNING'
                elif ev_type == 'CLOSE':
                    if state in ('RUNNING', 'PAUSED'):
                        state = 'CLOSED'
                elif ev_type == 'REOPEN':
                    if state == 'CLOSED':
                        state = 'RUNNING'

            if had_valid_open and not breached and priority is not None:
                if used_minutes > LIMITS[priority]:
                    breached = True
                    breached_at = m

        if last_m is not None and last_m < now:
            if state == 'RUNNING':
                biz = _count_business_minutes(last_m, now, holiday_list, weekday_holidays)
                if not breached:
                    lim = LIMITS[priority]
                    if used_minutes + biz > lim:
                        target = lim + 1 - used_minutes
                        ans_t = _find_breach_minute(last_m, now, target, holiday_list, weekday_holidays)
                        if ans_t <= now:
                            breached = True
                            breached_at = ans_t
                used_minutes += biz

        if had_valid_open:
            result.append({
                "ticket_id": ticket_id,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": state.lower(),
            })

    return result