from bisect import bisect_left
from collections import defaultdict

LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}

VALID_EVENTS = {
    "OPEN",
    "PRIORITY",
    "PAUSE",
    "RESUME",
    "CLOSE",
    "REOPEN",
    "HOLIDAY",
}

STATUS_MAP = {
    "RUNNING": "running",
    "PAUSED": "paused",
    "CLOSED": "closed",
}


def _biz_minutes_in_day(mod):
    if mod <= 540:
        return 0
    elif mod < 1020:
        return mod - 540
    else:
        return 480


def compute_sla(stream):
    holiday_days = set()
    ticket_events = defaultdict(list)
    now = None
    stream_idx = 0

    # 1. Parse and validate stream
    for line in stream:
        raw = line.strip()
        if not raw:
            continue
        parts = raw.split(",")
        n = len(parts)
        if n not in (3, 4):
            continue

        f0 = parts[0].strip()
        if not f0 or not all("0" <= c <= "9" for c in f0):
            continue
        minute = int(f0)

        f1 = parts[1].strip()
        if not f1:
            continue

        f2 = parts[2].strip()
        if f2 not in VALID_EVENTS:
            continue

        if f2 == "HOLIDAY":
            if n != 3 or f1 != "*":
                continue
            holiday_days.add(minute // 1440)
        else:
            if f1 == "*":
                continue
            if f2 in ("OPEN", "PRIORITY"):
                if n != 4:
                    continue
                f3 = parts[3].strip()
                if f3 not in LIMITS:
                    continue
                priority = f3
            else:
                if n != 3:
                    continue
                priority = None

            if now is None or minute > now:
                now = minute
            ticket_events[f1].append((minute, stream_idx, f2, priority))
            stream_idx += 1

    if now is None:
        return []

    # 2. Build calendar lookup
    weekday_holidays = sorted(d for d in holiday_days if d % 7 < 5)
    weekday_holidays_set = set(weekday_holidays)

    def F(t):
        if t <= 0:
            return 0
        d = t // 1440
        mod = t % 1440
        weeks = d // 7
        rem_days = d % 7
        full_biz_days = weeks * 5 + min(rem_days, 5)
        day_biz = _biz_minutes_in_day(mod) if rem_days < 5 else 0
        reg = full_biz_days * 480 + day_biz

        idx = bisect_left(weekday_holidays, d)
        deduction = idx * 480
        if d in weekday_holidays_set:
            deduction += _biz_minutes_in_day(mod)
        return reg - deduction

    def find_breach_minute(t_start, t_end, target_F):
        lo = t_start
        hi = t_end
        while lo < hi:
            mid = (lo + hi) // 2
            if F(mid) >= target_F:
                hi = mid
            else:
                lo = mid + 1
        return lo

    # 3. Sweep events per ticket, rebuild running intervals, count business minutes
    results = []

    for tid, events in ticket_events.items():
        # Sort stably by minute
        events.sort(key=lambda x: (x[0], x[1]))

        # Group events by minute
        grouped_events = []
        cur_min = None
        cur_list = []
        for m, _, ev, p in events:
            if m != cur_min:
                if cur_min is not None:
                    grouped_events.append((cur_min, cur_list))
                cur_min = m
                cur_list = [(ev, p)]
            else:
                cur_list.append((ev, p))
        if cur_min is not None:
            grouped_events.append((cur_min, cur_list))

        state = "NOT_OPENED"
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        had_valid_open = False
        m_prev = None

        for m, ev_list in grouped_events:
            # Interval [m_prev, m)
            if m_prev is not None and m > m_prev:
                if state == "RUNNING":
                    delta_biz = F(m) - F(m_prev)
                    if not breached:
                        L = LIMITS[priority]
                        k = L + 1 - used_minutes
                        if delta_biz >= k:
                            t_breach = find_breach_minute(m_prev, m, F(m_prev) + k)
                            if t_breach < m:
                                breached = True
                                breached_at = t_breach
                    used_minutes += delta_biz

            m_prev = m

            # Apply events at minute m in stream order
            for ev, p in ev_list:
                if ev == "OPEN":
                    if state in ("NOT_OPENED", "CLOSED"):
                        state = "RUNNING"
                        priority = p
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif ev == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        priority = p
                elif ev == "PAUSE":
                    if state == "RUNNING":
                        state = "PAUSED"
                elif ev == "RESUME":
                    if state == "PAUSED":
                        state = "RUNNING"
                elif ev == "CLOSE":
                    if state in ("RUNNING", "PAUSED"):
                        state = "CLOSED"
                elif ev == "REOPEN":
                    if state == "CLOSED":
                        state = "RUNNING"

            # Check breach at minute m after all events at m have been applied
            if had_valid_open and state != "NOT_OPENED":
                if not breached and used_minutes > LIMITS[priority]:
                    breached = True
                    breached_at = m

        # Final interval [m_prev, now)
        if m_prev is not None and now > m_prev:
            if state == "RUNNING":
                delta_biz = F(now) - F(m_prev)
                if not breached:
                    L = LIMITS[priority]
                    k = L + 1 - used_minutes
                    if delta_biz >= k:
                        t_breach = find_breach_minute(m_prev, now, F(m_prev) + k)
                        if t_breach <= now:
                            breached = True
                            breached_at = t_breach
                used_minutes += delta_biz

        if had_valid_open:
            results.append({
                "ticket_id": tid,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": STATUS_MAP[state],
            })

    results.sort(key=lambda d: d["ticket_id"])
    return results