# TASK 10 — local time zones instead of bare UTC

All times in the UI are currently UTC. A user standing in Málaga wants to know
the clock-on-the-wall time of totality, not a UTC value they must convert.

## What to build

1. **Time zone from the clicked/selected location, not from the viewer's
   browser.** When the user clicks a point or picks a marker, show times in
   that place's local zone. The viewer may be in Finland planning a trip to
   Egypt — browser zone is the wrong answer.
2. Display format: local time first, UTC secondary:
   `11:07:41 (UTC+2) — 09:07:41 UTC`. Include the UTC offset label so there
   is no ambiguity. If the zone has a name available (e.g. `Europe/Madrid`),
   show it in a tooltip or smaller text.
3. **Zone lookup must work offline-ish and self-contained** (the page has no
   backend). Acceptable approaches, pick the simplest that works:
   - a small embedded coordinate→zone dataset (e.g. simplified tz polygon
     lookup) covering the eclipse paths in the catalogue, or
   - a longitude-based offset estimate ONLY as documented fallback, clearly
     labeled `~UTC+2` with the tilde. Never present an estimated offset as
     exact.
   Note DST: 2027-08-02 in Spain is UTC+2 (CEST), not UTC+1. Whatever
   mechanism you choose must produce the DST-correct offset for the eclipse's
   DATE, not for today. `Intl.DateTimeFormat` with an IANA zone name gives
   this for free — so mapping coordinates to an IANA name and letting Intl do
   offset math is the preferred design.
4. Markers: each predefined marker already knows its country — give markers an
   explicit IANA zone field in their data, no lookup needed there.
5. Do NOT change any computation or stored times — everything internal stays
   UTC. This is presentation only.

## Validation

- Marker Tarifa: totality shown as local CEST, exactly UTC+2 on 2027-08-02.
- Marker Luxor: UTC+2 (Egypt, no DST).
- A click in Iceland for 2026-08-12: UTC+0.
- check.py: add assertions for at least the Tarifa and Luxor cases; all
  existing checks stay green.

Bump version, one line in STATUS.md.
