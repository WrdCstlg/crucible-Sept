SLA_LIMIT_MS = 14_400_000

_VALID_EVENTS = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}


def _parse_timestamp(text):
    text = text.strip()
    if not text or not text.isascii() or not text.isdigit():
        return None
    return int(text)


def compute_sla(stream):
    events = []  # (timestamp, arrival_index, ticket_id, event)
    now = None

    for idx, raw in enumerate(stream):
        if raw is None:
            continue
        if not isinstance(raw, str):
            try:
                raw = str(raw)
            except Exception:
                continue
        line = raw.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) != 3:
            continue
        ts = _parse_timestamp(parts[0])
        if ts is None:
            continue
        # A timestamp that parses counts toward "now", even if the rest of the
        # line turns out to be semantically invalid.
        if now is None or ts > now:
            now = ts
        ticket_id = parts[1].strip()
        event = parts[2].strip()
        if not ticket_id or event not in _VALID_EVENTS:
            continue
        events.append((ts, idx, ticket_id, event))

    # Stable sort by timestamp; arrival index keeps ties in original order.
    events.sort(key=lambda e: (e[0], e[1]))

    # state: "running", "paused", "closed"
    tickets = {}  # ticket_id -> dict(state, used, since)

    for ts, _idx, tid, ev in events:
        t = tickets.get(tid)
        if t is None:
            if ev == "OPEN":
                tickets[tid] = {"state": "running", "used": 0, "since": ts}
            # anything else before the first valid OPEN is ignored
            continue

        state = t["state"]
        if ev == "OPEN":
            # Already opened once; reopening must go through REOPEN.
            continue
        elif ev == "PAUSE":
            if state == "running":
                t["used"] += ts - t["since"]
                t["since"] = None
                t["state"] = "paused"
        elif ev == "RESUME":
            if state == "paused":
                t["since"] = ts
                t["state"] = "running"
        elif ev == "CLOSE":
            if state == "running":
                t["used"] += ts - t["since"]
                t["since"] = None
                t["state"] = "closed"
            elif state == "paused":
                t["state"] = "closed"
        elif ev == "REOPEN":
            if state == "closed":
                t["since"] = ts
                t["state"] = "running"

    result = []
    for tid in sorted(tickets):
        t = tickets[tid]
        used = t["used"]
        if t["state"] == "running" and now is not None:
            used += max(0, now - t["since"])
        status = "closed" if t["state"] == "closed" else "open"
        result.append({
            "ticket_id": tid,
            "used_ms": used,
            "breached": used > SLA_LIMIT_MS,
            "status": status,
        })
    return result