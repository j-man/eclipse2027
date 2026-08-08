# TASK 2 — click-to-time

Read PLAN.md and STATUS.md first for context. This is a small increment on the
existing, working page in `web/`. Do not regenerate data; `gen_data.py` and its
output stay as they are unless you find you need one extra field.

## Feature

When the user clicks anywhere on the map:

1. Find the animation time at which the umbra center is closest to the clicked
   point (nearest umbra sample by great-circle distance; linear interpolation
   between the two neighboring samples for a smooth result).
2. Set the animation clock to that time, **pause playback**, and update the
   umbra, slider and clock display accordingly.
3. If the clicked point is inside the path of totality, also show a small popup
   at the clicked location: local totality duration (interpolate from the
   cross-track data you have — if the current data cannot answer this, show
   the time only, don't guess) and the UTC time of maximum at that point.
4. Clicks on existing markers/popups keep their current behavior.

## Constraints

- Keep it in `web/app.js` + minimal CSS; no new dependencies, no build step.
- Don't break the existing controls: play resumes from the newly set time,
  arrow keys still step one minute, space still toggles.
- Map dragging must NOT trigger the click behavior (Leaflet distinguishes
  `click` from drag already — just don't bind to `mousedown`).
- Update `check.py` with at least one test for this (click a known point →
  clock shows expected time ± a few minutes, animation paused).
- Update STATUS.md briefly when done.
