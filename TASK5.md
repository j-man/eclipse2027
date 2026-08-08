# TASK 5 — every total solar eclipse, 1986–2066

Big one. The existing single-eclipse pipeline (see PLAN.md, STATUS.md) is the
starting point — extend it, don't rewrite what works. Do this task only after
TASK2–4 are done and committed.

## Goal

The same page, but with an **eclipse picker**: a dropdown (top corner) listing
every **total** solar eclipse from 1986 through 2066. Picking one loads that
eclipse's data and flies the map to its path. Everything else — animation,
controls, click-to-time, markers where applicable — keeps working.

**Totals only.** No annular, no partial. Hybrid (annular-total) eclipses ARE
included if any part of their path is total: generate only the total portion
and label them "hybrid" in the dropdown.

## Part 1 — discovery (extend gen_data.py or a new find_eclipses.py)

Find the eclipses from the ephemeris itself — do NOT hardcode a list from the
web (published catalogs are used for VALIDATION only, part 3):

1. Switch ephemeris to **DE440s** (DE421 only covers ~1900–2050; DE440s covers
   the full range and skyfield downloads it the same way, ~32 MB).
2. Scan 1986-01-01 → 2066-12-31 for new moons (Sun–Moon elongation minima;
   coarse 6 h grid + refine is plenty).
3. For each new moon, run a cheap version of the existing umbra check over a
   ±6 h window: does the umbra touch Earth's surface at any point (Moon's
   apparent angular radius > Sun's at that point → total there)?
   Classify: total / hybrid (both total and annular segments) / skip.
4. Output `data/index.json`: one row per eclipse — date, type (total/hybrid),
   greatest-eclipse time and location, max duration, a short human region tag
   (derive from path coordinates: continents/oceans crossed is fine to
   approximate; "Atlantic → Spain → Egypt" style).

Expect roughly 55–65 finds. Print the list; sanity-check count and a few known
ones (1991-07-11 Mexico 6m53s; 1999-08-11 Europe; 2009-07-22 Asia 6m39s —
longest of the century; 2017-08-21 USA; 2024-04-08 USA; 2026-08-12 Iceland/
Spain; 2027-08-02) before generating everything.

## Part 2 — per-eclipse generation

Run the existing single-eclipse pipeline for each catalog entry →
`data/eclipses/YYYY-MM-DD.js` (same window.-global trick as now, so file://
keeps working; name the global with the date or use a registration callback).
~9 s × ~60 = ~10 min total; print progress per eclipse. Handle gracefully:

- paths that cross the ±180° meridian (split polylines/polygons at the seam)
- polar paths (high-latitude geometry, umbra outlines may be very elongated)
- hybrid eclipses: total segment(s) only; if the total segment is tiny, keep
  it — that's the interesting part of a hybrid
- an eclipse whose generation fails: log it, skip it, don't kill the run

## Part 3 — validation (this is a correctness product)

- `check.py` grows a catalog test: compare the discovered list against the
  known facts embedded above (count in range, the 7 named eclipses present
  with dates exact, 2009-07-22 is the longest with ~6m39s ± a few s).
- Per-eclipse spot checks: for 2017-08-21 and 2024-04-08 assert a few
  published values (e.g. 2017 max ~2m40s near Hopkinsville KY; 2024 max
  ~4m28s near Torreón, Mexico) within ±5 s (durations may run ~2 s long from
  the mean-limb simplification — that tolerance is fine).
- Keep the existing browser tests passing for the default eclipse.

## Part 4 — UI

- Dropdown top-left (or a compact panel): rows like
  `2027-08-02 · total · 6m23s · Atlantic→Spain→Egypt`, sorted by date,
  default selection 2027-08-02.
- Selecting: lazy-load that eclipse's data file (inject <script>), rebuild
  layers, fly to path start, reset controls. No full page reload.
- Title box and version corner update per eclipse. Bump version.
- Markers: the current city markers are 2027-specific — show them only for
  2027 (a marker set keyed by eclipse date; empty for others is fine in v1).

## Update at the end

STATUS.md: what was done, the discovered eclipse count, validation results,
and total data size. Keep README.md in sync (it's public-repo facing).
