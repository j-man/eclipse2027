# TASK 11 — three clocks: place, viewer, UTC

Follow-up to TASK10. Wherever an event time is shown for a selected point or
marker, show **three** times, in this order:

1. **Local time at the place** — as built in TASK10, offset label included.
2. **The viewer's own time** — browser zone via `Intl.DateTimeFormat`
   (no lookup table involved), labeled `sinun aikasi` with its UTC offset,
   resolved for the eclipse's DATE (DST again).
3. **UTC**.

Rules:

- Hide the viewer row when the viewer's zone gives the same offset-and-time
  as the place's zone — no duplicate rows.
- Keep the display compact: three short rows or one line with separators,
  whichever fits the current card without crowding. Place time keeps the
  visual emphasis; viewer and UTC are secondary.
- Presentation only, nothing internal changes.

Validation: with browser zone forced to Europe/Helsinki (Playwright
`timezone_id`), a Tarifa 2027-08-02 totality at 09:07 UTC must show place
11:07 (+2), sinun aikasi 12:07 (+3), UTC 09:07. Add that to check.py; all
existing checks stay green. Bump version, one line in STATUS.md.
