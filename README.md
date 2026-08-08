# Eclipse 2027 — interactive totality map

Interactive map of the **total solar eclipse of August 2, 2027** — the longest
land totality of the 21st century (6 min 23 s near Luxor, Egypt).

Everything is computed from scratch: the only external input is NASA JPL's
DE421 ephemeris. No published eclipse tables, no external path data.

![Umbra over Luxor](shots/luxor.png)

## Features

- Slippy satellite map (Leaflet + Esri World Imagery), zoom & pan
- Path of totality: northern/southern limits, center line, duration contours
  (1 / 2 / 4 / 6 minutes)
- Animated umbra moving along its true track at true speed — video-style
  controls: play/pause, speed multiplier, time slider, UTC clock
- Keyboard: space = play/pause, arrow keys = step one minute

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install numpy skyfield
.venv/bin/python gen_data.py   # ~9 s; downloads de421.bsp (~17 MB) on first run
```

Then open `web/index.html` directly in a browser, or serve it:

```bash
cd web && python3 -m http.server 8000    # → http://localhost:8000
```

## How it works

A point on Earth is inside the umbra at time *t* when, as seen from that
point, *separation(Sun, Moon) + angular radius of Sun < angular radius of
Moon* (and the Sun is above the horizon). This observer-based criterion is
evaluated on numpy grids: a coarse global sweep finds the track, a local
refinement (60 s steps) traces the umbra outline with 60 radial rays, and
cross-track duration profiles yield the path limits and duration contours.

Two optimizations make the full computation run in ~9 seconds: apparent
Sun/Moon positions are evaluated once per time step from the geocenter (the
topocentric correction is then a vector subtraction, cross-validated against
skyfield's full pipeline to < 0.02″), and the ITRS→GCRS rotation matrix is
hoisted out of the per-point loop.

## Validation

| checkpoint | computed | published |
|---|---|---|
| Path start | 08:25 UTC, Atlantic | ✓ |
| Strait of Gibraltar | 08:48 UTC | ✓ |
| Luxor | 10:02–10:08 UTC, 6 min 23 s | ✓ |
| Maximum duration | 6 min 25 s | ~6 min 23 s (Δ from mean lunar limb) |
| Path end | 11:49 UTC, Indian Ocean | ✓ |

Durations run ~2 s long versus published predictions because the computation
uses the Moon's mean radius rather than the true limb profile.

Acceptance tests (`check.py`, Playwright + headless Chromium):

```bash
.venv/bin/pip install playwright && .venv/bin/playwright install chromium
.venv/bin/python check.py
```

## Files

```
gen_data.py            data generator (numpy + skyfield)
check.py               browser acceptance tests
data/eclipse2027.json  generated eclipse geometry
web/                   the page (Leaflet from CDN, no build step)
```

Map tiles © Esri. Ephemeris: JPL DE421.
