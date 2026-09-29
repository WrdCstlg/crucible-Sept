from typing import Iterable, List, Dict, Any

SLA_LIMIT_MS = 14_400_000

_VALID_EVENTS = frozenset({"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"})
_ASCII_DIGITS = frozenset("0123456789")

_NOT_OPENED = "NOT_OPENED"
_RUNNING = "RUNNING"
_PAUSED = "PAUSED"
_CLOSED = "CLOSED"


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
    ts_str, ticket_id, event = (p.strip() for p in parts)
    if not ts_str or any(c not in _ASCII_DIGITS for c in ts_str):
        return None
    if not ticket_id:
        return None
    if event not in _VALID_EVENTS:
        return None
    return int(ts_str, 10), ticket_id, event


class _Ticket:
    __slots__ = ("state", "used", "run_start")

    def __init__(self):
        self.state = _NOT_OPENED
        self.used = 0
        self.run_start = 0


def compute_sla(stream: Iterable[str]) -> List[Dict[str, Any]]:
    events = []
    if stream is not None:
        for line in stream:
            parsed = _parse_line(line)
            if parsed is not None:
                events.append(parsed)

    if not events:
        return []

    now = max(ev[0] for ev in events)

    # Stable sort by timestamp only.
    events.sort(key=lambda ev: ev[0])

    tickets: Dict[str, _Ticket] = {}

    for ts, tid, event in events:
        t = tickets.get(tid)
        if t is None:
            t = _Ticket()
            tickets[tid] = t
        state = t.state

        if event == "OPEN":
            if state == _NOT_OPENED or state == _CLOSED:
                t.state = _RUNNING
                t.used = 0
                t.run_start = ts
        elif event == "PAUSE":
            if state == _RUNNING:
                t.used += ts - t.run_start
                t.state = _PAUSED
        elif event == "RESUME":
            if state == _PAUSED:
                t.state = _RUNNING
                t.run_start = ts
        elif event == "CLOSE":
            if state == _RUNNING:
                t.used += ts - t.run_start
                t.state = _CLOSED
            elif state == _PAUSED:
                t.state = _CLOSED
        elif event == "REOPEN":
            if state == _CLOSED:
                t.state = _RUNNING
                t.run_start = ts

    result: List[Dict[str, Any]] = []
    for tid in sorted(tickets):
        t = tickets[tid]
        if t.state == _NOT_OPENED:
            continue
        used = t.used
        if t.state == _RUNNING:
            used += now - t.run_start
        used = int(used)
        result.append(
            {
                "ticket_id": tid,
                "used_ms": used,
                "breached": bool(used > SLA_LIMIT_MS),
                "status": "closed" if t.state == _CLOSED else "open",
            }
        )
    return result