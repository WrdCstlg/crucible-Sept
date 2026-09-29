# Problem 4: Support-ticket SLA clock

Implement `def compute_sla(stream)` in Python, using only the standard library.

## Input

`stream` is an iterable of strings. Each string is one CSV record: `timestamp_ms,ticket_id,event`.

A line is **well-formed** only if, after trimming surrounding whitespace, it splits on commas into **exactly 3 fields**, and, after trimming each field:

- the timestamp consists only of ASCII digits `0-9` (leading zeros allowed) and is read as a base-10 integer number of milliseconds;
- the ticket ID is non-empty (ticket IDs are case-sensitive: `t1` and `T1` are different tickets);
- the event is exactly one of `OPEN`, `PAUSE`, `RESUME`, `CLOSE`, `REOPEN` (uppercase).

Any other line, including an empty line, is **malformed** and is ignored completely: it has no effect on anything, including "now".

## Ordering

Events may arrive out of order. Process the well-formed events in order of timestamp; events with equal timestamps keep their original order in the stream (a stable sort).

## "Now"

"Now" is the largest timestamp among all well-formed lines, including well-formed events that are later ignored as invalid transitions.

## SLA

The SLA limit is **14,400,000 ms (4 hours)** of calendar time. A ticket **breaches only if its used time is strictly greater than the limit**. Exactly 14,400,000 ms does not breach.

## Ticket states

Each ticket is in one of four states: `NOT_OPENED` (initial), `RUNNING`, `PAUSED`, `CLOSED`. Used time accumulates only while the ticket is `RUNNING`: from the timestamp of the event that enters `RUNNING` to the timestamp of the event that leaves it. Time spent `PAUSED` or `CLOSED` never counts. For example, the stretch between a `PAUSE` and a later `CLOSE` does not count.

Transitions (any combination marked "ignored" is silently ignored: no error, no output, no effect):

| Event  | NOT_OPENED                       | RUNNING      | PAUSED       | CLOSED                                              |
|--------|----------------------------------|--------------|--------------|-----------------------------------------------------|
| OPEN   | to RUNNING, used time starts at 0 | ignored      | ignored      | to RUNNING, used time **resets to 0**               |
| PAUSE  | ignored                          | to PAUSED    | ignored      | ignored                                             |
| RESUME | ignored                          | ignored      | to RUNNING   | ignored                                             |
| CLOSE  | ignored                          | to CLOSED    | to CLOSED    | ignored                                             |
| REOPEN | ignored                          | ignored      | ignored      | to RUNNING, used time **continues** from its total  |

## End of stream

A ticket still `RUNNING` when the stream ends counts up to "now". A ticket still `PAUSED` counts only up to its pause.

## Output

Return a **list** (not a generator or other iterable) with one dict per ticket that had at least one valid `OPEN`. Tickets that never had a valid `OPEN` are omitted. An empty stream returns `[]`.

The list is sorted by `ticket_id` ascending in Python's default string order (code-point order, so `"T10"` sorts before `"T2"`).

Each dict has exactly these four keys:

- `"ticket_id"`: `str`
- `"used_ms"`: `int`
- `"breached"`: `bool` (`True` only if `used_ms` is strictly greater than 14,400,000; this applies to open tickets too)
- `"status"`: `"closed"` if the ticket's final state is `CLOSED`, otherwise `"open"`

## Format example

Input:

```
100,A,OPEN
400,A,CLOSE
```

Output:

```
[{"ticket_id": "A", "used_ms": 300, "breached": False, "status": "closed"}]
```
