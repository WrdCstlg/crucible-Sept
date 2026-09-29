def compute_sla(stream):
    LIMIT = 14_400_000
    VALID_EVENTS = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}
    DIGITS = set("0123456789")

    events = []
    if stream is not None:
        for line in stream:
            if not isinstance(line, str):
                continue
            s = line.strip()
            if not s:
                continue
            parts = s.split(",")
            if len(parts) != 3:
                continue
            ts_s, tid, ev = (p.strip() for p in parts)
            if not ts_s or not all(c in DIGITS for c in ts_s):
                continue
            if not tid:
                continue
            if ev not in VALID_EVENTS:
                continue
            events.append((int(ts_s), tid, ev))

    if not events:
        return []

    now = max(e[0] for e in events)
    events.sort(key=lambda e: e[0])  # stable

    # ticket_id -> [state, used, run_start]
    tickets = {}
    for ts, tid, ev in events:
        t = tickets.get(tid)
        if t is None:
            t = ["NOT_OPENED", 0, None]
            tickets[tid] = t
        state = t[0]
        if ev == "OPEN":
            if state == "NOT_OPENED" or state == "CLOSED":
                t[0] = "RUNNING"
                t[1] = 0
                t[2] = ts
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
        state, used, start = tickets[tid]
        if state == "NOT_OPENED":
            continue
        if state == "RUNNING":
            used += now - start
        result.append({
            "ticket_id": tid,
            "used_ms": int(used),
            "breached": bool(used > LIMIT),
            "status": "closed" if state == "CLOSED" else "open",
        })
    return result