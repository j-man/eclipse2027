# TASK 3 — more site markers

Read PLAN.md / STATUS.md for context. Small increment: add more named markers
(same style as the existing Malaga/Luxor ones) with popups showing local
totality duration and time of maximum, computed from the data as before.

## Markers to add

| name | lat | lon | note |
|---|---|---|---|
| Sevilla | 37.3891 | -5.9845 | big city, southern Spain |
| Cádiz | 36.5271 | -6.2886 | big city, southern Spain |
| Tarifa | 36.0143 | -5.6044 | near-centerline, best mainland-Spain duration |
| Gibraltar | 36.1408 | -5.3536 | |
| Ceuta | 35.8894 | -5.3213 | |
| Sfax | 34.7406 | 10.7603 | Tunisia |
| Wadi Lahmy Azur Resort | 24.2369 | 35.4118 | Red Sea coast, Egypt (coords from OpenStreetMap, verified) |

City coordinates above are city centers; sanity-check each against the
computed path (all should be inside or near the zone — if one lands far
outside, flag it rather than silently plotting).

## Constraints

- If a marker is outside the path of totality, still show it but say so in the
  popup ("outside totality — XX% partial" if magnitude is computable, otherwise
  just "outside the path of totality").
- Marker data belongs in gen_data.py's markers list (regenerate data) OR in a
  static list in app.js — choose whichever the current architecture already
  uses for Malaga/Luxor and stay consistent.
- Keep the map uncluttered: at low zoom the labels must not overlap into mush —
  Leaflet default popup-on-click (no permanent labels) is fine.
- Update check.py (marker count) and STATUS.md briefly.
