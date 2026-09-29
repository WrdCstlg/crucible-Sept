"""Support-ticket SLA clock calculation module."""

from typing import Any, Dict, Iterable, List, Optional


class TicketState:
    UNOPENED = "UNOPENED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"


class TicketStateMachine:
    """Per-ticket state machine updated event by event."""

    SLA_LIMIT_MS = 14_400_000  # 4 hours

    def __init__(self, ticket_id: str) -> None:
        self.ticket_id = ticket_id
        self.state = TicketState.UNOPENED
        self.used_ms = 0
        self.last_running_start: Optional[int] = None
        self.had_valid_open = False

    def process_event(self, event: str, timestamp_ms: int) -> None:
        if self.state == TicketState.UNOPENED:
            if event == "OPEN":
                self.had_valid_open = True
                self.state = TicketState.RUNNING
                self.last_running_start = timestamp_ms
            # Any event before first valid OPEN is silently ignored

        elif self.state == TicketState.RUNNING:
            if event == "PAUSE":
                self.used_ms += timestamp_ms - self.last_running_start  # type: ignore[operator]
                self.last_running_start = None
                self.state = TicketState.PAUSED
            elif event == "CLOSE":
                self.used_ms += timestamp_ms - self.last_running_start  # type: ignore[operator]
                self.last_running_start = None
                self.state = TicketState.CLOSED
            # OPEN when already open, RESUME when clock is running,
            # REOPEN when not closed, or invalid events are silently ignored

        elif self.state == TicketState.PAUSED:
            if event == "RESUME":
                self.last_running_start = timestamp_ms
                self.state = TicketState.RUNNING
            elif event == "CLOSE":
                # Time from PAUSE to CLOSE does not count
                self.state = TicketState.CLOSED
            # OPEN when already open, PAUSE when already paused,
            # REOPEN when not closed, or invalid events are silently ignored

        elif self.state == TicketState.CLOSED:
            if event == "REOPEN":
                self.last_running_start = timestamp_ms
                self.state = TicketState.RUNNING
            # CLOSE when already closed, or invalid events when closed are silently ignored

    def finalize(self, now_ms: int) -> Dict[str, Any]:
        total_used = self.used_ms
        if self.state == TicketState.RUNNING:
            if self.last_running_start is not None and now_ms >= self.last_running_start:
                total_used += now_ms - self.last_running_start
            status = "open"
        elif self.state == TicketState.PAUSED:
            status = "open"
        elif self.state == TicketState.CLOSED:
            status = "closed"
        else:
            status = "unopened"

        return {
            "ticket_id": self.ticket_id,
            "used_ms": total_used,
            "breached": total_used > self.SLA_LIMIT_MS,
            "status": status,
        }


def compute_sla(stream: Iterable[str]) -> List[Dict[str, Any]]:
    """Compute SLA metrics for support tickets using a per-ticket state machine."""
    events = []
    max_ts: Optional[int] = None

    for arrival_idx, line in enumerate(stream):
        if not isinstance(line, str):
            continue
        stripped = line.strip()
        if not stripped:
            continue

        parts = stripped.split(",")
        if len(parts) != 3:
            continue

        raw_ts, raw_ticket_id, raw_event = (
            parts[0].strip(),
            parts[1].strip(),
            parts[2].strip(),
        )

        try:
            ts = int(raw_ts)
            if ts < 0:
                continue
        except ValueError:
            continue

        # "Now" is the maximum timestamp_ms appearing anywhere in the stream
        # (including lines that are otherwise invalid).
        if max_ts is None or ts > max_ts:
            max_ts = ts

        if not raw_ticket_id:
            continue

        events.append((ts, arrival_idx, raw_ticket_id, raw_event))

    if max_ts is None:
        return []

    # Sort all events by timestamp_ms; ties broken by arrival order (stable sort)
    events.sort(key=lambda x: (x[0], x[1]))

    # Feed events into per-ticket state machines
    machines: Dict[str, TicketStateMachine] = {}
    for ts, _, ticket_id, event in events:
        if ticket_id not in machines:
            machines[ticket_id] = TicketStateMachine(ticket_id)
        machines[ticket_id].process_event(event, ts)

    # Finalize tickets that had at least one valid OPEN
    results = [
        sm.finalize(max_ts)
        for sm in machines.values()
        if sm.had_valid_open
    ]

    # Return results sorted by ticket_id ascending (string order)
    results.sort(key=lambda x: x["ticket_id"])
    return results