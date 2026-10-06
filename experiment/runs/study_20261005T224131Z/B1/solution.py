import bisect
from collections import defaultdict


def compute_sla(stream):
    ticket_events = []
    holiday_days = set()

    # 1. Parse and validate stream
    for idx, raw_line in enumerate(stream):
        line = raw_line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) not in (3, 4):
            continue

        m_str, tid, ev = parts[0], parts[1], parts[2]
        if not m_str or not all(c in "0123456789" for c in m_str):
            continue
        minute = int(m_str)

        if not tid:
            continue

        if ev not in (
            "OPEN",
            "PRIORITY",
            "PAUSE",
            "RESUME",
            "CLOSE",
            "REOPEN",
            "HOLIDAY",
        ):
            continue

        if ev in ("OPEN", "PRIORITY"):
            if len(parts) != 4:
                continue
            p = parts[3]
            if p not in ("P1", "P2", "P3", "P4"):
                continue
        else:
            if len(parts) != 3:
                continue
            p = None

        if ev == "HOLIDAY":
            if tid != "*":
                continue
            d = minute // 1440
            if d % 7 < 5:
                holiday_days.add(d)
        else:
            if tid == "*":
                continue
            ticket_events.append((minute, idx, tid, ev, p))

    if not ticket_events:
        return []

    now = max(ev[0] for ev in ticket_events)

    # 2. Closed-form calendar arithmetic setup
    h_set = holiday_days
    h_list = sorted(h_set)

    def bd_raw(d):
        return (d // 7) * 5 + min(d % 7, 5)

    def bd(d):
        if d <= 0:
            return 0
        h_count = bisect.bisect_left(h_list, d)
        return bd_raw(d) - h_count

    def B(t):
        if t <= 0:
            return 0
        d = t // 1440
        mod = t % 1440
        res = bd(d) * 480
        if (d % 7 < 5) and (d not in h_set):
            if mod > 540:
                if mod < 1020:
                    res += mod - 540
                else:
                    res += 480
        return res

    def invert_B(Y):
        bd_index = (Y - 1) // 480
        bm_index = (Y - 1) % 480

        low = (bd_index // 5) * 7 + (bd_index % 5) + 1
        high = low + len(h_list) * 3 + 10
        target = bd_index + 1
        while low < high:
            mid = (low + high) // 2
            if bd(mid) >= target:
                high = mid
            else:
                low = mid + 1
        D = low - 1
        mod = 540 + bm_index + 1
        return D * 1440 + mod

    limits = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}

    # 3. Group events by ticket
    tickets_map = defaultdict(list)
    for minute, idx, tid, ev, p in ticket_events:
        tickets_map[tid].append((minute, idx, ev, p))

    results = []

    # 4. Advance each ticket using its per-ticket state machine
    for tid in sorted(tickets_map.keys()):
        ev_list = tickets_map[tid]
        ev_list.sort(key=lambda x: (x[0], x[1]))

        # Group events by minute
        grouped = []
        for minute, idx, ev, p in ev_list:
            if not grouped or grouped[-1][0] != minute:
                grouped.append((minute, [(ev, p)]))
            else:
                grouped[-1][1].append((ev, p))

        state = "NOT_OPENED"
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        had_valid_open = False
        last_t = None

        for m, events_at_m in grouped:
            if last_t is not None and last_t < m:
                if state == "RUNNING":
                    if not breached:
                        rem = limits[priority] - used_minutes + 1
                        t_breach = invert_B(B(last_t) + rem)
                        if t_breach < m:
                            breached = True
                            breached_at = t_breach
                    used_minutes += B(m) - B(last_t)
                last_t = m
            elif last_t is None:
                last_t = m

            for ev, p_arg in events_at_m:
                if ev == "OPEN":
                    if state == "NOT_OPENED":
                        state = "RUNNING"
                        priority = p_arg
                        used_minutes = 0
                        had_valid_open = True
                    elif state == "CLOSED":
                        state = "RUNNING"
                        priority = p_arg
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif ev == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        priority = p_arg
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

            if had_valid_open and not breached and priority is not None:
                if used_minutes > limits[priority]:
                    breached = True
                    breached_at = m

        if not had_valid_open:
            continue

        if last_t is not None and last_t < now:
            if state == "RUNNING":
                if not breached:
                    rem = limits[priority] - used_minutes + 1
                    t_breach = invert_B(B(last_t) + rem)
                    if t_breach <= now:
                        breached = True
                        breached_at = t_breach
                used_minutes += B(now) - B(last_t)
            last_t = now

        results.append(
            {
                "ticket_id": tid,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": state.lower(),
            }
        )

    return results