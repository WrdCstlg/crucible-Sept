**Problem 4: Support-ticket SLA clock.** Implement `def compute_sla(stream)` where `stream` is an iterable of CSV strings `timestamp_ms,ticket_id,event`, with `timestamp_ms` a non-negative integer of whole milliseconds. Whitespace around fields is ignored; empty or malformed lines are skipped. Events: `OPEN`, `PAUSE`, `RESUME`, `CLOSE`, `REOPEN`.

The SLA limit is **14,400,000 ms (4 hours)** of elapsed calendar time. A ticket **breaches iff its used time is strictly greater than the limit**; exactly 14,400,000 ms does not breach. Used time accumulates only while the clock is running:

- `OPEN` starts the clock. Time before `OPEN` never counts.
- `PAUSE` stops the clock; the paused stretch does not count, even if the ticket is later `CLOSE`d mid-pause.
- `RESUME` restarts the clock.
- `CLOSE` stops the clock permanently (unless reopened). The time from `PAUSE` to `CLOSE` does not count.
- `REOPEN` (only valid after `CLOSE`) puts the ticket back in service; the clock runs from the `REOPEN` timestamp and the **running total continues from before — it never resets**.

**Invalid events are silently ignored** (no error, no output flag): any event for a ticket before its first valid `OPEN`; `OPEN` when already open; `PAUSE` when already paused; `RESUME` when the clock is running; `CLOSE` when already closed; `REOPEN` when not closed.

Events may arrive out of order. Sort all events by `timestamp_ms`; ties are broken by original arrival order (stable sort).

**"Now" is defined as the maximum `timestamp_ms` appearing anywhere in the stream** (including lines that are otherwise invalid). For a ticket still open when the stream ends: if its clock is running, count up to `now`; if paused, it counts only up to the pause. Such tickets appear in the output with `status: "open"`. An open ticket whose used time exceeds the limit has `breached: true`.

Return a list of `{"ticket_id", "used_ms", "breached", "status"}` for every ticket that had at least one valid `OPEN`, sorted by `ticket_id` ascending (string order). Tickets with no valid `OPEN` are omitted entirely.
