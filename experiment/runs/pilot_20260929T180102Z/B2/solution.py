"""SLA clock computation for support tickets."""

from typing import Any, Dict, Iterable, List


class TicketStateMachine:
    """State machine tracking SLA used time and status for a single ticket."""

    NOT_OPENED = "NOT_OPENED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"

    SLA_LIMIT_MS = 14_400_000

    def __init__(self, ticket_id: str) -> None:
        self.ticket_id = ticket_id
        self.state = self.NOT_OPENED
        self.used_ms = 0
        self.running_since: int | None = None
        self.has_valid_open = False

    def handle_event(self, ts: int, event: str) -> None:
        """Update ticket state based on the arriving event."""
        if self.state == self.NOT_OPENED:
            if event == "OPEN":
                self.state = self.RUNNING
                self.used_ms = 0
                self.running_since = ts
                self.has_valid_open = True
            # PAUSE, RESUME, CLOSE, REOPEN are ignored

        elif self.state == self.RUNNING:
            if event == "PAUSE":
                self.used_ms += ts - self.running_since  # type: ignore[operator]
                self.running_since = None
                self.state = self.PAUSED
            elif event == "CLOSE":
                self.used_ms += ts - self.running_since  # type: ignore[operator]
                self.running_since = None
                self.state = self.CLOSED
            # OPEN, RESUME, REOPEN are ignored

        elif self.state == self.PAUSED:
            if event == "RESUME":
                self.running_since = ts
                self.state = self.RUNNING
            elif event == "CLOSE":
                self.state = self.CLOSED
            # OPEN, PAUSE, REOPEN are ignored

        elif self.state == self.CLOSED:
            if event == "OPEN":
                self.state = self.RUNNING
                self.used_ms = 0
                self.running_since = ts
                self.has_valid_open = True
            elif event == "REOPEN":
                self.state = self.RUNNING
                self.running_since = ts
            # PAUSE, RESUME, CLOSE are ignored

    def finalize(self, now: int) -> Dict[str, Any]:
        """Produce the final SLA report dictionary for this ticket."""
        final_used_ms = self.used_ms
        if self.state == self.RUNNING and self.running_since is not None:
            final_used_ms += now - self.running_since

        return {
            "ticket_id": self.ticket_id,
            "used_ms": final_used_ms,
            "breached": final_used_ms > self.SLA_LIMIT_MS,
            "status": "closed" if self.state == self.CLOSED else "open",
        }


def compute_sla(stream: Iterable[str]) -> List[Dict[str, Any]]:
    """Compute SLA clock metrics for tickets in the event stream."""
    valid_events = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}
    well_formed_records: List[tuple[int, str, str]] = []

    for raw_line in stream:
        if not isinstance(raw_line, str):
            continue

        stripped_line = raw_line.strip()
        parts = stripped_line.split(",")
        if len(parts) != 3:
            continue

        ts_str, ticket_id, event = (p.strip() for p in parts)

        if not ts_str or not ts_str.isascii() or not ts_str.isdigit():
            continue

        if not ticket_id:
            continue

        if event not in valid_events:
            continue

        ts = int(ts_str, 10)
        well_formed_records.append((ts, ticket_id, event))

    if not well_formed_records:
        return []

    # Sort events by timestamp stably to preserve original order on equal timestamps
    well_formed_records.sort(key=lambda record: record[0])

    # "Now" is the largest timestamp among all well-formed lines
    now = well_formed_records[-1][0]

    # Process events through per-ticket state machines
    machines: Dict[str, TicketStateMachine] = {}
    for ts, ticket_id, event in well_formed_records:
        if ticket_id not in machines:
            machines[ticket_id] = TicketStateMachine(ticket_id)
        machines[ticket_id].handle_event(ts, event)

    # Collect and sort tickets that had at least one valid OPEN
    results = [
        sm.finalize(now)
        for sm in machines.values()
        if sm.has_valid_open
    ]
    results.sort(key=lambda item: item["ticket_id"])

    return results