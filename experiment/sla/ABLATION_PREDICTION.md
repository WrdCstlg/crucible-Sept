# Spec ablation: prediction (written before the run)

Written: 2026-09-29, before launching the ablation. Test set unchanged (FROZEN.json, 39 cases).

## What changes
All three arms receive `SPEC_v0_original.md` (the user's spec before review) instead of `SPEC.md`.
Everything else is identical to pilot_20260929T180102Z, where every arm scored 39/39 on every run.

## Fairness label
This does not measure pure capability. The hidden tests encode decisions made *after* review, so some
v0 failures are models reasonably guessing differently where v0 was silent, or following a v0 rule
that was later changed. What it measures is how much the spec review changed outcomes.

## Where v0 differs from the final spec
1. Closed tickets: v0 never says what OPEN, PAUSE or RESUME do on a closed ticket. A literal reading
   ("RESUME when the clock is running" is invalid) lets RESUME restart a closed ticket's clock.
   Final: OPEN resets used time to 0; PAUSE and RESUME are ignored.
2. "Now": v0 says malformed lines are skipped but also that "now" includes "lines that are otherwise
   invalid". Final: malformed lines never affect "now".
3. No definition of a well-formed line (decimal or signed timestamps, lowercase events, empty IDs,
   trailing commas).
4. v0 never states the value "closed" for status, or the output types.

## Prediction
- Hand cases H1-H6 still pass in most runs (v0 fully determines them).
- Failures concentrate in E05, E06 (closed-ticket RESUME/PAUSE), E07, E22 (OPEN reset),
  E15, E16 (malformed lines and "now"), and the random and stress layers, which mix all of these.
- Strict pass rates drop well below 100% in all three arms.
- No prediction about which model degrades more.
