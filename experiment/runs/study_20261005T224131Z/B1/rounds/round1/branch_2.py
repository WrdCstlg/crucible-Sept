from bisect import bisect_left
from collections import defaultdict

PRIORITY_LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}

STATUS_MAP = {
    1: 'running',
    2: 'paused',
    3: 'closed',
}


def parse_record(raw_line):
    line = raw_line.strip()
    if not line:
        return None
    parts = line.split(',')
    if len(parts) not in (3, 4):
        return None
    p0 = parts[0].strip()
    if not p0 or not p0.isascii() or not p0.isdigit():
        return None
    m = int(p0)
    tid = parts[1].strip()
    if not tid:
        return None
    ev = parts[2].strip()
    if ev in ('OPEN', 'PRIORITY'):
        if len(parts) != 4:
            return None
        prio = parts[3].strip()
        if prio not in ('P1', 'P2', 'P3', 'P4'):
            return None
        if tid == '*':
            return None
        return (m, tid, ev, prio)
    elif ev in ('PAUSE', 'RESUME', 'CLOSE', 'REOPEN'):
        if len(parts) != 3:
            return None
        if tid == '*':
            return None
        return (m, tid, ev, None)
    elif ev == 'HOLIDAY':
        if len(parts) != 3:
            return None
        if tid != '*':
            return None
        return (m, '*', ev, None)
    else:
        return None


def raw_business_minutes(m):
    w = m // 10080
    rem = m % 10080
    d_rem = rem // 1440
    mod = rem % 1440
    ans = w * 2400
    if d_rem >= 5:
        ans += 2400
    else:
        ans += d_rem * 480
        if mod > 540:
            ans += min(mod, 1020) - 540
    return ans


def count_business_minutes(A, B, h_days, h_set):
    if A >= B:
        return 0
    dA = A // 1440
    dB = B // 1440
    if dA == dB:
        if dA in h_set or dA % 7 >= 5:
            return 0
        s = max(A, dA * 1440 + 540)
        e = min(B, dA * 1440 + 1020)
        return max(0, e - s)

    raw = raw_business_minutes(B) - raw_business_minutes(A)

    idx1 = bisect_left(h_days, dA + 1)
    idx2 = bisect_left(h_days, dB)
    if idx2 > idx1:
        raw -= (idx2 - idx1) * 480

    if dA in h_set and dA % 7 < 5:
        s = max(A, dA * 1440 + 540)
        e = dA * 1440 + 1020
        if e > s:
            raw -= (e - s)

    if dB in h_set and dB % 7 < 5:
        s = dB * 1440 + 540
        e = min(B, dB * 1440 + 1020)
        if e > s:
            raw -= (e - s)

    return raw


def find_kth_business_minute(A, B, k, h_days, h_set):
    low = A
    high = B - 1
    ans = high
    while low <= high:
        mid = (low + high) // 2
        if count_business_minutes(A, mid + 1, h_days, h_set) >= k:
            ans = mid
            high = mid - 1
        else:
            low = mid + 1
    return ans


def compute_sla(stream):
    holidays = set()
    ticket_events = defaultdict(list)
    now = None

    stream_idx = 0
    for line in stream:
        rec = parse_record(line)
        if rec is None:
            stream_idx += 1
            continue
        m, tid, ev, prio = rec
        if ev == 'HOLIDAY':
            holidays.add(m // 1440)
        else:
            if now is None or m > now:
                now = m
            ticket_events[tid].append((m, stream_idx, ev, prio))
        stream_idx += 1

    if now is None:
        return []

    h_set = holidays
    h_days = sorted(d for d in holidays if d % 7 < 5)

    results = []

    for tid in sorted(ticket_events.keys()):
        events = ticket_events[tid]
        events.sort(key=lambda x: (x[0], x[1]))

        grouped_events = []
        current_m = None
        current_group = []
        for m, s_idx, ev, prio in events:
            if m != current_m:
                if current_group:
                    grouped_events.append((current_m, current_group))
                current_m = m
                current_group = [(ev, prio)]
            else:
                current_group.append((ev, prio))
        if current_group:
            grouped_events.append((current_m, current_group))

        state = 0  # 0: NOT_OPENED, 1: RUNNING, 2: PAUSED, 3: CLOSED
        priority = None
        had_valid_open = False
        session_elements = []
        m_prev = None

        for m, ev_list in grouped_events:
            if had_valid_open:
                if state == 1 and m > m_prev:
                    session_elements.append(('RUN', m_prev, m, priority))

            for ev, prio in ev_list:
                if ev == 'OPEN':
                    if state == 0 or state == 3:
                        state = 1
                        priority = prio
                        had_valid_open = True
                        session_elements.clear()
                elif ev == 'PRIORITY':
                    if state in (1, 2):
                        priority = prio
                elif ev == 'PAUSE':
                    if state == 1:
                        state = 2
                elif ev == 'RESUME':
                    if state == 2:
                        state = 1
                elif ev == 'CLOSE':
                    if state in (1, 2):
                        state = 3
                elif ev == 'REOPEN':
                    if state == 3:
                        state = 1

            if had_valid_open:
                session_elements.append(('CHECK', m, priority))
                m_prev = m

        if had_valid_open:
            if m_prev < now:
                if state == 1:
                    session_elements.append(('RUN', m_prev, now, priority))
                session_elements.append(('CHECK', now, priority))

        if not had_valid_open:
            continue

        used_time = 0
        breached = False
        breached_at = None

        for elem in session_elements:
            if elem[0] == 'RUN':
                _, start, end, prio = elem
                b = count_business_minutes(start, end, h_days, h_set)
                if b > 0:
                    if not breached:
                        lim = PRIORITY_LIMITS[prio]
                        if used_time + b > lim:
                            k = lim + 1 - used_time
                            x = find_kth_business_minute(start, end, k, h_days, h_set)
                            t = x + 1
                            if t < end:
                                breached = True
                                breached_at = t
                    used_time += b
            elif elem[0] == 'CHECK':
                _, m_chk, prio = elem
                if not breached:
                    lim = PRIORITY_LIMITS[prio]
                    if used_time > lim:
                        breached = True
                        breached_at = m_chk

        results.append({
            "ticket_id": tid,
            "priority": priority,
            "used_minutes": used_time,
            "breached": breached,
            "breached_at": breached_at,
            "status": STATUS_MAP[state],
        })

    return results