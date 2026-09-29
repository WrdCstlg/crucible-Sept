def compute_sla(stream):
    SLA_LIMIT = 14_400_000
    VALID_EVENTS = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}
    DIGITS = set("0123456789")

    events = []
    for line in stream:
        if not isinstance(line, str):
            continue
        s = line.strip()
        if not s:
            continue
        parts = s.split(",")
        if len(parts) != 3:
            continue
        ts_str, tid, ev = (p.strip() for p in parts)
        if not ts_str or any(c not in DIGITS for c in ts_str):
            continue
        if not tid:
            continue
        if ev not in VALID_EVENTS:
            continue
        events.append((int(ts_str), tid, ev))

    if not events:
        return []

    now = max(e[0] for e in events)
    events.sort(key=lambda e: e[0])  # stable sort

    # per ticket: [state, used, run_start, opened]
    tickets = {}
    for ts, tid, ev in events:
        t = tickets.get(tid)
        if t is None:
            t = ["NOT_OPENED", 0, None, False]
            tickets[tid] = t
        state = t[0]
        if ev == "OPEN":
            if state == "NOT_OPENED" or state == "CLOSED":
                t[0] = "RUNNING"
                t[1] = 0
                t[2] = ts
                t[3] = True
        elif ev == "PAUSE":
            if state == "RUNNING":
                t[1] += ts - t[2]
                t[2] = None
                t[0] = "PAUSED"
        elif ev == "RESUME":
            if state == "PAUSED":
                t[0] = "RUNNING"
                t[2] = ts
        elif ev == "CLOSE":
            if state == "RUNNING":
                t[1] += ts - t[2]
                t[2] = None
                t[0] = "CLOSED"
            elif state == "PAUSED":
                t[0] = "CLOSED"
        elif ev == "REOPEN":
            if state == "CLOSED":
                t[0] = "RUNNING"
                t[2] = ts

    result = []
    for tid in sorted(tickets):
        state, used, run_start, opened = tickets[tid]
        if not opened:
            continue
        if state == "RUNNING":
            used += now - run_start
        used = int(used)
        result.append({
            "ticket_id": tid,
            "used_ms": used,
            "breached": used > SLA_LIMIT,
            "status": "closed" if state == "CLOSED" else "open",
        })
    return result