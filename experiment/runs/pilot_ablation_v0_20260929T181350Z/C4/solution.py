"""Support-ticket SLA clock."""

SLA_LIMIT_MS = 14_400_000  # 4 hours

_VALID_EVENTS = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}

# Internal ticket states
_RUNNING = "running"
_PAUSED = "paused"
_CLOSED = "closed"


def _parse_line(line):
    """Parse a CSV line into (timestamp, ticket_id, event) or return None."""
    if not isinstance(line, str):
        return None
    stripped = line.strip()
    if not stripped:
        return None
    parts = stripped.split(",")
    if len(parts) != 3:
        return None
    ts_raw, tid, event = (p.strip() for p in parts)
    if not ts_raw or not ts_raw.isascii() or not ts_raw.isdigit():
        return None
    if not tid:
        return None
    if event not in _VALID_EVENTS:
        return None
    return int(ts_raw), tid, event


def compute_sla(stream):
    events = []
    now = None
    if stream is not None:
        for idx, line in enumerate(stream):
            parsed = _parse_line(line)
            if parsed is None:
                continue
            ts, tid, ev = parsed
            events.append((ts, idx, tid, ev))
            if now is None or ts > now:
                now = ts

    # Stable sort by timestamp (arrival index kept as tie-breaker).
    events.sort(key=lambda e: (e[0], e[1]))

    # ticket_id -> dict(state, total, start)
    tickets = {}

    for ts, _idx, tid, ev in events:
        t = tickets.get(tid)
        if t is None:
            # Before first valid OPEN: only OPEN is accepted.
            if ev == "OPEN":
                tickets[tid] = {"state": _RUNNING, "total": 0, "start": ts}
            continue

        state = t["state"]
        if ev == "OPEN":
            # Already opened (open, paused, or closed): ignored.
            continue
        elif ev == "PAUSE":
            if state == _RUNNING:
                t["total"] += ts - t["start"]
                t["start"] = None
                t["state"] = _PAUSED
        elif ev == "RESUME":
            if state == _PAUSED:
                t["start"] = ts
                t["state"] = _RUNNING
        elif ev == "CLOSE":
            if state == _RUNNING:
                t["total"] += ts - t["start"]
                t["start"] = None
                t["state"] = _CLOSED
            elif state == _PAUSED:
                t["state"] = _CLOSED
        elif ev == "REOPEN":
            if state == _CLOSED:
                t["start"] = ts
                t["state"] = _RUNNING

    result = []
    for tid in sorted(tickets):
        t = tickets[tid]
        used = t["total"]
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