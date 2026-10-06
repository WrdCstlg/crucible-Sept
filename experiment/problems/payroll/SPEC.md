# Problem 10: Timesheet to payroll

Implement `def compute_pay(punches, rate)` in Python, using only the standard library. Money is integer cents.

- `punches`: list of `[in, out]` pairs of strings.
- `rate`: the regular hourly rate, an int ≥ 1 (cents per hour).

Times are local wall-clock times with no time zones and no daylight-saving changes.

## Steps

1. **Parse.** A timestamp is valid only if it is exactly `YYYY-MM-DD HH:MM` (16 characters, ASCII digits, one
   space), a real calendar date, hour 00–23 and minute 00–59. A punch is **invalid** if either timestamp is invalid
   or if `out` is not later than `in`.
2. **Round** each timestamp of a valid punch to a quarter hour by the 7-minute rule: with q = minute mod 15, round
   **down** if q ≤ 7 and **up** if q ≥ 8 (up may move into the next hour or the next day: `23:53` becomes `00:00` of
   the following day). A punch whose rounded `out` is not later than its rounded `in` is **empty**.
3. **Overlaps.** Sort the remaining punches by rounded `in`, then rounded `out`, then input index. Go through them in
   that order and keep a punch only if its rounded `in` is not earlier than the rounded `out` of the last kept punch;
   otherwise it is **overlapping** and is dropped (it does not extend anything). Kept punches are **shifts**.
4. **Days.** A shift belongs entirely to the calendar date of its rounded `in` (a shift that crosses midnight
   counts for the day it started). A day's **worked minutes** is the sum of its shifts' lengths.
5. **Weeks** run Monday to Sunday; a day belongs to the week containing its date.
6. **Daily classification.** For each day with worked minutes w: the first 480 minutes are regular, the next 240
   (minutes 481–720) are overtime, the rest are double time. **Seventh day:** if every one of the seven days of a
   week has worked minutes > 0, that week's Sunday instead has its first 480 minutes as overtime and the rest as
   double time (no regular minutes).
7. **Weekly overtime.** Within each week, walk the days Monday to Sunday keeping a running total of regular
   minutes. Regular minutes that would take the running total above 2400 become overtime instead (daily overtime
   and double time never count toward the 2400).
8. **Meal penalty.** A day earns one meal penalty if any of its shifts is longer than 300 minutes. At most one per
   day.
9. **Pay**, per week, each category rounded once (half up, i.e. `.5` goes up) from the week's minute totals:
   regular = R·rate/60, overtime = O·rate·1.5/60, double = D·rate·2/60, meal = (penalties)·rate. Compute these
   exactly (with integers or `fractions`), not with floating point.

## Output

```python
{"weeks": [ {"week_start": "YYYY-MM-DD",      # the Monday
             "regular_minutes": R, "overtime_minutes": O, "double_minutes": D, "meal_penalties": N,
             "regular_pay": ..., "overtime_pay": ..., "double_pay": ..., "meal_pay": ..., "total_pay": ...},
            ... ],                              # only weeks with a shift, sorted by week_start
 "ignored": [indices of invalid, empty and overlapping punches, ascending]}
```

`total_pay` is the sum of the four pay fields.

## Examples

Example 1 (rounding, daily overtime, meal penalty):

```python
compute_pay([["2026-03-02 08:07", "2026-03-02 18:08"]], 2000)
# 08:07 -> 08:00, 18:08 -> 18:15: 615 minutes = 480 regular + 135 overtime; one shift over 300 minutes
# -> {"weeks": [{"week_start": "2026-03-02", "regular_minutes": 480, "overtime_minutes": 135,
#                "double_minutes": 0, "meal_penalties": 1, "regular_pay": 16000, "overtime_pay": 6750,
#                "double_pay": 0, "meal_pay": 2000, "total_pay": 24750}], "ignored": []}
```

Example 2 (a shift crossing midnight counts for its start day, which here is a Sunday; overlapping, invalid and
empty punches are ignored):

```python
compute_pay([["2026-03-08 22:00", "2026-03-09 03:00"], ["2026-03-09 02:00", "2026-03-09 06:00"],
             ["2026-03-09 25:00", "2026-03-09 26:00"], ["2026-03-09 09:00", "2026-03-09 09:05"]], 1500)
# -> {"weeks": [{"week_start": "2026-03-02", "regular_minutes": 300, "overtime_minutes": 0,
#                "double_minutes": 0, "meal_penalties": 0, "regular_pay": 7500, "overtime_pay": 0,
#                "double_pay": 0, "meal_pay": 0, "total_pay": 7500}], "ignored": [1, 2, 3]}
```

Example 3 (weekly overtime: Monday–Friday 09:00–18:00, Saturday 09:00–15:00, all in the week of 2026-03-02):

```python
punches = [[f"2026-03-0{d} 09:00", f"2026-03-0{d} 18:00"] for d in range(2, 7)] + \
          [["2026-03-07 09:00", "2026-03-07 15:00"]]
compute_pay(punches, 1000)
# Mon-Fri: 480 regular + 60 overtime each. By Friday the week has 2400 regular minutes, so Saturday's 360 are overtime.
# -> {"weeks": [{"week_start": "2026-03-02", "regular_minutes": 2400, "overtime_minutes": 660,
#                "double_minutes": 0, "meal_penalties": 6, "regular_pay": 40000, "overtime_pay": 16500,
#                "double_pay": 0, "meal_pay": 6000, "total_pay": 62500}], "ignored": []}
```

Example 4 (seventh day: Monday–Saturday 09:00–13:00, Sunday 08:00–18:00):

```python
punches = [[f"2026-03-0{d} 09:00", f"2026-03-0{d} 13:00"] for d in range(2, 8)] + \
          [["2026-03-08 08:00", "2026-03-08 18:00"]]
compute_pay(punches, 1200)
# -> {"weeks": [{"week_start": "2026-03-02", "regular_minutes": 1440, "overtime_minutes": 480,
#                "double_minutes": 120, "meal_penalties": 1, "regular_pay": 28800, "overtime_pay": 14400,
#                "double_pay": 4800, "meal_pay": 1200, "total_pay": 49200}], "ignored": []}
```
