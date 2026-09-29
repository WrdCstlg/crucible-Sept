SLA_LIMIT_MS = 14_400_000

_VALID_EVENTS = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}
_DIGITS = set("0123456789")

NOT_OPENED = "NOT_OPENED"
RUNNING = "RUNNING"
PAUSED = "PAUSED"
CLOSED = "CLOSED"


def _parse_line(line):
    """Return (timestamp, ticket_id, event) for a well-formed line, else None."""
    if not isinstance(line, str):
        return None
    stripped = line.strip()
    if not stripped:
        return None
    parts = stripped.split(",")
    if len(parts) != 3:
        return None
    ts_raw, tid, event = (p.strip() for p in parts)
    if not ts_raw or any(c not in _DIGITS for c in ts_raw):
        return None
    if not tid:
        return None
    if event not in _VALID_EVENTS:
        return None
    return int(ts_raw), tid, event


def compute_sla(stream):
    events = []
    if stream is not None:
        for line in stream:
            parsed = _parse_line(line)
            if parsed is not None:
                events.append(parsed)

    if not events:
        return []

    now = max(e[0] for e in events)
    # Python's sort is stable, so equal timestamps keep stream order.
    events.sort(key=lambda e: e[0])

    state = {}      # ticket_id -> state
    used = {}       # ticket_id -> accumulated ms
    run_start = {}  # ticket_id -> timestamp RUNNING was entered

    for ts, tid, ev in events:
        st = state.get(tid, NOT_OPENED)
        if ev == "OPEN":
            if st == NOT_OPENED or st == CLOSED:
                state[tid] = RUNNING
                used[tid] = 0
                run_start[tid] = ts
        elif ev == "PAUSE":
            if st == RUNNING:
                used[tid] += ts - run_start[tid]
                state[tid] = PAUSED
        elif ev == "RESUME":
            if st == PAUSED:
                state[tid] = RUNNING
                run_start[tid] = ts
        elif ev == "CLOSE":
            if st == RUNNING:
                used[tid] += ts - run_start[tid]
                state[tid] = CLOSED
            elif st == PAUSED:
                state[tid] = CLOSED
        elif ev == "REOPEN":
            if st == CLOSED:
                state[tid] = RUNNING
                run_start[tid] = ts

    result = []
    for tid in sorted(state):
        st = state[tid]
        if st == NOT_OPENED:
            continue
        total = used[tid]
        if st == RUNNING:
            total += now - run_start[tid]
        total = int(total)
        result.append({
            "ticket_id": tid,
            "used_ms": total,
            "breached": bool(total > SLA_LIMIT_MS),
            "status": "closed" if st == CLOSED else "open",
        })
    return result