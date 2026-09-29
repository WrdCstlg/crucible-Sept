"""Reference oracle #2 for SPEC.md, structured differently from reference.py on purpose:
its own parser, per-ticket grouping, and explicit running intervals that are summed at the end.
The two oracles must agree on every generated case before any case is written.
"""

LIMIT_MS = 14_400_000
_EVENT_NAMES = ("OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN")
_DIGITS = "0123456789"


def _well_formed(raw):
    if not isinstance(raw, str):
        return None
    fields = [f.strip() for f in raw.strip().split(",")]
    if len(fields) != 3:
        return None
    ts, ticket_id, event = fields
    if ts == "" or any(ch not in _DIGITS for ch in ts):
        return None
    if ticket_id == "" or event not in _EVENT_NAMES:
        return None
    return int(ts), ticket_id, event


def compute_sla(stream):
    well_formed = []
    for position, raw in enumerate(stream):
        parsed = _well_formed(raw)
        if parsed:
            well_formed.append((parsed, position))
    if not well_formed:
        return []
    now = max(parsed[0] for parsed, _ in well_formed)

    by_ticket = {}
    for (ts, ticket_id, event), position in well_formed:
        by_ticket.setdefault(ticket_id, []).append((ts, position, event))

    rows = []
    for ticket_id, history in by_ticket.items():
        history.sort()  # (timestamp, arrival position) is unique, so this is the stable order
        intervals = []
        running_from = None
        state = "NOT_OPENED"
        for ts, _, event in history:
            if event == "OPEN" and state in ("NOT_OPENED", "CLOSED"):
                intervals = []
                running_from, state = ts, "RUNNING"
            elif event == "REOPEN" and state == "CLOSED":
                running_from, state = ts, "RUNNING"
            elif event == "PAUSE" and state == "RUNNING":
                intervals.append((running_from, ts))
                running_from, state = None, "PAUSED"
            elif event == "RESUME" and state == "PAUSED":
                running_from, state = ts, "RUNNING"
            elif event == "CLOSE" and state in ("RUNNING", "PAUSED"):
                if state == "RUNNING":
                    intervals.append((running_from, ts))
                running_from, state = None, "CLOSED"
        if state == "NOT_OPENED":
            continue
        if state == "RUNNING":
            intervals.append((running_from, now))
        used = sum(end - start for start, end in intervals)
        rows.append({
            "ticket_id": ticket_id,
            "used_ms": used,
            "breached": used > LIMIT_MS,
            "status": "closed" if state == "CLOSED" else "open",
        })
    rows.sort(key=lambda row: row["ticket_id"])
    return rows
