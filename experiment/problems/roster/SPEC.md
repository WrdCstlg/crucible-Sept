# Problem 13: Shift rostering with backtracking

Implement `def make_roster(staff, shifts, rules)` in Python, using only the standard library.

Fill every seat of every shift with a staff member, using one exactly specified depth-first search. The answer is
the first complete roster that this search reaches. Do not modify the inputs.

## Input

- `staff`: a list of records `{"id": str, "skills": [str, ...], "max_minutes_week": int, "unavailable":
  ["YYYY-MM-DD", ...], "senior": bool}`.
- `shifts`: a list of records `{"id": str, "start": "YYYY-MM-DD HH:MM", "end": "YYYY-MM-DD HH:MM", "skill": str,
  "need": int, "needs_senior": bool}`.
- `rules`: `{"min_rest_minutes": int, "max_consecutive_days": int, "forbidden_pairs": [[id, id], ...]}`.

`staff` and `shifts` are always lists, but their records may be malformed (section 1). `rules` is always well formed:
`min_rest_minutes` ≥ 0, `max_consecutive_days` ≥ 1, and each pair is a list of two strings. A pair is unordered. A
pair that names an id which is not a valid staff member, or names the same id twice, has no effect. Times are local
wall-clock times with no time zones and no daylight-saving changes.

## 1. Validation

A **date** is valid only if it is exactly `YYYY-MM-DD` (10 characters: ASCII digits and two hyphens) and is a real
calendar date, years 0001–9999. A **timestamp** is valid only if it is exactly `YYYY-MM-DD HH:MM` (16 characters: a
valid date, one space, two ASCII digits, a colon, two ASCII digits) with hour 00–23 and minute 00–59. Below, "int"
means a Python `int` that is not a `bool`, and "string" means a `str`.

A staff record is **ignored** if any of these holds:

1. it is not a dict, or lacks one of the five keys (extra keys are allowed in any record);
2. `id` is not a non-empty string;
3. `skills` is not a list of strings (an empty list is fine);
4. `max_minutes_week` is not an int ≥ 0;
5. `unavailable` is not a list of valid dates (one bad entry makes the whole record ignored);
6. `senior` is not a bool.

A shift record is **ignored** if any of these holds:

1. it is not a dict, or lacks one of the six keys;
2. `id` is not a non-empty string;
3. `start` or `end` is not a valid timestamp, `end` is not later than `start`, or the shift lasts more than 1440
   minutes;
4. `skill` is not a string;
5. `need` is not an int ≥ 1;
6. `needs_senior` is not a bool.

**Duplicates.** After these checks, if two or more of the remaining staff records share an id, **all** of them are
ignored. The same applies to shifts. The records left are the **valid** staff and shifts; nothing else takes part
below.

## 2. Time terms

- The **length** of a shift is the number of minutes from `start` to `end`.
- A shift is **on** every calendar date that contains at least one minute of the half-open interval [`start`,
  `end`). A shift ending at exactly 00:00 is not on the date it ends. A shift is on one or two dates.
- Weeks run Monday to Sunday. The **week of a shift** is the week containing its `start` date. Its whole length
  belongs to that week, even when the shift runs into the next week.
- Ids are compared as Python strings (`<` on `str`, code point by code point), so `"s10" < "s9"` and `"Z" < "a"`.
  Skill names must match exactly.

## 3. Acceptable rosters

A roster, complete or partial, is **acceptable** when all of these hold:

1. **Skill.** Everyone on a shift has the shift's `skill` in their `skills`.
2. **No overlap.** Nobody holds two shifts that overlap. A and B overlap when A starts before B ends and B starts
   before A ends, so a shift ending at 14:00 does not overlap one starting at 14:00.
3. **Rest.** If someone holds shifts A and B and A ends at or before the start of B, then (B's start − A's end) ≥
   `min_rest_minutes`. This applies to any two of their shifts, including two on the same date.
4. **Weekly cap.** For each person and each week, the total length of their shifts belonging to that week is at most
   their `max_minutes_week`.
5. **Consecutive days.** A person works on a date if any of their shifts is on that date. Nobody may work on more
   than `max_consecutive_days` consecutive dates. Runs continue across weeks. A shift on two dates counts on both;
   with `max_consecutive_days` = 1, nobody can hold such a shift.
6. **Availability.** Nobody holds a shift that is on one of their `unavailable` dates.
7. **Forbidden pairs.** The two people of a forbidden pair are never on the same shift. They may hold different
   shifts, even overlapping ones.
8. **Senior.** Every `needs_senior` shift whose seats are all filled has at least one person with `senior` true.

## 4. The search

A valid shift with `need` = n has seats 0, 1, …, n−1. Each (shift, seat) is a **slot**. Sort all slots ascending by
(shift start time, shift end time, shift id, seat). The search fills the slots in this order, depth first. The
**partial roster** is the people placed in the earlier slots.

1. **Enter a slot** (shift s, seat k). Its candidates are the valid staff who have s's skill and, when k ≥ 1, whose
   id is greater than the id of the person in seat k−1 of s. Order them ascending by (W, id), where W is the total
   length of the shifts that person holds in the current partial roster that belong to the same week as s.
2. **Try** the candidates in that order. Place the candidate in the slot. If the partial roster is still
   acceptable, enter the next slot. Otherwise remove the candidate and try the next one.
3. **Backtrack.** When a slot has no more candidates, go back to the previous slot, remove its person, and try that
   slot's next candidate in the order fixed when that slot was entered (the partial roster is as it was then,
   so the order is unchanged).
4. **Finish.** When the last slot has been filled, the roster is the answer and `ok` is true. If the first slot runs
   out of candidates, there is no answer and `ok` is false. With no valid shifts there are no slots, and the answer
   is the empty roster with `ok` true.

The answer is the unique roster this procedure reaches first. A shift that cannot be filled is never skipped; it
makes the whole call fail. Because seat ids increase, each shift's people are in ascending id order. You may add
extra pruning or reorganise the procedure, but only if this never changes which roster is found first.

## Output

```python
{"ok": bool,
 "assignments": {shift_id: [staff_id, ...]},  # if ok: every valid shift, people in seat order; if not ok: {}
 "minutes": {staff_id: int},   # every valid staff member: total length of their shifts in "assignments" (0 if none)
 "ignored": {"staff": [...], "shifts": [...]}}  # 0-based input positions of the ignored records, ascending
```

## Size

Up to 1,000 valid staff, 10,000 shifts and 30,000 slots (the sum of `need`), so the search can be 30,000 slots deep
and one person may hold over a hundred shifts. The whole call must finish within a few seconds in CPython. The large
tests are built so that the specified search never has to undo more than a few slots at a time.

## Examples

Example 1 defines three helpers that the other examples reuse.

Example 1 (load order, ids compared as strings, increasing seat ids):

```python
def person(i, skills, off=(), senior=False):
    return {"id": i, "skills": skills, "max_minutes_week": 2400, "unavailable": list(off), "senior": senior}
def shift(i, start, end, skill, need=1, senior=False):
    return {"id": i, "start": start, "end": end, "skill": skill, "need": need, "needs_senior": senior}
def rules(rest=0, run=7, pairs=()):
    return {"min_rest_minutes": rest, "max_consecutive_days": run, "forbidden_pairs": [list(p) for p in pairs]}

make_roster([person(i, ["med"]) for i in ["s1", "s2", "s10"]],
            [shift("d1", "2026-03-02 09:00", "2026-03-02 17:00", "med", 2),
             shift("d2", "2026-03-03 09:00", "2026-03-03 17:00", "med", 2),
             shift("d3", "2026-03-04 09:00", "2026-03-04 13:00", "med")], rules())
# d1: s1, then s10 ("s10" < "s2"). d2 seat 0: s2 has W 0, but no id is greater than "s2", so seat 1 has no
# candidates; back to seat 0, which takes s1, and seat 1 takes s2. d3: s10 and s2 tie at W 480, s10 wins on id.
# -> {"ok": True, "assignments": {"d1": ["s1", "s10"], "d2": ["s1", "s2"], "d3": ["s10"]},
#     "minutes": {"s1": 960, "s10": 720, "s2": 480}, "ignored": {"staff": [], "shifts": []}}
```

Example 2 (rest across midnight, the senior check on the last seat, backtracking into an earlier shift):

```python
make_roster([person("ann", ["er"], senior=True), person("bob", ["er"]), person("cat", ["er"])],
            [shift("sun", "2026-03-08 22:00", "2026-03-09 06:00", "er"),
             shift("mon", "2026-03-09 18:00", "2026-03-09 23:00", "er", 2, senior=True)], rules(rest=780))
# sun -> ann. mon: ann has only 720 minutes of rest; [bob, cat] has no senior; cat in seat 0 leaves no seat 1.
# Back to sun -> bob. mon seat 0 -> ann; seat 1: bob lacks rest, cat fits.
# -> {"ok": True, "assignments": {"sun": ["bob"], "mon": ["ann", "cat"]},
#     "minutes": {"ann": 300, "bob": 480, "cat": 300}, "ignored": {"staff": [], "shifts": []}}
```

Example 3 (dates a shift is on, availability, consecutive days, no roster):

```python
make_roster([person("kim", ["icu"]), person("lee", ["icu"], ["2026-03-03", "2026-03-05"])],
            [shift("a", "2026-03-02 16:00", "2026-03-03 00:00", "icu"),
             shift("b", "2026-03-03 16:00", "2026-03-04 00:00", "icu"),
             shift("c", "2026-03-04 22:00", "2026-03-05 06:00", "icu")], rules(run=2))
# a is on 03-02 only, b on 03-03 only, c on 03-04 and 03-05. lee can never take b or c, and kim cannot take
# both b and c (three or more days in a row), so every branch fails.
# -> {"ok": False, "assignments": {}, "minutes": {"kim": 0, "lee": 0}, "ignored": {"staff": [], "shifts": []}}
```

Example 4 (ignored records, a forbidden pair, a valid person with no shifts):

```python
make_roster([person("amy", ["lab"], senior=True), person("ben", ["lab"], ["2026-02-30"]),
             person("cal", ["lab", "lab"]), person("dee", ["lab"]), person("dee", ["lab"], senior=True),
             person("eve", []), person("fay", ["lab"])],
            [shift("x1", "2026-03-02 08:00", "2026-03-02 12:00", "lab", 2),
             shift("x2", "2026-03-02 13:00", "2026-03-02 17:00", "lab", True),
             shift("x3", "2026-03-03 08:00", "2026-03-03 12:00", "lab", 2)],
            rules(pairs=[["cal", "amy"], ["ben", "cal"]]))
# ben: 2026-02-30 is not a date; both dee records share an id; x2: need True is not an int.
# x1: amy, then cal is forbidden with amy, so fay. x3: cal has W 0 and goes first; seat 1 must have an id
# greater than "cal", so fay.
# -> {"ok": True, "assignments": {"x1": ["amy", "fay"], "x3": ["cal", "fay"]},
#     "minutes": {"amy": 240, "cal": 240, "eve": 0, "fay": 480},
#     "ignored": {"staff": [1, 3, 4], "shifts": [1]}}
```
