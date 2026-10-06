import bisect
from collections import defaultdict


def compute_sla(stream):
    holidays = set()
    ticket_events = []

    for stream_idx, line in enumerate(stream):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) not in (3, 4):
            continue

        f1, ticket_id, event = parts[0], parts[1], parts[2]

        if not f1 or not all("0" <= c <= "9" for c in f1):
            continue
        minute = int(f1)

        if not ticket_id:
            continue

        if event not in (
            "OPEN",
            "PRIORITY",
            "PAUSE",
            "RESUME",
            "CLOSE",
            "REOPEN",
            "HOLIDAY",
        ):
            continue

        if event == "HOLIDAY":
            if ticket_id != "*" or len(parts) != 3:
                continue
            holidays.add(minute // 1440)
            continue

        if ticket_id == "*":
            continue

        if event in ("OPEN", "PRIORITY"):
            if len(parts) != 4:
                continue
            priority = parts[3]
            if priority not in ("P1", "P2", "P3", "P4"):
                continue
            ticket_events.append(
                (minute, stream_idx, ticket_id, event, priority)
            )
        else:
            if len(parts) != 3:
                continue
            ticket_events.append((minute, stream_idx, ticket_id, event, None))

    if not ticket_events:
        return []

    now = max(ev[0] for ev in ticket_events)

    weekday_holidays = sorted(d for d in holidays if d % 7 < 5)

    def raw_biz(t):
        if t <= 0:
            return 0
        weeks = t // 10080
        rem = t % 10080
        ans = weeks * 2400
        day = rem // 1440
        mod = rem % 1440
        ans += min(day, 5) * 480
        if day < 5:
            ans += max(0, min(mod, 1020) - 540)
        return ans

    def holiday_deduction(t):
        if not weekday_holidays or t <= 0:
            return 0
        d_t = t // 1440
        idx = bisect.bisect_left(weekday_holidays, d_t)
        total = idx * 480
        if idx < len(weekday_holidays) and weekday_holidays[idx] == d_t:
            mod = t % 1440
            total += max(0, min(mod, 1020) - 540)
        return total

    def biz(t):
        return raw_biz(t) - holiday_deduction(t)

    def find_breach_minute(m_start, m_end, target):
        low = m_start + 1
        high = m_end
        while low < high:
            mid = (low + high) // 2
            if biz(mid) >= target:
                high = mid
            else:
                low = mid + 1
        return low

    limits = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}

    events_by_ticket = defaultdict(list)
    for ev in ticket_events:
        events_by_ticket[ev[2]].append(ev)

    results = []

    for ticket_id in sorted(events_by_ticket.keys()):
        t_events = events_by_ticket[ticket_id]
        t_events.sort(key=lambda x: (x[0], x[1]))

        events_by_minute = []
        for ev in t_events:
            if not events_by_minute or events_by_minute[-1][0] != ev[0]:
                events_by_minute.append((ev[0], [ev]))
            else:
                events_by_minute[-1][1].append(ev)

        state = "NOT_OPENED"
        priority = None
        used = 0
        breached = False
        breached_at = None
        had_valid_open = False

        num_minutes = len(events_by_minute)
        for i in range(num_minutes):
            m, ev_list = events_by_minute[i]

            for ev in ev_list:
                _, _, _, event_type, p_arg = ev
                if event_type == "OPEN":
                    if state in ("NOT_OPENED", "CLOSED"):
                        state = "RUNNING"
                        priority = p_arg
                        used = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif event_type == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        priority = p_arg
                elif event_type == "PAUSE":
                    if state == "RUNNING":
                        state = "PAUSED"
                elif event_type == "RESUME":
                    if state == "PAUSED":
                        state = "RUNNING"
                elif event_type == "CLOSE":
                    if state in ("RUNNING", "PAUSED"):
                        state = "CLOSED"
                elif event_type == "REOPEN":
                    if state == "CLOSED":
                        state = "RUNNING"

            if had_valid_open and not breached and priority is not None:
                if used > limits[priority]:
                    breached = True
                    breached_at = m

            if i + 1 < num_minutes:
                next_m = events_by_minute[i + 1][0]
            else:
                next_m = now

            if next_m > m:
                if state == "RUNNING":
                    if not breached and priority is not None:
                        limit = limits[priority]
                        target = biz(m) + limit + 1 - used
                        if next_m - 1 >= m + 1 and biz(next_m - 1) >= target:
                            breached_at = find_breach_minute(
                                m, next_m - 1, target
                            )
                            breached = True
                    used += biz(next_m) - biz(m)

                if i + 1 == num_minutes:
                    if (
                        had_valid_open
                        and not breached
                        and priority is not None
                        and used > limits[priority]
                    ):
                        breached = True
                        breached_at = now

        if not had_valid_open:
            continue

        results.append(
            {
                "ticket_id": ticket_id,
                "priority": priority,
                "used_minutes": used,
                "breached": breached,
                "breached_at": breached_at,
                "status": state.lower(),
            }
        )

    return results