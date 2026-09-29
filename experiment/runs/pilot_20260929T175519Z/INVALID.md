# Invalid pilot run: harness bug

Arms A and B produced no gradeable output in this run. The harness (`experiment/arms.py`) called the
Antigravity SDK's `conversation.total_usage` as a method; it is a property, so every Gemini call raised
`TypeError: 'UsageMetadata' object is not callable` *after* the model had answered, and the answer was
discarded before it was saved. This was a bug in the experiment harness, not a model outcome.

The summary in this folder also reported "H1 gap closed: 0.0". That figure is wrong: the first version of
`run_pilot.py` counted harness crashes as model failures.

Arm C (Claude Opus 5.5) completed normally here: 5/5 runs passed all 39 hidden cases, total cost $0.15.

Fixes: the answer is now saved before usage is read, usage is read safely, and harness crashes are reported
separately and excluded from pass rates. The pilot was rerun in full (all three arms) with the unchanged,
frozen test set. The design (runs per arm, models, settings) was not changed after seeing these results.
