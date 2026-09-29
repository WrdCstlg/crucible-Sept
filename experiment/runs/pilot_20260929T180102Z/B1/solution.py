"""Support-ticket SLA clock computation module."""

from typing import Any, Dict, Iterable, List, Optional, Tuple

VALID_EVENTS = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}
SLA_LIMIT_MS = 14_400_000


class TicketStateMachine:
    """Per-ticket state machine tracking lifecycle state and accumulated used time."""

    NOT_OPENED = "NOT_OPENED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"

    def __init__(self, ticket_id: str) -> None:
        self.ticket_id: str = ticket_id
        self.state: str = self.NOT_OPENED
        self.used_ms: int = 0
        self.last_running_start: int = 0
        self.had_valid_open: bool = False

    def handle_event(self, event: str, timestamp_ms: int) -> None:
        """Transition ticket state based on event and event timestamp."""
        if self.state == self.NOT_OPENED:
            if event == "OPEN":
                self.had_valid_open = True
                self.state = self.RUNNING
                self.used_ms = 0
                self.last_running_start = timestamp_ms
        elif self.state == self.RUNNING:
            if event == "PAUSE":
                self.used_ms += timestamp_ms - self.last_running_start
                self.state = self.PAUSED
            elif event == "CLOSE":
                self.used_ms += timestamp_ms - self.last_running_start
                self.state = self.CLOSED
        elif self.state == self.PAUSED:
            if event == "RESUME":
                self.state = self.RUNNING
                self.last_running_start = timestamp_ms
            elif event == "CLOSE":
                self.state = self.CLOSED
        elif self.state == self.CLOSED:
            if event == "OPEN":
                self.had_valid_open = True
                self.state = self.RUNNING
                self.used_ms = 0
                self.last_running_start = timestamp_ms
            elif event == "REOPEN":
                self.state = self.RUNNING
                self.last_running_start = timestamp_ms

    def finalize(self, now: int) -> Dict[str, Any]:
        """Produce the final ticket summary dictionary evaluated up to 'now'."""
        total_used = self.used_ms
        if self.state == self.RUNNING:
            total_used += now - self.last_running_start

        return {
            "ticket_id": self.ticket_id,
            "used_ms": total_used,
            "breached": total_used > SLA_LIMIT_MS,
            "status": "closed" if self.state == self.CLOSED else "open",
        }


def _parse_line(line: Any) -> Optional[Tuple[int, str, str]]:
    """Parse and validate a stream line. Returns (timestamp_ms, ticket_id, event) or None."""
    if not isinstance(line, str):
        return None

    trimmed = line.strip()
    parts = trimmed.split(",")
    if len(parts) != 3:
        return None

    ts_str = parts[0].strip()
    ticket_id = parts[1].strip()
    event = parts[2].strip()

    if not ts_str or not all("0" <= c <= "9" for c in ts_str):
        return None
    if not ticket_id:
        return None
    if event not in VALID_EVENTS:
        return None

    return int(ts_str), ticket_id, event


def compute_sla(stream: Iterable[str]) -> List[Dict[str, Any]]:
    """Compute SLA clock metrics for support tickets from an event stream."""
    well_formed_events: List[Tuple[int, int, str, str]] = []
    max_ts: Optional[int] = None

    for idx, line in enumerate(stream):
        parsed = _parse_line(line)
        if parsed is not None:
            ts, ticket_id, event = parsed
            well_formed_events.append((ts, idx, ticket_id, event))
            if max_ts is None or ts > max_ts:
                max_ts = ts

    if max_ts is None:
        return []

    # Sort stably by timestamp, preserving arrival order for equal timestamps
    well_formed_events.sort(key=lambda item: item[0])

    tickets: Dict[str, TicketStateMachine] = {}

    for ts, _, ticket_id, event in well_formed_events:
        if ticket_id not in tickets:
            tickets[ticket_id] = TicketStateMachine(ticket_id)
        tickets[ticket_id].handle_event(event, ts)

    output: List[Dict[str, Any]] = [
        machine.finalize(max_ts)
        for machine in tickets.values()
        if machine.had_valid_open
    ]

    output.sort(key=lambda item: item["ticket_id"])
    return output