# TASK 5 — external-oracle test table

Add a validation layer to `check.py` (or a separate `check_oracle.py`): compare
our computed local circumstances against independently published values.

## Getting the reference values — IMPORTANT

Do NOT write the reference table from memory. Model memory is exactly the
error source this test exists to catch (this project already had one "known"
timestamp that was an hour off). Fetch the published local-circumstances data
for the 2027-08-02 eclipse from an authoritative source — EclipseWise
(eclipsewise.com, Fred Espenak) has city tables, NASA GSFC eclipse pages work
too. Use your web tools; put the source URL and retrieval date in a comment
next to the table. If you cannot reach any authoritative source, STOP and say
so — do not fill the table from memory.

## The test

- ~10–15 sites spread along the path (Spain, Gibraltar/Ceuta, North Africa,
  Luxor, Red Sea coast, + one or two near the edges of the path).
- For each: published totality duration and time of maximum vs. our
  `gen_data.py` computation at those exact coordinates.
- Tolerances: duration ±5 s (we run ~+2 s from the mean-limb simplification —
  assert the signed difference stays within [-3 s, +5 s] to catch systematic
  drift in either direction), time of maximum ±30 s.
- Also assert one *negative* case: a city clearly outside the path (e.g.
  Madrid) gets zero totality from us.
- Output a small table in the test log: site, published, computed, delta.
- Update STATUS.md with the results table.
