"""Reference oracle #1 for SPEC.md: one global stable sort, then a per-ticket state machine.

Never shown to any model. Used only to compute expected outputs for generated test cases,
and only after it passes the user's hand-written cases (hand_cases.json).
"""
import re

LIMIT_MS = 14_400_000
EVENTS = frozenset({"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"})
_TIMESTAMP = re.compile(r"[0-9]+")


def parse_line(line):
    """Returns (timestamp, ticket_id, event) for a well-formed line, else None."""
    if not isinstance(line, str):
        return None
    fields = line.strip().split(",")
    if len(fields) != 3:
        return None
    ts, ticket_id, event = (f.strip() for f in fields)
    if not _TIMESTAMP.fullmatch(ts) or not ticket_id or event not in EVENTS:
        return None
    return int(ts), ticket_id, event


def compute_sla(stream):
    events = []
    for position, line in enumerate(stream):
        parsed = parse_line(line)
        if parsed is not None:
            events.append((parsed[0], position, parsed[1], parsed[2]))
    if not events:
        return []
    now = max(e[0] for e in events)
    events.sort(key=lambda e: (e[0], e[1]))

    tickets = {}  # ticket_id -> [state, used_ms, running_since]
    for ts, _, ticket_id, event in events:
        t = tickets.get(ticket_id)
        state = t[0] if t else "NOT_OPENED"
        if event == "OPEN" and state in ("NOT_OPENED", "CLOSED"):
            tickets[ticket_id] = ["RUNNING", 0, ts]
        elif event == "PAUSE" and state == "RUNNING":
            t[1] += ts - t[2]
            t[0] = "PAUSED"
        elif event == "RESUME" and state == "PAUSED":
            t[0], t[2] = "RUNNING", ts
        elif event == "CLOSE" and state in ("RUNNING", "PAUSED"):
            if state == "RUNNING":
                t[1] += ts - t[2]
            t[0] = "CLOSED"
        elif event == "REOPEN" and state == "CLOSED":
            t[0], t[2] = "RUNNING", ts

    result = []
    for ticket_id in sorted(tickets):
        state, used, running_since = tickets[ticket_id]
        if state == "RUNNING":
            used += now - running_since
        result.append({
            "ticket_id": ticket_id,
            "used_ms": used,
            "breached": used > LIMIT_MS,
            "status": "closed" if state == "CLOSED" else "open",
        })
    return result
