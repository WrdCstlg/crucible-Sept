from bisect import bisect_left
from collections import defaultdict

LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}


def compute_sla(stream):
    raw_holiday_days = set()
    ticket_events_map = defaultdict(list)
    has_open_event = set()
    now = None
    stream_idx = 0

    for line in stream:
        line = line.strip()
        if not line:
            continue
        fields = line.split(",")
        if len(fields) not in (3, 4):
            continue
        fields = [f.strip() for f in fields]

        f0, ticket_id, event = fields[0], fields[1], fields[2]

        if not (f0.isascii() and f0.isdigit()):
            continue
        minute = int(f0)

        if not ticket_id:
            continue

        if event == "HOLIDAY":
            if ticket_id != "*" or len(fields) != 3:
                continue
            raw_holiday_days.add(minute // 1440)
            continue

        if ticket_id == "*":
            continue

        if event in ("OPEN", "PRIORITY"):
            if len(fields) != 4:
                continue
            prio = fields[3]
            if prio not in ("P1", "P2", "P3", "P4"):
                continue
            if event == "OPEN":
                has_open_event.add(ticket_id)
            ticket_events_map[ticket_id].append((minute, stream_idx, event, prio))
        elif event in ("PAUSE", "RESUME", "CLOSE", "REOPEN"):
            if len(fields) != 3:
                continue
            ticket_events_map[ticket_id].append((minute, stream_idx, event, None))
        else:
            continue

        if now is None or minute > now:
            now = minute
        stream_idx += 1

    if now is None:
        return []

    # Prepare calendar data
    holiday_set = {d for d in raw_holiday_days if d % 7 < 5}
    holiday_list = sorted(holiday_set)

    def count_business_days(d):
        w = d // 7
        rem = d % 7
        raw_days = w * 5 + (rem if rem < 5 else 5)
        return raw_days - bisect_left(holiday_list, d)

    def find_business_day(start_day, n):
        target = count_business_days(start_day) + n + 1
        low = start_day
        span = (n + 2) * 7 + len(holiday_list) * 2 + 14
        high = start_day + span
        ans = high
        while low <= high:
            mid = (low + high) // 2
            if count_business_days(mid + 1) >= target:
                ans = mid
                high = mid - 1
            else:
                low = mid + 1
        return ans

    def total_business_minutes(m):
        d = m // 1440
        minute_of_day = m % 1440
        w = d // 7
        rem_days = d % 7
        raw = w * 2400 + (rem_days if rem_days < 5 else 5) * 480
        if rem_days < 5:
            if minute_of_day > 1020:
                raw += 480
            elif minute_of_day > 540:
                raw += minute_of_day - 540

        idx = bisect_left(holiday_list, d)
        holiday_sub = idx * 480
        if idx < len(holiday_list) and holiday_list[idx] == d:
            if minute_of_day > 1020:
                holiday_sub += 480
            elif minute_of_day > 540:
                holiday_sub += minute_of_day - 540

        return raw - holiday_sub

    def business_minutes_between(start_m, end_m):
        if end_m <= start_m:
            return 0
        return total_business_minutes(end_m) - total_business_minutes(start_m)

    def advance_by_business_minutes(start_m, k):
        d = start_m // 1440
        is_bday = (d % 7 < 5) and (d not in holiday_set)
        rem = 0
        eff_start = start_m
        if is_bday:
            b_start = d * 1440 + 540
            b_end = d * 1440 + 1020
            if start_m < b_start:
                rem = 480
                eff_start = b_start
            elif start_m < b_end:
                rem = b_end - start_m
                eff_start = start_m
            else:
                rem = 0

        if rem > 0:
            if k <= rem:
                return eff_start + k
            k -= rem

        n = (k - 1) // 480
        rem_minutes = k - n * 480
        final_day = find_business_day(d + 1, n)
        return final_day * 1440 + 540 + rem_minutes

    results = []

    for ticket_id, raw_events in ticket_events_map.items():
        if ticket_id not in has_open_event:
            continue

        raw_events.sort(key=lambda x: (x[0], x[1]))

        # Group events by minute
        grouped_events = []
        cur_m = None
        cur_batch = []
        for m, _, ev, arg in raw_events:
            if m != cur_m:
                if cur_batch:
                    grouped_events.append((cur_m, cur_batch))
                cur_m = m
                cur_batch = [(ev, arg)]
            else:
                cur_batch.append((ev, arg))
        if cur_batch:
            grouped_events.append((cur_m, cur_batch))

        if grouped_events[-1][0] < now:
            grouped_events.append((now, []))

        state = "NOT_OPENED"
        prio = None
        used = 0
        breached = False
        breached_at = None
        had_valid_open = False

        t_curr = grouped_events[0][0]

        for m, batch in grouped_events:
            if m > t_curr:
                if state == "RUNNING":
                    bm = business_minutes_between(t_curr, m)
                    if not breached:
                        needed = (LIMITS[prio] + 1) - used
                        if bm >= needed:
                            t_cand = advance_by_business_minutes(t_curr, needed)
                            if t_cand < m:
                                breached = True
                                breached_at = t_cand
                    used += bm
                t_curr = m

            for ev, arg in batch:
                if ev == "OPEN":
                    if state in ("NOT_OPENED", "CLOSED"):
                        state = "RUNNING"
                        prio = arg
                        used = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif ev == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        prio = arg
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

            if not breached and had_valid_open and prio is not None:
                if used > LIMITS[prio]:
                    breached = True
                    breached_at = m

        if had_valid_open:
            results.append({
                "ticket_id": ticket_id,
                "priority": prio,
                "used_minutes": used,
                "breached": breached,
                "breached_at": breached_at,
                "status": state.lower(),
            })

    results.sort(key=lambda x: x["ticket_id"])
    return results