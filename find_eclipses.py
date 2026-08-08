#!/usr/bin/env python3
"""
Find every total (and hybrid) solar eclipse between 1986 and 2066.

The list is derived from the ephemeris, not from a published catalogue: new
moons are located first, then each one is tested to see whether the Moon's
umbra actually reaches the Earth's surface.

The test is the same criterion the rest of the project uses, evaluated at the
one place it matters.  The shadow axis is the line from the Sun's centre
through the Moon's centre; where it meets the ellipsoid is the deepest point of
the shadow, so an observer standing there decides the whole question:

    total   at that point when  r_moon - r_sun - separation  > 0
    annular at that point when  r_sun - r_moon - separation  > 0

An eclipse showing only the first is total, one showing both at different
moments along its track is hybrid (annular-total), and one showing only the
second is annular and is skipped.  Working at the axis point rather than on a
global grid keeps this exact for umbrae only a few tens of kilometres wide,
which a grid coarse enough to sweep 80 years would step straight over.

    python find_eclipses.py            ->  data/index.json
"""

import json
import os
import sys

import numpy as np

from eclipse_core import (SkyTable, classify, eph, geodetic,
                          local_circumstances, sun_moon_geocentric, ts)

YEAR_FROM, YEAR_TO = 1986, 2066

# The eclipse the page opens with. This is THE place it is defined: it travels
# to the browser inside data/index.json, so nothing downstream repeats it.
DEFAULT_ECLIPSE = "2026-08-12"

COARSE_STEP_H = 6.0        # new-moon bracketing
WINDOW_H = 6.0             # scanned either side of each new moon
WINDOW_STEP_S = 180.0      # inside that window
MAX_SEP_DEG = 4.0          # geocentric Sun-Moon separation worth examining

HERE = os.path.dirname(os.path.abspath(__file__))

# Coarse boxes used only to describe where a path goes, most specific first.
# Approximate by design: the tag is a human hint, not a geographic claim.
REGIONS = [
    ("Antarctica", -90, -60, -180, 180), ("Arctic", 72, 90, -180, 180),
    ("Iceland", 62, 67, -25, -13), ("Svalbard", 74, 81, 10, 35),
    ("Greenland", 59, 84, -73, -12), ("Alaska", 52, 72, -170, -130),
    ("Canada", 43, 75, -141, -52), ("USA", 25, 49, -125, -67),
    ("Mexico", 14, 33, -118, -86), ("Central America", 7, 19, -93, -77),
    ("Caribbean", 10, 27, -85, -59), ("Brazil", -34, 6, -74, -34),
    ("Argentina/Chile", -56, -17, -76, -53), ("South America", -56, 13, -82, -34),
    ("Spain", 36, 44, -10, 4), ("Portugal", 37, 42, -10, -6),
    ("France", 42, 51, -5, 8), ("UK", 49, 61, -11, 2),
    ("Scandinavia", 55, 72, 4, 32), ("Russia", 41, 78, 27, 180),
    ("Europe", 35, 60, -10, 40), ("Morocco", 27, 36, -14, -1),
    ("Algeria/Tunisia", 18, 38, -2, 12), ("Libya", 19, 34, 9, 26),
    ("Egypt", 21, 32, 24, 37), ("Sahara", 15, 32, -17, 38),
    ("West Africa", 3, 20, -18, 16), ("East Africa", -12, 18, 30, 52),
    ("Southern Africa", -35, -12, 11, 41), ("Africa", -35, 37, -18, 52),
    ("Arabia", 12, 33, 34, 60), ("Iran/Central Asia", 24, 48, 44, 80),
    ("India", 6, 36, 68, 90), ("China", 20, 54, 73, 135),
    ("Mongolia/Siberia", 45, 78, 80, 180), ("Japan", 30, 46, 129, 146),
    ("Southeast Asia", -11, 29, 92, 128), ("Indonesia", -11, 7, 95, 141),
    ("Australia", -44, -10, 112, 154), ("New Zealand", -48, -33, 165, 179),
    ("Pacific", -60, 65, 120, 180), ("Pacific", -60, 65, -180, -78),
    ("Atlantic", -60, 68, -78, 20), ("Indian Ocean", -60, 30, 20, 120),
]


def write_index_js(index):
    """The page reads the catalogue as a plain global, so file:// works too."""
    index.setdefault("default", DEFAULT_ECLIPSE)
    os.makedirs(os.path.join(HERE, "web"), exist_ok=True)
    with open(os.path.join(HERE, "web", "eclipse-index.js"), "w") as fh:
        fh.write("window.ECLIPSE_INDEX=" + json.dumps(index, separators=(",", ":"))
                 + ";\n")


def region_of(lat, lon):
    lon = (lon + 540.0) % 360.0 - 180.0
    for name, la0, la1, lo0, lo1 in REGIONS:
        if la0 <= lat <= la1 and lo0 <= lon <= lo1:
            return name
    return "Southern Ocean" if lat < -45 else "open ocean"


def main():
    t0 = ts.utc(YEAR_FROM, 1, 1)
    t1 = ts.utc(YEAR_TO, 12, 31)
    n = int((t1.tt - t0.tt) * 24 / COARSE_STEP_H)
    print(f"scanning {YEAR_FROM}-{YEAR_TO} for new moons "
          f"({n} steps of {COARSE_STEP_H:.0f} h)", flush=True)

    times = ts.tt_jd(t0.tt + np.arange(n) * COARSE_STEP_H / 24.0)
    # Geometric positions are plenty for bracketing a new moon, and skipping
    # the light-time solution makes this pass roughly ten times cheaper.
    sg = (eph["sun"] - eph["earth"]).at(times).position.km
    mg = (eph["moon"] - eph["earth"]).at(times).position.km
    cosang = ((sg * mg).sum(axis=0)
              / (np.linalg.norm(sg, axis=0) * np.linalg.norm(mg, axis=0)))
    sep = np.degrees(np.arccos(np.clip(cosang, -1, 1)))

    dips = np.where((sep[1:-1] < sep[:-2]) & (sep[1:-1] <= sep[2:])
                    & (sep[1:-1] < MAX_SEP_DEG))[0] + 1
    print(f"  {len(dips)} new moons close enough to be worth checking "
          f"(separation < {MAX_SEP_DEG:.0f} deg)", flush=True)

    nw = int(WINDOW_H * 3600 / WINDOW_STEP_S)
    offs = np.arange(-nw, nw + 1) * WINDOW_STEP_S
    found = []

    for j, i in enumerate(dips):
        base = times[int(i)]
        wt = ts.tt_jd(base.tt + offs / 86400.0)
        S, M = sun_moon_geocentric(wt)
        P, total, annular, axis_dist = classify(S, M)
        if not total.any():
            continue

        kind = "hybrid" if annular.any() else "total"
        # Greatest eclipse: the moment the axis passes closest to the centre.
        k = int(np.argmin(np.where(total | annular, axis_dist, np.inf)))
        # refine on a 2 s grid around it
        fine = ts.tt_jd(wt[k].tt + np.arange(-120, 121) * 2.0 / 86400.0)
        Sf, Mf = sun_moon_geocentric(fine)
        Pf, tf, af, adf = classify(Sf, Mf)
        kf = int(np.argmin(np.where(tf | af, adf, np.inf)))
        t_ge = fine[kf]
        lat_ge, lon_ge = geodetic(Pf[:, kf], t_ge)

        # Duration at the greatest-eclipse point, as a first estimate; the full
        # pipeline overwrites this with its own maximum when it runs.
        day = ts.utc(t_ge.utc.year, t_ge.utc.month, t_ge.utc.day)
        sec0 = (t_ge.tt - day.tt) * 86400.0
        sky = SkyTable(day, np.arange(sec0 - 600.0, sec0 + 600.0, 1.0))
        c = local_circumstances(sky, float(lat_ge), float(lon_ge))
        dur = c.get("duration", 0.0)

        # Region tag from the sequence of axis points that land on Earth. The
        # first and last few are dropped: there the axis grazes the limb and
        # skids across a lot of geography in a couple of minutes.
        on = np.where(total | annular)[0]
        trim = max(1, len(on) // 12)
        on = on[trim:-trim] if len(on) > 4 * trim else on
        la, lo = geodetic(P[:, on], wt[on])
        seq = []
        for tg in (region_of(a, b) for a, b in zip(np.atleast_1d(la),
                                                   np.atleast_1d(lo))):
            if not seq or seq[-1] != tg:
                seq.append(tg)
        if len(seq) > 4:                       # keep the ends, thin the middle
            mid = seq[1:-1]
            step = max(1, round(len(mid) / 2))
            seq = [seq[0]] + mid[::step][:2] + [seq[-1]]
        out_seq = []                           # thinning can re-introduce repeats
        for tg in seq:
            if not out_seq or out_seq[-1] != tg:
                out_seq.append(tg)
        seq = out_seq

        date = f"{t_ge.utc.year:04d}-{t_ge.utc.month:02d}-{t_ge.utc.day:02d}"
        found.append({
            "date": date,
            "type": kind,
            "greatest_utc": t_ge.utc_strftime("%H:%M:%S"),
            "greatest_lat": round(float(lat_ge), 3),
            "greatest_lon": round(float(lon_ge), 3),
            "max_duration_s": round(float(dur), 1),
            "regions": " - ".join(seq),
        })
        print(f"  {len(found):3d}. {date}  {kind:6s} "
              f"{int(dur) // 60}m{int(dur) % 60:02d}s  "
              f"{lat_ge:7.2f},{lon_ge:8.2f}  {found[-1]['regions']}", flush=True)

    found.sort(key=lambda e: e["date"])
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    out = {"generated_from": f"JPL DE440s, {YEAR_FROM}-{YEAR_TO}",
           "count": len(found), "default": DEFAULT_ECLIPSE, "eclipses": found}
    with open(os.path.join(HERE, "data", "index.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    write_index_js(out)

    n_total = sum(1 for e in found if e["type"] == "total")
    print(f"\n{len(found)} eclipses with a total phase "
          f"({n_total} total, {len(found) - n_total} hybrid) "
          f"-> data/index.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
