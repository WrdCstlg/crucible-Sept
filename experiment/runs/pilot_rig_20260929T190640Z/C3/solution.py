"""Support-ticket SLA clock."""

SLA_LIMIT_MS = 14_400_000

_VALID_EVENTS = frozenset({"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"})
_DIGITS = frozenset("0123456789")

_NOT_OPENED = "NOT_OPENED"
_RUNNING = "RUNNING"
_PAUSED = "PAUSED"
_CLOSED = "CLOSED"


def _digits_to_int(s):
    """Convert a string of ASCII digits to int, avoiding str->int digit limits."""
    if len(s) <= 4000:
        return int(s, 10)
    value = 0
    chunk = 1000
    for i in range(0, len(s), chunk):
        piece = s[i:i + chunk]
        value = value * (10 ** len(piece)) + int(piece, 10)
    return value


def _parse(line):
    """Return (timestamp, ticket_id, event) for a well-formed line, else None."""
    if not isinstance(line, str):
        return None
    s = line.strip()
    if not s:
        return None
    parts = s.split(",")
    if len(parts) != 3:
        return None
    ts_s = parts[0].strip()
    tid = parts[1].strip()
    ev = parts[2].strip()
    if not ts_s:
        return None
    for c in ts_s:
        if c not in _DIGITS:
            return None
    if not tid:
        return None
    if ev not in _VALID_EVENTS:
        return None
    return _digits_to_int(ts_s), tid, ev


def compute_sla(stream):
    events = []
    if stream is not None:
        for line in stream:
            parsed = _parse(line)
            if parsed is not None:
                events.append(parsed)

    if not events:
        return []

    now = max(e[0] for e in events)

    # Stable sort by timestamp only.
    events.sort(key=lambda e: e[0])

    # ticket_id -> [state, used_ms, run_start]
    tickets = {}

    for ts, tid, ev in events:
        rec = tickets.get(tid)
        state = rec[0] if rec is not None else _NOT_OPENED

        if ev == "OPEN":
            if state == _NOT_OPENED or state == _CLOSED:
                if rec is None:
                    tickets[tid] = [_RUNNING, 0, ts]
                else:
                    rec[0] = _RUNNING
                    rec[1] = 0
                    rec[2] = ts
        elif ev == "PAUSE":
            if state == _RUNNING:
                rec[1] += ts - rec[2]
                rec[0] = _PAUSED
                rec[2] = None
        elif ev == "RESUME":
            if state == _PAUSED:
                rec[0] = _RUNNING
                rec[2] = ts
        elif ev == "CLOSE":
            if state == _RUNNING:
                rec[1] += ts - rec[2]
                rec[0] = _CLOSED
                rec[2] = None
            elif state == _PAUSED:
                rec[0] = _CLOSED
                rec[2] = None
        elif ev == "REOPEN":
            if state == _CLOSED:
                rec[0] = _RUNNING
                rec[2] = ts

    result = []
    for tid in sorted(tickets):
        state, used, start = tickets[tid]
        if state == _RUNNING:
            used += now - start
        used = int(used)
        result.append({
            "ticket_id": tid,
            "used_ms": used,
            "breached": bool(used > SLA_LIMIT_MS),
            "status": "closed" if state == _CLOSED else "open",
        })
    return result