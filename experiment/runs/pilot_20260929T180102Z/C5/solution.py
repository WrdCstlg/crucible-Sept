from typing import Iterable, List, Dict, Any

SLA_LIMIT_MS = 14_400_000
_VALID_EVENTS = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}
_DIGITS = set("0123456789")


def _parse(line):
    if not isinstance(line, str):
        return None
    s = line.strip()
    if not s:
        return None
    parts = s.split(",")
    if len(parts) != 3:
        return None
    ts_s, tid, ev = (p.strip() for p in parts)
    if not ts_s or any(c not in _DIGITS for c in ts_s):
        return None
    if not tid:
        return None
    if ev not in _VALID_EVENTS:
        return None
    return int(ts_s), tid, ev


def compute_sla(stream: Iterable[str]) -> List[Dict[str, Any]]:
    events = []
    if stream is not None:
        for line in stream:
            parsed = _parse(line)
            if parsed is not None:
                events.append(parsed)

    if not events:
        return []

    now = max(e[0] for e in events)
    events.sort(key=lambda e: e[0])  # stable

    state = {}      # tid -> state string
    used = {}       # tid -> accumulated ms
    run_start = {}  # tid -> ts when entered RUNNING
    opened = set()

    for ts, tid, ev in events:
        st = state.get(tid, "NOT_OPENED")
        if ev == "OPEN":
            if st == "NOT_OPENED" or st == "CLOSED":
                state[tid] = "RUNNING"
                used[tid] = 0
                run_start[tid] = ts
                opened.add(tid)
        elif ev == "PAUSE":
            if st == "RUNNING":
                used[tid] += ts - run_start[tid]
                state[tid] = "PAUSED"
        elif ev == "RESUME":
            if st == "PAUSED":
                state[tid] = "RUNNING"
                run_start[tid] = ts
        elif ev == "CLOSE":
            if st == "RUNNING":
                used[tid] += ts - run_start[tid]
                state[tid] = "CLOSED"
            elif st == "PAUSED":
                state[tid] = "CLOSED"
        elif ev == "REOPEN":
            if st == "CLOSED":
                state[tid] = "RUNNING"
                run_start[tid] = ts

    result = []
    for tid in sorted(opened):
        st = state[tid]
        total = used[tid]
        if st == "RUNNING":
            total += now - run_start[tid]
        total = int(total)
        result.append({
            "ticket_id": tid,
            "used_ms": total,
            "breached": bool(total > SLA_LIMIT_MS),
            "status": "closed" if st == "CLOSED" else "open",
        })
    return result