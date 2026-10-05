# Problem 5: Business-hours SLA clock (priorities, holidays, breach time)

Implement `def compute_sla(stream)` in Python, using only the standard library.

## Input

`stream` is an iterable of strings. Each string is one CSV record.

A line is **well-formed** only if, after trimming surrounding whitespace, it splits on commas into **3 or 4 fields**
and, after trimming each field:

- field 1, the minute, consists only of ASCII digits `0-9` (leading zeros allowed) and is read as a base-10 integer:
  minutes since **Monday 00:00 of week 0**;
- field 2, the ticket ID, is non-empty (IDs are case-sensitive: `t1` and `T1` are different tickets);
- field 3, the event, is exactly one of `OPEN`, `PRIORITY`, `PAUSE`, `RESUME`, `CLOSE`, `REOPEN`, `HOLIDAY`
  (uppercase);
- `OPEN` and `PRIORITY` have **exactly 4** fields, and field 4 is exactly one of `P1`, `P2`, `P3`, `P4` (uppercase);
- every other event has **exactly 3** fields;
- `HOLIDAY` lines have ticket ID exactly `*`; any other event with ticket ID `*` is malformed.

Any other line, including an empty line, is **malformed** and ignored completely: it has no effect on anything.

## Calendar

Minute `m` lies on day `d = m // 1440`, weekday `d % 7` (0 = Monday ... 6 = Sunday), at minute-of-day `m % 1440`.

Minute `m` is a **business minute** if and only if all of these hold:

- its weekday is Monday to Friday (0-4);
- its minute-of-day is in `[540, 1020)`, that is 09:00 inclusive to 17:00 exclusive;
- its day is not a holiday.

A well-formed `HOLIDAY` line at minute `m` declares the whole day `m // 1440` a holiday. Holidays are a calendar,
not events: they apply wherever they appear in the stream (before or after any ticket event, before or after
"now"), and declaring the same day twice is the same as declaring it once.

## Ordering and "now"

Ticket events (every well-formed line except `HOLIDAY`) may arrive out of order. Process them in order of minute;
events with the same minute keep their original order in the stream (a stable sort).

"Now" is the largest minute among all well-formed ticket events, including events later ignored as invalid
transitions. `HOLIDAY` lines never affect "now". If there are no well-formed ticket events, return `[]`.

## Priorities and limits

| Priority | Limit (business minutes) |
|---|---|
| `P1` | 240 |
| `P2` | 480 |
| `P3` | 1440 |
| `P4` | 2400 |

A ticket's priority is set by `OPEN` and changed by `PRIORITY`. The limit that applies at any moment is the limit of
the ticket's priority at that moment.

## Ticket states

Each ticket is in one of four states: `NOT_OPENED` (initial), `RUNNING`, `PAUSED`, `CLOSED`.
Transitions (any combination marked "ignored" is silently ignored: no error, no effect):

| Event | NOT_OPENED | RUNNING | PAUSED | CLOSED |
|---|---|---|---|---|
| `OPEN,<P>` | to RUNNING, priority P, used 0 | ignored | ignored | to RUNNING, priority P, used **resets to 0**, breach **cleared** |
| `PRIORITY,<P>` | ignored | priority becomes P | priority becomes P | ignored |
| `PAUSE` | ignored | to PAUSED | ignored | ignored |
| `RESUME` | ignored | ignored | to RUNNING | ignored |
| `CLOSE` | ignored | to CLOSED | to CLOSED | ignored |
| `REOPEN` | ignored | ignored | ignored | to RUNNING, used **continues**, breach **kept**, priority kept |

## Used time

An event at minute `m` takes effect at the start of minute `m`. A ticket's **used time at minute `t`** is the number
of business minutes `x < t` during which it was `RUNNING` (its state during minute `x` is its state after every
event at minute `x` has been applied), counted since its most recent valid `OPEN`.

## Breach

A ticket **breaches at minute `t`** if `t <= now` and, after every event at minute `t` has been applied, its used time
at `t` is **strictly greater** than the limit of its priority at that point. `breached_at` is the **first** such
minute. A breach is sticky: later events (including a `PRIORITY` that raises the limit) do not undo it. Only a valid
`OPEN` from `CLOSED` clears it.

Consequences worth stating: a ticket that ran for exactly its limit has not breached; a `PRIORITY` change can cause a
breach immediately (used time already above the new limit) even while `PAUSED`; a `PRIORITY` raise at the very minute
a breach would occur prevents it, because events at a minute are applied before that minute is checked.

## Output

Return a **list** (not a generator or other iterable) with one dict per ticket that had at least one valid `OPEN`,
sorted by `ticket_id` ascending in Python's default string order (code-point order: `"T10"` before `"T2"`).

Each dict has exactly these six keys:

- `"ticket_id"`: `str`
- `"priority"`: `str`, the ticket's priority at "now" (`"P1"` to `"P4"`)
- `"used_minutes"`: `int`, its used time at "now"
- `"breached"`: `bool`
- `"breached_at"`: `int` minute of the first breach, or `None` if not breached
- `"status"`: `"running"`, `"paused"` or `"closed"`, its state at "now"

## Performance

Inputs may have up to 200,000 lines, minutes up to 1,000,000,000 and up to 20,000 holiday lines. Each call must
finish within 10 seconds in CPython on a typical laptop. Counting minute by minute over the whole span will not.

## Examples

Example 1 (format; Monday 09:00 is minute 540):

```
540,A,OPEN,P2
600,A,CLOSE
```

```
[{"ticket_id": "A", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
```

Example 2 (only business minutes count; Friday 16:00 is minute 6720, next Monday 10:00 is minute 10680):

```
6720,B,OPEN,P1
10680,B,PAUSE
```

```
[{"ticket_id": "B", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "paused"}]
```

Example 3 (breach time: opened Monday 09:00 at P1, the 241st business minute is minute 780, so the breach is
at minute 781):

```
540,C,OPEN,P1
900,C,CLOSE
```

```
[{"ticket_id": "C", "priority": "P1", "used_minutes": 360, "breached": True, "breached_at": 781, "status": "closed"}]
```

Example 4 (a holiday on Monday of week 0 declared at the end of the stream; the ticket runs from Monday 09:00 to
Tuesday 10:00 but only Tuesday's 60 minutes count; malformed lines are ignored):

```
540,D,OPEN,P3
2040,D,PAUSE
open,D,RESUME
2100,D,RESUME,P1
5,*,HOLIDAY
```

```
[{"ticket_id": "D", "priority": "P3", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}]
```
