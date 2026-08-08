#!/usr/bin/env python3
"""Compare our computed local circumstances against independently published values.

REFERENCE SOURCE
    "Path of the Total Solar Eclipse of 2027 Aug 02", Fred Espenak, NASA/GSFC
    https://eclipse.gsfc.nasa.gov/SEpath/SEpath2001/SE2027Aug02Tpath.html
    Retrieved 2026-08-08.

The published values below are transcribed verbatim in the source page's own
notation (sexagesimal coordinates, "MMmSS.Ss" durations) and parsed here, so the
table can be checked against the page line by line without doing any arithmetic.

Every row is a point on the central line, where the published Universal Time is
by definition the instant of maximum eclipse for an observer standing there and
the published duration is that observer's totality.  Two rows taken from the
northern/southern limit columns and one city well outside the path exercise the
edge and negative cases.

    .venv/bin/python check_oracle.py
"""

import json
import os
import sys

import numpy as np

from eclipse_core import SkyTable, local_circumstances, ts

HERE = os.path.dirname(os.path.abspath(__file__))

SOURCE = ("NASA/GSFC SE2027Aug02Tpath (Espenak), retrieved 2026-08-08")

# Espenak's solution for this eclipse uses this value; skyfield carries its own
# long-term model. The difference is reported in the output because it is the
# main reason our times cannot match the published ones exactly.
PUBLISHED_DELTA_T = 71.7

# --------------------------------------------------------------- reference data
# (label, published UT of maximum, central-line latitude, longitude, duration)
# Transcribed from the "Central Line" and "Central Duration" columns.
CENTRAL_LINE = [
    ("Atlantic, path start", "08:26", "30°29.3'N", "036°14.0'W", "03m24.6s"),
    ("Atlantic, mid-ocean",  "08:36", "34°41.3'N", "017°00.2'W", "04m16.5s"),
    ("Atlantic off Morocco", "08:44", "35°33.9'N", "008°31.3'W", "04m42.6s"),
    ("Strait of Gibraltar",  "08:48", "35°43.1'N", "005°00.6'W", "04m53.8s"),
    ("Algerian coast",       "08:54", "35°42.5'N", "000°19.8'W", "05m09.0s"),
    ("Algeria",              "09:02", "35°21.6'N", "005°06.3'E", "05m26.5s"),
    ("Tunisia, near Sfax",   "09:10", "34°43.4'N", "009°51.5'E", "05m41.5s"),
    ("Libya",                "09:20", "33°37.1'N", "015°04.8'E", "05m56.8s"),
    ("Libya, Cyrenaica",     "09:34", "31°37.4'N", "021°23.1'E", "06m12.2s"),
    ("Egypt, Western Desert", "09:50", "28°50.9'N", "027°33.4'E", "06m21.6s"),
    ("Egypt, near Luxor",    "10:06", "25°38.3'N", "032°58.8'E", "06m22.7s"),
    ("Egypt, Red Sea coast", "10:12", "24°20.1'N", "034°53.1'E", "06m21.2s"),
    ("Saudi Arabia",         "10:22", "22°02.6'N", "037°57.5'E", "06m16.3s"),
    ("Saudi Arabia, Asir",   "10:40", "17°32.0'N", "043°23.0'E", "06m00.8s"),
    ("Gulf of Aden",         "11:00", "11°51.1'N", "049°46.1'E", "05m34.0s"),
    ("Indian Ocean",         "11:20", "05°08.3'N", "057°39.1'E", "04m56.3s"),
    ("Indian Ocean, path end", "11:40", "03°54.4'S", "070°51.6'E", "04m01.1s"),
]

# Greatest eclipse, from the summary block of the same page.
GREATEST = ("10:06:37.7", "25°30.3'N", "033°11.0'E", "06m22.6s")

# Points read off the Northern/Southern Limit columns. A limit point is by
# definition the boundary of totality, so its published duration is zero.
LIMITS = [
    ("N limit off Tarifa", "08:48", "36°46.8'N", "005°19.2'W"),
    ("S limit, Egypt",     "10:06", "24°41.7'N", "032°14.2'E"),
]

# Published path width in km at selected times, for a cross-track check.
WIDTHS = [("08:48", 237), ("09:20", 250), ("10:06", 258), ("10:40", 259),
          ("11:20", 251)]

# A capital city far outside the path: we must find no totality at all.
OUTSIDE = [("Madrid", 40.4168, -3.7038)]

# --------------------------------------------------------------- tolerances
DUR_MIN, DUR_MAX = -3.0, 5.0     # signed seconds, per the task brief
TMAX_TOL = 30.0                  # seconds


def dms(text):
    """Parse "036°14.0'W" / "03°54.4'S" into signed decimal degrees."""
    hemi = text[-1]
    deg, rest = text[:-1].split("°")
    value = float(deg) + float(rest.rstrip("'")) / 60.0
    return -value if hemi in "WS" else value


def dur(text):
    """Parse "06m22.6s" into seconds."""
    m, s = text.rstrip("s").split("m")
    return float(m) * 60.0 + float(s)


def ut(text):
    parts = [float(x) for x in text.split(":")]
    return parts[0] * 3600 + parts[1] * 60 + (parts[2] if len(parts) > 2 else 0.0)


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * 6378.137 * np.arcsin(np.sqrt(a))


def hhmmss(sec):
    sec = round(sec % 86400, 1)
    return f"{int(sec // 3600):02d}:{int(sec % 3600 // 60):02d}:{sec % 60:04.1f}"


results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("  PASS  " if ok else "  FAIL  ") + name + ("  " + detail if detail else ""))


def main():
    epoch = ts.utc(2027, 8, 2, 0, 0, 0)
    our_dt = (epoch.tt - epoch.ut1) * 86400.0

    print(f"Reference: {SOURCE}")
    print(f"delta-T: published {PUBLISHED_DELTA_T:.1f} s, skyfield "
          f"{our_dt:.1f} s ({our_dt - PUBLISHED_DELTA_T:+.1f} s)\n")

    # One grid covering every partial phase along the path, 2 s steps to match
    # what gen_data.py uses for its site markers.
    sky = SkyTable(epoch, np.arange(5 * 3600.0, 15 * 3600.0, 2.0))

    print("Central line — published (Espenak) vs computed")
    print(f"  {'site':24s} {'pub max':>10s} {'our max':>10s} {'dt':>7s}"
          f" {'pub dur':>8s} {'our dur':>8s} {'ddur':>7s}")

    d_times, d_durs = [], []
    for label, t_pub, lat_s, lon_s, dur_s in CENTRAL_LINE:
        lat, lon = dms(lat_s), dms(lon_s)
        c = local_circumstances(sky, lat, lon)
        if "duration" not in c:
            check(f"central-line site has totality: {label}", False,
                  "no totality computed")
            continue
        dt = c["max_s"] - ut(t_pub)
        dd = c["duration"] - dur(dur_s)
        d_times.append(dt)
        d_durs.append(dd)
        print(f"  {label:24s} {t_pub + ':00':>10s} {hhmmss(c['max_s']):>10s}"
              f" {dt:>+7.1f} {dur(dur_s):>8.1f} {c['duration']:>8.1f} {dd:>+7.1f}")

    print()
    check("1. every central-line duration within [-3, +5] s of published",
          all(DUR_MIN <= d <= DUR_MAX for d in d_durs),
          f"range {min(d_durs):+.1f} .. {max(d_durs):+.1f} s, "
          f"mean {np.mean(d_durs):+.2f} s")
    check("2. every time of maximum within 30 s of published",
          all(abs(d) <= TMAX_TOL for d in d_times),
          f"range {min(d_times):+.1f} .. {max(d_times):+.1f} s, "
          f"mean {np.mean(d_times):+.2f} s")

    # Greatest eclipse, quoted to a tenth of a second on the source page.
    t_pub, lat_s, lon_s, dur_s = GREATEST
    g = local_circumstances(sky, dms(lat_s), dms(lon_s))
    gdt, gdd = g["max_s"] - ut(t_pub), g["duration"] - dur(dur_s)
    check("3. greatest eclipse matches at the published coordinates",
          DUR_MIN <= gdd <= DUR_MAX and abs(gdt) <= TMAX_TOL,
          f"max {hhmmss(g['max_s'])} vs {t_pub} ({gdt:+.1f} s), "
          f"dur {g['duration']:.1f} vs {dur(dur_s):.1f} s ({gdd:+.1f} s)")

    # Path limits: a published limit point sits on the boundary, so totality
    # there is zero. Duration grows as sqrt(distance) inside the edge, which
    # makes seconds a hypersensitive unit; the honest test is that the point
    # lands within a couple of km of our own edge.
    print()
    for label, t_pub, lat_s, lon_s in LIMITS:
        c = local_circumstances(sky, dms(lat_s), dms(lon_s))
        d = c.get("duration", 0.0)
        # A central duration D and half-width W give duration D*sqrt(1-(x/W)^2);
        # invert to turn our duration at the limit into an offset in km.
        half_w, full = 129.0, 383.0
        inside_km = half_w * (1.0 - max(0.0, 1.0 - (d / full) ** 2) ** 0.5)
        check(f"4. published limit point is on our edge: {label}",
              inside_km < 6.0,
              f"our totality there {d:.1f} s = {inside_km:.1f} km inside our limit")

    # Cross-track check: the width of the band we actually ship, against the
    # published path width at the same instants.
    print()
    path = json.load(open(os.path.join(HERE, "data", "eclipse2027.json")))["path"]
    idx = {p[2]: i for i, p in enumerate(path["center"])}
    dw = []
    for t_pub, w_pub in WIDTHS:
        i = idx.get(t_pub + ":00")
        if i is None:
            check(f"6. path width at {t_pub}", False, "no centre-line sample")
            continue
        w = haversine_km(*path["north"][i], *path["south"][i])
        dw.append(w - w_pub)
        print(f"  path width {t_pub}  published {w_pub:3d} km   ours {w:6.1f} km"
              f"   {w - w_pub:+5.1f} km")
    check("6. path width within 4 km of published at every sampled time",
          all(abs(x) <= 4.0 for x in dw),
          f"range {min(dw):+.1f} .. {max(dw):+.1f} km")

    print()
    for name, lat, lon in OUTSIDE:
        c = local_circumstances(sky, lat, lon)
        check(f"5. no totality outside the path: {name}",
              "duration" not in c,
              f"magnitude {c.get('max_magnitude', 0):.3f}, partial only"
              if "duration" not in c else f"{c['duration']:.1f} s computed")

    bad = results.count(False)
    print(f"\n{len(results) - bad}/{len(results)} oracle checks passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
