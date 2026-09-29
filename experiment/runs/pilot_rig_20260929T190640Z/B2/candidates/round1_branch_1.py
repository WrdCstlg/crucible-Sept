from enum import Enum, auto
from typing import Any, Dict, Iterable, List, Optional


class TicketState(Enum):
    NOT_OPENED = auto()
    RUNNING = auto()
    PAUSED = auto()
    CLOSED = auto()


class TicketStateMachine:
    def __init__(self, ticket_id: str) -> None:
        self.ticket_id = ticket_id
        self.state = TicketState.NOT_OPENED
        self.used_ms = 0
        self.last_start_ms = 0
        self.has_valid_open = False

    def handle_event(self, timestamp: int, event: str) -> None:
        if event == "OPEN":
            if self.state == TicketState.NOT_OPENED or self.state == TicketState.CLOSED:
                self.state = TicketState.RUNNING
                self.used_ms = 0
                self.last_start_ms = timestamp
                self.has_valid_open = True
        elif event == "PAUSE":
            if self.state == TicketState.RUNNING:
                self.used_ms += timestamp - self.last_start_ms
                self.state = TicketState.PAUSED
        elif event == "RESUME":
            if self.state == TicketState.PAUSED:
                self.state = TicketState.RUNNING
                self.last_start_ms = timestamp
        elif event == "CLOSE":
            if self.state == TicketState.RUNNING:
                self.used_ms += timestamp - self.last_start_ms
                self.state = TicketState.CLOSED
            elif self.state == TicketState.PAUSED:
                self.state = TicketState.CLOSED
        elif event == "REOPEN":
            if self.state == TicketState.CLOSED:
                self.state = TicketState.RUNNING
                self.last_start_ms = timestamp

    def finalize(self, now: int) -> Dict[str, Any]:
        total_used = self.used_ms
        if self.state == TicketState.RUNNING:
            total_used += now - self.last_start_ms

        return {
            "ticket_id": self.ticket_id,
            "used_ms": total_used,
            "breached": total_used > 14_400_000,
            "status": "closed" if self.state == TicketState.CLOSED else "open",
        }


def compute_sla(stream: Iterable[str]) -> List[Dict[str, Any]]:
    valid_events = []
    valid_event_types = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}
    max_timestamp: Optional[int] = None

    for line in stream:
        if not isinstance(line, str):
            continue

        trimmed = line.strip()
        parts = trimmed.split(",")
        if len(parts) != 3:
            continue

        ts_str = parts[0].strip()
        ticket_id = parts[1].strip()
        event = parts[2].strip()

        if not (ts_str.isascii() and ts_str.isdigit()):
            continue
        if not ticket_id:
            continue
        if event not in valid_event_types:
            continue

        timestamp = int(ts_str)
        if max_timestamp is None or timestamp > max_timestamp:
            max_timestamp = timestamp

        valid_events.append((timestamp, ticket_id, event))

    if max_timestamp is None:
        return []

    # Sort stably by timestamp
    valid_events.sort(key=lambda x: x[0])

    tickets: Dict[str, TicketStateMachine] = {}
    for timestamp, ticket_id, event in valid_events:
        if ticket_id not in tickets:
            tickets[ticket_id] = TicketStateMachine(ticket_id)
        tickets[ticket_id].handle_event(timestamp, event)

    results = [
        ticket.finalize(max_timestamp)
        for ticket in tickets.values()
        if ticket.has_valid_open
    ]

    results.sort(key=lambda x: x["ticket_id"])
    return results