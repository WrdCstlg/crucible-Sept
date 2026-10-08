# Problem 15: Calendar recurrence expansion

Implement `def occurrences(event, range_start, range_end)` in Python, using only the standard library.

The function expands a recurring calendar event and returns its occurrences inside a time range. The rule language is
a subset of iCalendar (RFC 5545), defined completely below. Where this text differs from RFC 5545 or from common
calendar libraries, this text is what counts.

## Inputs and datetimes

- `event`: a dict with exactly the keys `"start"` (str), `"rule"` (str or `None`), `"exdates"` (list of str) and
  `"rdates"` (list of str).
- `range_start`, `range_end`: str.

A **datetime** is exactly 16 characters `YYYY-MM-DDTHH:MM`: ASCII digits, with `-`, `-`, `T` and `:` at the 5th, 8th,
11th and 14th characters; year 0001–9999; a real date of the Gregorian calendar (a leap year is divisible by 4, except
century years not divisible by 400); hour 00–23; minute 00–59. Times are local wall-clock times with no time zones.
Datetimes compare chronologically. The calendar runs from 0001-01-01 to 9999-12-31; days outside it **do not exist**.

## Rule syntax

A rule is one or more **parts** separated by `;`. A part must contain exactly one `=`: the text before it is the name,
the text after it is the value. Names and keywords are case-sensitive (unlike RFC 5545), and nothing outside this
grammar is accepted: no spaces, no empty part, no trailing `;`. Parts may come in any order.

| Name | Value | Default |
|---|---|---|
| `FREQ` (required) | `DAILY`, `WEEKLY`, `MONTHLY` or `YEARLY` | |
| `INTERVAL` | unsigned integer 1–100000 | 1 |
| `COUNT` | unsigned integer 1–1000000 | none |
| `UNTIL` | a datetime in the format above (not RFC 5545's) | none |
| `WKST` | a weekday code: `MO`, `TU`, `WE`, `TH`, `FR`, `SA` or `SU` | `MO` |
| `BYMONTH` | list of unsigned integers 1–12 | none |
| `BYMONTHDAY` | list of signed integers 1–31 or −31 to −1 | none |
| `BYDAY` | list of weekday codes, each optionally preceded by an ordinal, a signed integer 1–53 or −53 to −1 (`MO`, `2TU`, `-1FR`, `+3SA`) | none |
| `BYSETPOS` | list of signed integers 1–366 or −366 to −1 | none |

An **unsigned integer** is one or more ASCII digits with no leading zero (stricter than RFC 5545). A **signed
integer** is an unsigned integer, optionally preceded by `+` or `-`. A **list** is one or more items separated by
single commas; an item may repeat, which changes nothing.

The rule is **invalid** if:
1. a part has no `=` or more than one, its name is not in the table, or a name appears twice;
2. `FREQ` is missing, or `COUNT` and `UNTIL` are both present;
3. a value does not match its row of the table;
4. `BYDAY` has an entry with an ordinal while `FREQ` is `DAILY` or `WEEKLY`;
5. `BYMONTHDAY` is present while `FREQ` is `WEEKLY`;
6. `BYSETPOS` is present but none of `BYMONTH`, `BYMONTHDAY`, `BYDAY` is written in the rule.

For example `INTERVAL=02`, `BYDAY=MO,`, `BYDAY=0MO`, `BYDAY=+MO`, `BYMONTHDAY=0`, `FREQ=daily` and `BYHOUR=9` are all
invalid.

## Periods

`FREQ` cuts time into **periods**. Period 0 contains the start's day; period k comes k periods after it.

| FREQ | A period is | Period 0 |
|---|---|---|
| `DAILY` | one day | the start's day |
| `WEEKLY` | 7 days beginning on weekday `WKST` | the week containing the start's day |
| `MONTHLY` | a calendar month | the start's month |
| `YEARLY` | a calendar year | the start's year |

Only periods 0, INTERVAL, 2·INTERVAL, … are **used**. `WKST` matters only for `WEEKLY`: it decides which days share a
week, so it changes which days lie in the used weeks when INTERVAL > 1, and what `BYSETPOS` counts. Otherwise it is
ignored.

## Candidates

**Defaults.** Missing parts are filled from the start in exactly these cases:
- `WEEKLY` without `BYDAY`: `BYDAY` = the start's weekday.
- `MONTHLY` without `BYMONTHDAY` and without `BYDAY`: `BYMONTHDAY` = the start's day of the month.
- `YEARLY` without `BYMONTHDAY` and without `BYDAY`: `BYMONTHDAY` = the start's day of the month and, if `BYMONTH`
  is missing too, `BYMONTH` = the start's month.

The **candidates** of a used period are the existing days of that period that pass every filter present, defaults
included:
- `BYMONTH`: the day's month is listed.
- `BYMONTHDAY`: for some listed v, the day is the v-th day of its month (v > 0), or the |v|-th day counting back from
  the month's last day (v < 0; −1 is the last day). A month that lacks such a day contributes nothing for v: 31 in
  April, or 29 in February 2026, is **skipped, never moved** to another day.
- `BYDAY`: the day matches at least one entry. A bare code matches every day with that weekday. An entry with ordinal
  n matches only the n-th day with that weekday in the **scope** (for n < 0, counting from the scope's end: −1 is the
  last). The scope is the day's month when `FREQ` is `MONTHLY`, or `FREQ` is `YEARLY` and the rule has `BYMONTH`; it
  is the day's year when `FREQ` is `YEARLY` without `BYMONTH`. If the scope has fewer than |n| such weekdays, the
  entry matches nothing.

In RFC 5545 terms the parts behave as below; "expand" and "limit" both come out of the filtering just described.

| | DAILY | WEEKLY | MONTHLY | YEARLY |
|---|---|---|---|---|
| BYMONTH | limit | limit | limit | expand |
| BYMONTHDAY | limit | invalid | expand | expand |
| BYDAY | limit, bare codes only | expand, bare codes only | expand, or limit if BYMONTHDAY | expand, or limit if BYMONTHDAY |
| BYSETPOS | limit | limit | limit | limit |

**BYSETPOS.** List the period's candidates in date order. Position p > 0 is the p-th of them and p < 0 the |p|-th
from the end. Keep the candidates at the listed positions (a position past the end of the list selects nothing).
Without `BYSETPOS`, keep every candidate. `BYSETPOS` works on the period's full candidate list, before step 3 drops
days that are before the start or after `UNTIL`.

Each kept day gives a **rule instance**: that day at the start's time of day.

## Steps

1. If `start`, `range_start`, `range_end` or any item of `exdates` or `rdates` is not a valid datetime, return
   `{"ok": False, "error": "bad_datetime"}`.
2. Otherwise, if `rule` is not `None` and is invalid (an invalid `UNTIL` value included), return
   `{"ok": False, "error": "bad_rule"}`.
3. **Series.** The start is always the first entry of the series, even when it does not match the rule and even when
   it is later than `UNTIL` (RFC 5545 leaves both cases open). If there is a rule, go through the used periods in
   order and append, in date order, each rule instance that is later than the start and not later than `UNTIL`
   (`UNTIL` is inclusive); instances at or before the start are dropped. The series ends with the calendar; reaching
   9999-12-31 is not an error.
4. **COUNT.** If the rule has `COUNT`, keep only the first COUNT entries of the series (the start is entry 1).
5. **Extra and excluded dates.** Add every `rdates` item. These are not limited by the start, `UNTIL` or `COUNT`, and
   do not count toward `COUNT`. Then remove every entry equal to an `exdates` item (same date and time), whatever its
   origin. As this comes after `COUNT`, an excluded entry still uses up its place in the count.
6. Return `{"ok": True, "occurrences": [...]}`: the distinct remaining datetimes d with range_start ≤ d < range_end,
   in ascending order, written as datetimes. If range_end ≤ range_start, the list is empty.

## Size

A rule has at most 200 characters, `exdates` and `rdates` at most 1000 items each, and at most 50 000 occurrences are
returned. `range_end` lies at most 200 000 periods (of the rule's FREQ) after `range_start` and, when the rule has
`COUNT`, at most 200 000 periods after the start too. Without `COUNT`, the start may lie thousands of years before the
range. The whole call must finish within a few seconds in CPython; testing every calendar day, or walking through
every period from such a distant start, is too slow.

## Examples

Example 1 (BYSETPOS picks the last weekday of each month):

```python
occurrences({"start": "2026-01-30T09:00", "rule": "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1;COUNT=4",
             "exdates": [], "rdates": []}, "2026-01-01T00:00", "2027-01-01T00:00")
# -> {"ok": True, "occurrences": ["2026-01-30T09:00", "2026-02-27T09:00", "2026-03-31T09:00", "2026-04-30T09:00"]}
```

Example 2 (WKST decides which days share a week; INTERVAL=2 uses every other week):

```python
occurrences({"start": "1997-08-05T09:00", "rule": "FREQ=WEEKLY;INTERVAL=2;COUNT=4;BYDAY=TU,SU;WKST=SU",
             "exdates": [], "rdates": []}, "1997-01-01T00:00", "1998-01-01T00:00")
# used weeks (Sunday to Saturday): Aug 3-9 (Aug 3 is before the start), Aug 17-23, Aug 31-Sep 6
# -> {"ok": True, "occurrences": ["1997-08-05T09:00", "1997-08-17T09:00", "1997-08-19T09:00", "1997-08-31T09:00"]}
# with WKST=MO the used weeks are Aug 4-10 and Aug 18-24, giving Aug 5, 10, 19 and 24
```

Example 3 (day 31 is skipped in short months; UNTIL is inclusive; an excluded and an extra date):

```python
occurrences({"start": "2026-01-31T08:00", "rule": "FREQ=MONTHLY;UNTIL=2026-07-31T08:00",
             "exdates": ["2026-05-31T08:00"], "rdates": ["2026-02-28T08:00"]},
            "2026-02-01T00:00", "2026-08-01T00:00")
# -> {"ok": True, "occurrences": ["2026-02-28T08:00", "2026-03-31T08:00", "2026-07-31T08:00"]}
```

Example 4 (an ordinal is not allowed with WEEKLY):

```python
occurrences({"start": "2026-01-05T10:00", "rule": "FREQ=WEEKLY;BYDAY=1MO", "exdates": [], "rdates": []},
            "2026-01-01T00:00", "2026-02-01T00:00")
# -> {"ok": False, "error": "bad_rule"}
```
