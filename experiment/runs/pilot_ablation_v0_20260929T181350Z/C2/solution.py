import re

SLA_LIMIT_MS = 14_400_000

_TS_RE = re.compile(r"[0-9]+")
_VALID_EVENTS = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}

# Ticket states
_RUNNING = "running"
_PAUSED = "paused"
_CLOSED = "closed"


def _parse_line(line):
    """Return (timestamp, ticket_id, event) or None if malformed."""
    if not isinstance(line, str):
        return None
    stripped = line.strip()
    if not stripped:
        return None
    parts = stripped.split(",")
    if len(parts) != 3:
        return None
    ts_s, tid, ev = (p.strip() for p in parts)
    if not _TS_RE.fullmatch(ts_s):
        return None
    if not tid:
        return None
    if ev not in _VALID_EVENTS:
        return None
    return int(ts_s), tid, ev


def compute_sla(stream):
    events = []
    now = None
    if stream is not None:
        for idx, line in enumerate(stream):
            parsed = _parse_line(line)
            if parsed is None:
                continue
            ts, tid, ev = parsed
            if now is None or ts > now:
                now = ts
            events.append((ts, idx, tid, ev))

    # Stable sort by timestamp; ties broken by arrival order.
    events.sort(key=lambda e: (e[0], e[1]))

    # ticket_id -> dict(state, used, run_start)
    tickets = {}

    for ts, _idx, tid, ev in events:
        t = tickets.get(tid)
        if t is None:
            # Only a first valid OPEN creates the ticket.
            if ev == "OPEN":
                tickets[tid] = {"state": _RUNNING, "used": 0, "start": ts}
            continue

        state = t["state"]
        if ev == "OPEN":
            # Already opened once; ignore.
            continue
        elif ev == "PAUSE":
            if state == _RUNNING:
                t["used"] += ts - t["start"]
                t["start"] = None
                t["state"] = _PAUSED
        elif ev == "RESUME":
            if state == _PAUSED:
                t["start"] = ts
                t["state"] = _RUNNING
        elif ev == "CLOSE":
            if state == _RUNNING:
                t["used"] += ts - t["start"]
                t["start"] = None
                t["state"] = _CLOSED
            elif state == _PAUSED:
                t["start"] = None
                t["state"] = _CLOSED
        elif ev == "REOPEN":
            if state == _CLOSED:
                t["start"] = ts
                t["state"] = _RUNNING

    result = []
    for tid in sorted(tickets):
        t = tickets[tid]
        used = t["used"]
        if t["state"] == _RUNNING and now is not None:
            used += max(0, now - t["start"])
        status = "closed" if t["state"] == _CLOSED else "open"
        result.append(
            {
                "ticket_id": tid,
                "used_ms": used,
                "breached": used > SLA_LIMIT_MS,
                "status": status,
            }
        )
    return result