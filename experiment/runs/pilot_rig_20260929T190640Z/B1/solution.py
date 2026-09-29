"""Support-ticket SLA clock implementation."""

from enum import Enum, auto
from typing import Any, Dict, Iterable, List


class TicketState(Enum):
    NOT_OPENED = auto()
    RUNNING = auto()
    PAUSED = auto()
    CLOSED = auto()


class TicketStateMachine:
    """Per-ticket state machine updated event by event."""

    SLA_LIMIT_MS = 14_400_000

    def __init__(self, ticket_id: str) -> None:
        self.ticket_id = ticket_id
        self.state = TicketState.NOT_OPENED
        self.used_ms = 0
        self.running_start_ms = 0
        self.had_valid_open = False

    def process_event(self, event: str, timestamp: int) -> None:
        if event == "OPEN":
            if self.state == TicketState.NOT_OPENED:
                self.state = TicketState.RUNNING
                self.used_ms = 0
                self.running_start_ms = timestamp
                self.had_valid_open = True
            elif self.state == TicketState.CLOSED:
                self.state = TicketState.RUNNING
                self.used_ms = 0
                self.running_start_ms = timestamp
                self.had_valid_open = True
            # RUNNING and PAUSED: ignored

        elif event == "PAUSE":
            if self.state == TicketState.RUNNING:
                self.used_ms += timestamp - self.running_start_ms
                self.state = TicketState.PAUSED
            # NOT_OPENED, PAUSED, CLOSED: ignored

        elif event == "RESUME":
            if self.state == TicketState.PAUSED:
                self.state = TicketState.RUNNING
                self.running_start_ms = timestamp
            # NOT_OPENED, RUNNING, CLOSED: ignored

        elif event == "CLOSE":
            if self.state == TicketState.RUNNING:
                self.used_ms += timestamp - self.running_start_ms
                self.state = TicketState.CLOSED
            elif self.state == TicketState.PAUSED:
                self.state = TicketState.CLOSED
            # NOT_OPENED, CLOSED: ignored

        elif event == "REOPEN":
            if self.state == TicketState.CLOSED:
                self.state = TicketState.RUNNING
                self.running_start_ms = timestamp
            # NOT_OPENED, RUNNING, PAUSED: ignored

    def finalize(self, now: int) -> Dict[str, Any]:
        total_used = self.used_ms
        if self.state == TicketState.RUNNING:
            total_used += now - self.running_start_ms

        return {
            "ticket_id": self.ticket_id,
            "used_ms": total_used,
            "breached": total_used > self.SLA_LIMIT_MS,
            "status": "closed" if self.state == TicketState.CLOSED else "open",
        }


def compute_sla(stream: Iterable[str]) -> List[Dict[str, Any]]:
    valid_events = []
    allowed_events = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}

    for line in stream:
        trimmed_line = line.strip()
        parts = trimmed_line.split(",")
        if len(parts) != 3:
            continue

        raw_ts, raw_ticket_id, raw_event = (part.strip() for part in parts)

        if not raw_ts or not all("0" <= c <= "9" for c in raw_ts):
            continue
        if not raw_ticket_id:
            continue
        if raw_event not in allowed_events:
            continue

        timestamp = int(raw_ts, 10)
        valid_events.append((timestamp, raw_ticket_id, raw_event))

    if not valid_events:
        return []

    now = max(event[0] for event in valid_events)
    valid_events.sort(key=lambda item: item[0])

    state_machines: Dict[str, TicketStateMachine] = {}

    for timestamp, ticket_id, event in valid_events:
        if ticket_id not in state_machines:
            state_machines[ticket_id] = TicketStateMachine(ticket_id)
        state_machines[ticket_id].process_event(event, timestamp)

    results = [
        sm.finalize(now)
        for sm in state_machines.values()
        if sm.had_valid_open
    ]

    results.sort(key=lambda entry: entry["ticket_id"])
    return results