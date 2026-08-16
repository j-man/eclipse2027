#!/usr/bin/env python3
"""
Compute a total solar eclipse from first principles.

No pre-made eclipse paths are downloaded: the only external input is the JPL
DE440s ephemeris, which skyfield fetches on first run.

Criterion for a point being inside the umbra at time t, as seen by an observer
standing there:

    separation(Sun, Moon) + angular_radius(Sun) < angular_radius(Moon)

with angular_radius = asin(R / distance), R_sun = 696000 km, R_moon = 1737.4 km,
plus the requirement that the Sun is above the observer's horizon.

Speed comes from vectorisation.  The Sun and Moon apparent positions are
evaluated once per time step for the geocentre; the topocentric vector for a
whole numpy array of observers is then just a subtraction.  Cross-checked
against skyfield's full per-observer observe().apparent() pipeline: agreement
is better than 0.02 arcseconds, i.e. ~5000x finer than the 0.1 deg grid.

Usage:
    python gen_data.py                  the default eclipse (2027-08-02)
    python gen_data.py --all            every eclipse listed in data/index.json
    python gen_data.py --only 2024-04-08

Output:
    data/eclipse2027.json        canonical data file for the default eclipse
    web/eclipse2027.js           same payload as a global, so file:// works
    data/eclipses/YYYY-MM-DD.js  one file per catalogued eclipse, lazy-loaded
"""

import argparse
import json
import math
import os
import subprocess
import time as _time

import numpy as np
from skyfield.api import wgs84

# The umbra criterion, the SkyTable and the per-site circumstances live in
# eclipse_core so that check_oracle.py validates this exact code.
from eclipse_core import (R_EARTH_KM, R_MOON_KM, R_SUN_KM, SkyTable, classify,
                          geodetic, local_circumstances, sun_moon_geocentric,
                          ts, umbra_margin)
from skyfield.framelib import itrs
# The page's default eclipse is defined once, next to the catalogue it ships in.
from find_eclipses import DEFAULT_ECLIPSE, write_index_js

# ---------------------------------------------------------------- constants

# PLAN.md's eclipse: it alone keeps data/eclipse2027.json and the site markers.
PLAN_DATE = "2027-08-02"

COARSE_STEP_S = 300.0        # phase 1: whole day, global 1 deg grid
FINE_STEP_S = 60.0           # phase 2: umbra outline / centre line cadence

N_AZIMUTH = 60               # vertices per umbra outline
DUR_LEVELS_S = [60, 120, 240, 360]   # 1m / 2m / 4m / 6m duration contours
LOCAL_STEP_S = 60.0          # phase 4: sun/moon cadence for local circumstances
LOCAL_PAD_S = 9000.0         # ...2.5 h either side of the umbra's transit

DUR_WIN_S = 420.0            # totality never exceeds ~7.5 minutes
DUR_STEP_S = 5.0
N_OFFSET = 121               # cross-track samples per centre-line point

# How far either side of the centre line the cross-track profile is sampled.
# `reach` blows up at the ends of the track, where the umbra degenerates into a
# smear along the terminator, and an unbounded span costs twice: the sampled
# line grows long enough to cut the path of totality somewhere else entirely,
# and N_OFFSET samples spread over it get too coarse to place a limit at all
# (at span 5000 km the spacing is 83 km, on a path half a degree wide).
# Observed half-widths over the catalogue run 30-600 km, so this is generous.
MAX_HALF_WIDTH_KM = 1200.0

# Validation thresholds for the finished geometry (see validate_geometry).
# Latitude is the discriminator because it is physically bounded: over the 56
# datasets that generate cleanly the largest step between consecutive points in
# any polyline is 9.1 deg, while the three that were broken hit 15.2, 45.5 and
# 106.6. Longitude is deliberately not thresholded on its own — a polar track
# legitimately sweeps tens of degrees of longitude per frame. The distance cap
# is a coarse backstop for gross breakage (clean maximum is 2140 km).
MAX_STEP_LAT_DEG = 12.0
MAX_STEP_KM = 4000.0

# How far either side of the total section to look for annular stretches, and
# how finely. A hybrid's annular ends are minutes long where its total section
# is hours, so the sampling has to be finer than the frame cadence to catch
# them at all; the padding is generous because the ends are what we are after.
ANNULAR_PAD_S = 5400.0
ANNULAR_STEP_S = 20.0

HERE = os.path.dirname(os.path.abspath(__file__))

# name, lat, lon, IANA time zone.
#
# The zone name is all that is stored: the page asks the browser's own tz
# database what offset that zone is on at the eclipse's instant, which gets
# summer time right without anything here having to know about it. Storing a
# number instead would be a second place for the rules to go stale — Egypt
# reinstated summer time in 2023, and Kazakhstan merged its two zones in 2024.
# These sites are specific to the 2027 eclipse and are attached to it alone.
MARKERS_2027 = [
    ("Sevilla", 37.3891, -5.9845, "Europe/Madrid"),
    ("Malaga", 36.7213, -4.4214, "Europe/Madrid"),
    ("Cadiz", 36.5271, -6.2886, "Europe/Madrid"),
    ("Gibraltar", 36.1408, -5.3536, "Europe/Gibraltar"),
    ("Tarifa", 36.0143, -5.6044, "Europe/Madrid"),
    ("Ceuta", 35.8894, -5.3213, "Africa/Ceuta"),
    ("Sfax", 34.7406, 10.7603, "Africa/Tunis"),
    ("Luxor", 25.6872, 32.6396, "Africa/Cairo"),
    ("Wadi Lahmy Azur Resort", 24.2369, 35.4118, "Africa/Cairo"),
]

t_start_wall = _time.time()


def stamp(msg):
    print(f"[{_time.time() - t_start_wall:6.1f}s] {msg}", flush=True)


def r(x, n=3):
    return round(float(x), n)


def hhmmss(sec):
    sec = int(round(sec)) % 86400
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def git_short_hash():
    """Short commit hash, when this directory happens to be a git checkout.

    Purely informational for the version badge; the page just omits the hash
    when there is no repository.
    """
    try:
        p = subprocess.run(["git", "-C", HERE, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else None
    except (OSError, subprocess.SubprocessError):
        return None


# ---------------------------------------------------------------- geometry

def destination(lat0, lon0, bearing_deg, dist_km):
    """Great-circle destination point(s). Everything may be a numpy array."""
    d = np.asarray(dist_km, dtype=float) / R_EARTH_KM
    th = np.radians(np.asarray(bearing_deg, dtype=float))
    p1 = np.radians(lat0)
    l1 = np.radians(lon0)
    sp = np.sin(p1) * np.cos(d) + np.cos(p1) * np.sin(d) * np.cos(th)
    p2 = np.arcsin(np.clip(sp, -1.0, 1.0))
    l2 = l1 + np.arctan2(np.sin(th) * np.sin(d) * np.cos(p1),
                         np.cos(d) - np.sin(p1) * sp)
    return np.degrees(p2), (np.degrees(l2) + 540.0) % 360.0 - 180.0


def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(lon2 - lon1)
    return (np.degrees(np.arctan2(np.sin(dl) * np.cos(p2),
                                  np.cos(p1) * np.sin(p2)
                                  - np.sin(p1) * np.cos(p2) * np.cos(dl)))
            + 360.0) % 360.0


def near_branch(lon, ref):
    """Shift lon by whole turns so it lands within 180 deg of ref.

    Paths that cross the antimeridian are emitted as continuous longitudes
    (..., 179, 181, ...) rather than being split at the seam.  Leaflet draws
    those straight through into the next world copy, which keeps the band, the
    centre line and every umbra outline in one piece; splitting would leave a
    visible gap exactly where the shadow is most interesting.
    """
    return lon + 360.0 * np.round((np.asarray(ref) - np.asarray(lon)) / 360.0)


# ------------------------------------------------- phase 1: coarse global scan

_c_lat = np.arange(-88.0, 88.001, 1.0)
_c_lon = np.arange(-180.0, 180.0, 1.0)
_CLA, _CLO = np.meshgrid(_c_lat, _c_lon, indexing="ij")
COARSE_LAT, COARSE_LON = _CLA.ravel(), _CLO.ravel()
COARSE_GRID = wgs84.latlon(COARSE_LAT, COARSE_LON)


def coarse_scan(t_midnight):
    """Sweep the whole day on a 1 degree grid; return the umbra's rough track."""
    n = int(86400 / COARSE_STEP_S) + 1
    times = ts.tt_jd(t_midnight.tt + np.arange(n) * COARSE_STEP_S / 86400.0)
    sg, mg = sun_moon_geocentric(times)

    hits = []   # (seconds since midnight, lat, lon, margin)
    for i in range(n):
        op = COARSE_GRID.at(times[i]).position.km
        sv = sg[:, i, None] - op
        mv = mg[:, i, None] - op
        sd = np.linalg.norm(sv, axis=0)
        md = np.linalg.norm(mv, axis=0)
        sep = np.arccos(np.clip((sv * mv).sum(axis=0) / (sd * md), -1.0, 1.0))
        margin = np.arcsin(R_MOON_KM / md) - np.arcsin(R_SUN_KM / sd) - sep
        margin = np.where((op * sv).sum(axis=0) > 0, margin, -9.9)
        j = int(np.argmax(margin))
        if margin[j] > 0:
            hits.append((i * COARSE_STEP_S, COARSE_LAT[j], COARSE_LON[j],
                         float(margin[j])))
    return hits


def axis_scan(t_midnight, sec_hint, half_s=5400.0, step_s=10.0):
    """Track the umbra along the shadow axis instead of over a grid.

    The global sweep above walks a 1 degree grid every 300 s, which is blind to
    a barely-total hybrid whose umbra is a few km across and on the surface for
    under a minute.  Following the axis finds those exactly, and gives back the
    same (sec, lat, lon, margin) tuples the rest of the pipeline expects.
    """
    sec = np.arange(sec_hint - half_s, sec_hint + half_s + 1e-9, step_s)
    t = ts.tt_jd(t_midnight.tt + sec / 86400.0)
    S, M = sun_moon_geocentric(t)
    P, total, _annular, _ad = classify(S, M)
    on = np.where(total)[0]
    if not on.size:
        return []
    lat, lon = geodetic(P[:, on], t[on])
    lat, lon = np.atleast_1d(lat), np.atleast_1d(lon)
    # margin is only used to pick the seed frame, so the depth proxy can be
    # crude: the axis point nearest the middle of the window is the deepest.
    mid = 0.5 * (on[0] + on[-1])
    depth = 1.0 / (1.0 + np.abs(on - mid))
    return [(float(sec[k]), float(a), float(b), float(w))
            for k, a, b, w in zip(on, lat, lon, depth)]


# --------------------------------------- phase 2: centre line + umbra outlines

def refine_centre(t, sg, mg, guess_lat, guess_lon, half0=12.0):
    """Locate the deepest point of the shadow by successively finer local grids.

    `half0` bounds the first, coarsest sweep.  Keeping it tight matters near the
    ends of the path: there the shadow axis has not yet reached the Earth, the
    umbra is a long smear along the terminator and its margin maximum is so flat
    that a wide sweep happily jumps hundreds of kilometres between time steps.
    """
    lat0, lon0 = guess_lat, guess_lon
    best = -9.9
    for half, step in ((half0, half0 / 30.0), (1.2, 0.04), (0.06, 0.002)):
        # A degree of longitude shrinks with latitude; widen the box to keep the
        # search square in kilometres, and clamp so we never wrap past the poles.
        scale = min(1.0 / max(np.cos(np.radians(lat0)), 0.05), 20.0)
        la = np.clip(np.arange(-half, half + 1e-9, step) + lat0, -89.9, 89.9)
        lo = np.arange(-half * scale, half * scale + 1e-9, step * scale) + lon0
        A, O = np.meshgrid(la, lo, indexing="ij")
        m = umbra_margin(A.ravel(), O.ravel(), t, sg[:, None], mg[:, None])
        k = int(np.argmax(m))
        best = float(m[k])
        lat0, lon0 = float(A.ravel()[k]), float(O.ravel()[k])
    return lat0, (lon0 + 540.0) % 360.0 - 180.0, best


def umbra_outline(t, sg, mg, lat0, lon0):
    """Trace the umbra edge outward from its centre along N_AZIMUTH bearings."""
    az = np.arange(N_AZIMUTH) * (360.0 / N_AZIMUTH)
    reach = 400.0
    run, radii = None, None
    for _ in range(8):
        radii = np.linspace(0.0, reach, 220)
        AZ, RR = np.meshgrid(az, radii, indexing="ij")
        la, lo = destination(lat0, lon0, AZ.ravel(), RR.ravel())
        inside = (umbra_margin(la, lo, t, sg[:, None], mg[:, None]) > 0.0)
        inside = inside.reshape(N_AZIMUTH, -1)
        # keep only the run of "inside" samples that is connected to the centre
        run = np.cumprod(inside, axis=1).sum(axis=1)
        if run.max() < inside.shape[1]:
            break
        reach *= 2.0
    edge_km = np.where(run > 0, radii[np.maximum(run - 1, 0)], 0.0)
    # half a sample step past the last inside point is the best edge estimate
    edge_km = edge_km + np.where(run > 0, (reach / 219.0) * 0.5, 0.0)
    ola, olo = destination(lat0, lon0, az, edge_km)
    return ola, olo, float(edge_km.max())


def make_frame(t_midnight, sec, guess_lat, guess_lon, half0):
    t = ts.tt_jd(t_midnight.tt + sec / 86400.0)
    sg, mg = sun_moon_geocentric(t)
    lat, lon, margin = refine_centre(t, sg, mg, guess_lat, guess_lon, half0)
    if margin <= 0:
        return None
    ola, olo, reach = umbra_outline(t, sg, mg, lat, lon)
    return {"s": float(sec), "lat": lat, "lon": lon,
            "outline_lat": ola, "outline_lon": olo, "reach": reach}


def track(t_midnight, fine_s, indices, seed):
    """Follow the umbra centre step by step, seeded from a known good frame.

    Each step is predicted by extrapolating the previous two centres, and the
    search box is sized from how far the centre last moved.  Near the ends of
    the path that is several degrees per minute, so the box has to grow with the
    speed rather than being fixed.
    """
    out = []
    prev, prev2 = seed, None
    for i in indices:
        if prev2 is None:
            g_lat, g_lon, half = prev[0], prev[1], 3.0
        else:
            dlat = prev[0] - prev2[0]
            dlon = (prev[1] - prev2[1] + 540.0) % 360.0 - 180.0
            g_lat = prev[0] + dlat
            g_lon = prev[1] + dlon
            step = np.hypot(dlat, dlon * np.cos(np.radians(prev[0])))
            half = float(np.clip(1.3 * step, 2.0, 25.0))
        fr = make_frame(t_midnight, fine_s[i], g_lat, g_lon, half)
        if fr is None:
            break
        out.append(fr)
        prev2, prev = prev, (fr["lat"], fr["lon"])
    return out


def forward_only(fs):
    """Drop leading frames whose step reverses: at the first and last instants
    the umbra only grazes the limb and its centre is not yet well defined."""
    keep = list(fs)
    while len(keep) > 2:
        d0 = bearing(keep[0]["lat"], keep[0]["lon"], keep[1]["lat"], keep[1]["lon"])
        d1 = bearing(keep[1]["lat"], keep[1]["lon"], keep[2]["lat"], keep[2]["lon"])
        if abs((d0 - d1 + 180.0) % 360.0 - 180.0) < 60.0:
            break
        keep.pop(0)
    return keep


# ------------------------------- phase 3: durations, path limits, duration lines

def durations_for(sky, points_lat, points_lon, centre_sec):
    """Totality duration in seconds for each point, sampled around centre_sec."""
    i0, i1 = sky.window(centre_sec, DUR_WIN_S)
    m, _, _, _ = sky.margin(points_lat, points_lon, i0, i1)
    step = sky.sec[1] - sky.sec[0]
    nt = i1 - i0
    npt = m.shape[0]
    inside = m > 0
    has = inside.any(axis=1)
    first = np.where(has, np.argmax(inside, axis=1), 0)
    last = np.where(has, nt - 1 - np.argmax(inside[:, ::-1], axis=1), 0)
    # sub-step refinement of the two zero crossings of the margin
    rr = np.arange(npt)
    a0, a1 = m[rr, np.maximum(first - 1, 0)], m[rr, first]
    b1, b0 = m[rr, last], m[rr, np.minimum(last + 1, nt - 1)]
    lead = np.where((first > 0) & (a1 > a0), a1 / np.where(a1 > a0, a1 - a0, 1.0), 0.0)
    trail = np.where((last < nt - 1) & (b1 > b0), b1 / np.where(b1 > b0, b1 - b0, 1.0), 0.0)
    dur = inside.sum(axis=1) * step - step + (lead + trail) * step
    return np.where(has, np.maximum(dur, 0.0), 0.0)


def cross(level, offs, dur):
    """Offset where the duration profile crosses `level`, on each side of 0.

    Duration behaves like sqrt(distance) near a limit, so duration squared is
    close to linear there and that is what gets interpolated.

    The sample just outside the path is a special case: its duration is a hard
    zero, which says only "somewhere before here", not where.  Interpolating
    towards it places the limit almost on top of it and inflates the path by up
    to one sample spacing.  When the outer neighbour is that hard zero, the edge
    is extrapolated from the last two samples still inside instead, where the
    sqrt law actually holds.

    The walk starts from the umbra sitting under *this* frame — the local
    maximum reached by climbing from offset 0 — rather than from the tallest
    point anywhere on the sampled line.  Near the ends of the track the centre
    is only grazing, its own totality lasts a second or two, and the cross-track
    line is long enough to cut the deep part of the path elsewhere.  Anchoring
    on the global maximum then walks outward from that unrelated patch and
    returns a "limit" thousands of kilometres off the path: that is what put a
    north-limit point at lat 37 on the 2033-03-30 track, which runs 58-86 N.
    """
    out = [None, None]
    i0 = int(np.argmin(np.abs(offs)))
    while True:
        if i0 + 1 < dur.size and dur[i0 + 1] > dur[i0]:
            i0 += 1
        elif i0 > 0 and dur[i0 - 1] > dur[i0]:
            i0 -= 1
        else:
            break
    if dur[i0] <= level:
        return out
    for side in (1, 0):
        step = 1 if side else -1
        rng = range(i0, offs.size - 1) if side else range(i0, 0, -1)
        for i in rng:
            j = i + step
            if not (dur[j] <= level < dur[i]):
                continue
            d1, d2 = dur[i] ** 2, dur[j] ** 2
            k = i - step                       # one sample further inside
            if dur[j] <= 0.0 and 0 <= k < offs.size and dur[k] > dur[i]:
                slope = (dur[k] ** 2 - d1) / (offs[k] - offs[i])
                out[side] = (offs[i] + (level ** 2 - d1) / slope if slope
                             else offs[i])
            elif d1 != d2:
                out[side] = offs[i] + (d1 - level ** 2) / (d1 - d2) * (offs[j] - offs[i])
            else:
                out[side] = offs[i]
            # The crossing is bracketed by construction: dur[i] is above the
            # level and dur[j] is at or below it, so the edge lies between the
            # two samples.  The extrapolation above can leave that bracket by a
            # long way when the profile flattens out near the edge — a nearly
            # zero slope sends it to infinity — and an unclamped result is a
            # limit point placed thousands of kilometres off the path.  On the
            # 2033-03-30 track it returned 5446 km from a window sampled only
            # to 1200 km, which is the wedge that reached Mongolia.
            lo_, hi_ = (offs[i], offs[j]) if offs[j] >= offs[i] else (offs[j], offs[i])
            out[side] = float(min(max(out[side], lo_), hi_))
            break
    return out


def annular_runs(t_midnight, sec_from, sec_to, step_s, ref_lon):
    """Central-line stretches where the eclipse is annular rather than total.

    A hybrid's shadow cone reaches the ground over the middle of its path and
    falls short of it at either end; where it falls short the antumbra touches
    instead and the eclipse is annular. Those stretches belong to the same
    central line as the total section — the shadow does not stop and restart —
    but nothing else here can see them, because the whole umbra pipeline is
    built on a positive umbra margin, which is exactly what an annular eclipse
    does not have.

    Returned as a list of runs, each a list of (sec, lat, lon), so a track that
    is annular at both ends comes back as two pieces rather than one line with
    a jump through the total section in the middle.
    """
    sec = np.arange(sec_from, sec_to + 1e-9, step_s)
    if sec.size < 2:
        return []
    t = ts.tt_jd(t_midnight.tt + sec / 86400.0)
    S, M = sun_moon_geocentric(t)
    P, total, annular, _ad = classify(S, M)
    on = np.where(annular & ~total)[0]
    if not on.size:
        return []
    lat, lon = geodetic(P[:, on], t[on])
    lat, lon = np.atleast_1d(lat), np.atleast_1d(lon)

    runs, cur, prev = [], [], None
    for k, i in enumerate(on):
        if prev is not None and i - prev > 1:      # a gap: the total section
            if len(cur) > 1:
                runs.append(cur)
            cur = []
        cur.append((float(sec[i]), float(lat[k]), float(lon[k])))
        prev = i
    if len(cur) > 1:
        runs.append(cur)

    # Same continuous-longitude treatment the rest of the path gets, so an
    # annular end that crosses the antimeridian stays in one piece.
    out = []
    for run in runs:
        lons = np.degrees(np.unwrap(np.radians([p[2] for p in run])))
        lons = lons + 360.0 * np.round((ref_lon - lons[0]) / 360.0)
        out.append([(p[0], p[1], float(lo)) for p, lo in zip(run, lons)])
    return out


def dist_to_path_km(limit_n, limit_s, lat, lon):
    """Great-circle distance to the nearer edge of the path of totality.

    Measured to the limit polylines as segments, not just their vertices, so a
    site sitting between two 60 s samples is not reported tens of km too far out.
    """
    kx = np.cos(np.radians(lat))
    best = np.inf
    for line in (limit_n, limit_s):
        a = np.array(line)
        if a.shape[0] < 2:
            continue
        wrap = lambda d: (d + 540.0) % 360.0 - 180.0        # noqa: E731
        ay, ax = a[:-1, 0] - lat, wrap(a[:-1, 1] - lon) * kx
        by, bx = a[1:, 0] - lat, wrap(a[1:, 1] - lon) * kx
        vy, vx = by - ay, bx - ax
        len2 = vx * vx + vy * vy
        u = np.clip(np.where(len2 > 0, -(ax * vx + ay * vy) / np.where(len2 > 0, len2, 1),
                             0.0), 0.0, 1.0)
        dy, dx = ay + u * vy, ax + u * vx
        best = min(best, float(np.hypot(dy, dx).min()))
    return best * 111.195


# ------------------------------------------------------------------ pipeline

def generate(date, markers=(), verbose=True, coarse_hits=None, seed_utc=None):
    """Full pipeline for one eclipse date ("YYYY-MM-DD"). None if no umbra.

    `seed_utc` is "HH:MM:SS" of greatest eclipse when it is already known; it
    lets the axis scan take over for umbrae the global grid cannot see.
    """
    y, mo, d = (int(x) for x in date.split("-"))
    t_midnight = ts.utc(y, mo, d, 0, 0, 0)
    say = stamp if verbose else (lambda _m: None)

    if coarse_hits is None:
        say("  phase 1: coarse global scan")
        coarse_hits = coarse_scan(t_midnight)
        if not coarse_hits and seed_utc:
            h, m, s = (int(v) for v in seed_utc.split(":"))
            say("  phase 1: grid found nothing, following the shadow axis")
            coarse_hits = axis_scan(t_midnight, h * 3600 + m * 60 + s)
    if not coarse_hits:
        return None

    # A small umbra can clip the 1 deg / 300 s grid once and never again, which
    # leaves a "central path" one instant long. The fine window is sized from
    # that span, so it collapses to a few seconds and the track stops before it
    # has started — 2050-05-20 came out as 9 frames over 8 s of a path that
    # really runs an hour and a half. A span no longer than one grid step means
    # the grid has not resolved the path, so follow the axis instead, which
    # samples it directly rather than hoping it lands on a grid point.
    if coarse_hits[-1][0] - coarse_hits[0][0] <= COARSE_STEP_S:
        deepest = max(coarse_hits, key=lambda h: h[3])
        axis_hits = axis_scan(t_midnight, deepest[0])
        if len(axis_hits) > len(coarse_hits):
            say(f"  phase 1: grid caught {len(coarse_hits)} instant(s), "
                f"axis scan resolves {len(axis_hits)}")
            coarse_hits = axis_hits

    coarse_s = np.array([h[0] for h in coarse_hits])
    coarse_clat = np.array([h[1] for h in coarse_hits])
    coarse_clon = np.degrees(np.unwrap(np.radians([h[2] for h in coarse_hits])))

    # Enough frames to animate however brief the total phase is: a hybrid that
    # is total for half a minute needs seconds per frame, not a whole minute.
    span = float(coarse_s[-1] - coarse_s[0])
    step = FINE_STEP_S
    while step > 1.0 and span / step < 24.0:
        step /= 2.0
    pad = max(COARSE_STEP_S if span > 600 else step * 4, step)

    say(f"  phase 2: centre line and umbra outlines ({step:.0f} s steps)")
    fine_s = np.arange(coarse_s[0] - pad, coarse_s[-1] + pad + 1e-9, step)

    # Seed at the deepest coarse hit, where the shadow axis is well inside the
    # Earth and the margin maximum is sharp, then walk outwards both ways.
    seed_hit = max(coarse_hits, key=lambda h: h[3])
    i_seed = int(np.argmin(np.abs(fine_s - seed_hit[0])))
    seed_frame = make_frame(t_midnight, fine_s[i_seed], seed_hit[1], seed_hit[2], 12.0)
    if seed_frame is None:
        return None
    seed = (seed_frame["lat"], seed_frame["lon"])

    back = track(t_midnight, fine_s, range(i_seed - 1, -1, -1), seed)
    fwd = track(t_midnight, fine_s, range(i_seed + 1, fine_s.size), seed)
    frames = back[::-1] + [seed_frame] + fwd
    frames = forward_only(forward_only(frames)[::-1])[::-1]
    if len(frames) < 3:
        return None

    clat = np.array([f["lat"] for f in frames])
    csec = np.array([f["s"] for f in frames])
    # Continuous longitudes, so a path over the antimeridian stays in one piece.
    clon = np.degrees(np.unwrap(np.radians([f["lon"] for f in frames])))

    brg = np.empty(len(frames))
    for i in range(len(frames)):
        a = max(i - 1, 0)
        b = min(i + 1, len(frames) - 1)
        brg[i] = bearing(clat[a], clon[a], clat[b], clon[b])

    say("  phase 3: durations, path limits and duration contours")
    sky = SkyTable(t_midnight,
                   np.arange(frames[0]["s"] - DUR_WIN_S - 60.0,
                             frames[-1]["s"] + DUR_WIN_S + 60.0 + 1e-9, DUR_STEP_S))

    centre_dur = np.zeros(len(frames))
    limit_n, limit_s = [], []
    contours = {lv: ([], []) for lv in DUR_LEVELS_S}

    for i, fr in enumerate(frames):
        span = min(max(fr["reach"] * 1.6, 60.0), MAX_HALF_WIDTH_KM)
        offs = np.linspace(-span, span, N_OFFSET)
        # positive offset = to the left of travel = north side of the path
        pla, plo = destination(clat[i], clon[i], brg[i] - 90.0, offs)
        dur = durations_for(sky, pla, plo, fr["s"])
        centre_dur[i] = float(np.interp(0.0, offs, dur))

        zs, zn = cross(0.5, offs, dur)
        for bucket, off in ((limit_s, zs), (limit_n, zn)):
            if off is not None:
                la, lo = destination(clat[i], clon[i], brg[i] - 90.0, off)
                bucket.append((float(la), float(near_branch(lo, clon[i]))))
        for lv in DUR_LEVELS_S:
            cs, cn = cross(float(lv), offs, dur)
            for k, c in ((0, cs), (1, cn)):
                if c is not None:
                    la, lo = destination(clat[i], clon[i], brg[i] - 90.0, c)
                    contours[lv][k].append((float(la), float(near_branch(lo, clon[i]))))

    imax = int(np.argmax(centre_dur))
    say(f"  max duration {centre_dur[imax]:.0f} s "
        f"({int(centre_dur[imax]) // 60}m{int(centre_dur[imax]) % 60:02d}s) at "
        f"{clat[imax]:.2f}, {clon[imax]:.2f}")

    site_data = []
    if markers:
        marker_sky = SkyTable(t_midnight,
                              np.arange(frames[0]["s"] - 7200.0,
                                        frames[-1]["s"] + 7200.0 + 1e-9, 2.0))
        for name, lat, lon, tzone in markers:
            c = local_circumstances(marker_sky, lat, lon)
            if "duration" not in c:
                c["dist_to_path_km"] = round(dist_to_path_km(limit_n, limit_s,
                                                             lat, lon), 1)
            # Times stay UTC seconds from midnight; `tz` is presentation only.
            c.update(name=name, tz=tzone)
            site_data.append(c)
            if "duration" in c:
                dd = int(round(c["duration"]))
                say(f"  {name:24s} totality {dd // 60}m{dd % 60:02d}s"
                    f"  max {hhmmss(c['max_s'])} UTC")
            else:
                say(f"  {name:24s} OUTSIDE the path: magnitude "
                    f"{c.get('max_magnitude', 0):.3f}, "
                    f"{c['dist_to_path_km']:.0f} km from the nearest limit")

    # --- phase 4: Sun and Moon for local circumstances anywhere -------------
    #
    # 2.5 h either side of the umbra's transit covers the partial phase for
    # every observer who sees any of it: first and last contact worldwide are
    # inside that window for any central eclipse.
    say("  phase 4: sun and moon in the Earth-fixed frame")
    lc_sec = np.arange(frames[0]["s"] - LOCAL_PAD_S,
                       frames[-1]["s"] + LOCAL_PAD_S + LOCAL_STEP_S, LOCAL_STEP_S)
    lc_t = ts.tt_jd(t_midnight.tt + lc_sec / 86400.0)
    lc_sg, lc_mg = sun_moon_geocentric(lc_t)
    lc_rot = itrs.rotation_at(lc_t)                      # (3, 3, n): ITRS -> GCRS
    # ...so contracting over the GCRS index takes a vector the other way.
    lc_sun = np.einsum("jci,ci->ji", lc_rot, lc_sg)
    lc_moon = np.einsum("jci,ci->ji", lc_rot, lc_mg)
    local_block = {
        "t0_s": r(float(lc_sec[0]), 0),
        "step_s": r(LOCAL_STEP_S, 0),
        "sun": [[r(v, 0) for v in lc_sun[:, i]] for i in range(lc_sec.size)],
        "moon": [[r(v, 2) for v in lc_moon[:, i]] for i in range(lc_sec.size)],
        "r_sun_km": R_SUN_KM,
        "r_moon_km": R_MOON_KM,
    }

    payload = {
        "meta": {
            "date": date,
            "step_s": step,
            "t_start_s": r(frames[0]["s"], 0),
            "t_end_s": r(frames[-1]["s"], 0),
            "max_duration_s": r(centre_dur[imax], 1),
            "max_duration_at": [r(clat[imax], 4), r(clon[imax], 4), hhmmss(csec[imax])],
            "source": "computed with skyfield + JPL DE440s",
        },
        "path": {
            "center": [[r(clat[i], 4), r(clon[i], 4), hhmmss(csec[i]), r(centre_dur[i], 1)]
                       for i in range(len(frames))],
            "north": [[r(a, 4), r(b, 4)] for a, b in limit_n],
            "south": [[r(a, 4), r(b, 4)] for a, b in limit_s],
        },
        "contours": {str(lv): {"north": [[r(a, 4), r(b, 4)] for a, b in contours[lv][1]],
                               "south": [[r(a, 4), r(b, 4)] for a, b in contours[lv][0]]}
                     for lv in DUR_LEVELS_S},
        "umbra": [{"t": hhmmss(f["s"]), "s": r(f["s"], 0),
                   "c": [r(clat[i], 4), r(clon[i], 4)],
                   "poly": [[r(a, 3), r(near_branch(b, clon[i]), 3)]
                            for a, b in zip(f["outline_lat"], f["outline_lon"])]}
                  for i, f in enumerate(frames)],
        "markers": site_data,
        # Sun and Moon in the Earth-fixed frame, once a minute across the whole
        # partial phase. The path arrays only cover the umbra's transit, so a
        # click far from it had nothing to work with; from these two vectors a
        # browser can work out local circumstances for any point on Earth with
        # the same geometry eclipse_core uses.
        "local": local_block,
    }
    # Hybrids only: a purely total eclipse has no annular stretch, the key is
    # absent, and its dataset is byte for byte what it was before.
    ann = annular_runs(t_midnight, frames[0]["s"] - ANNULAR_PAD_S,
                       frames[-1]["s"] + ANNULAR_PAD_S,
                       min(step, ANNULAR_STEP_S), clon[0])
    if ann:
        payload["path"]["annular"] = [
            [[r(p[1], 4), r(p[2], 4), hhmmss(p[0])] for p in run] for run in ann
        ]
        say(f"  hybrid: {len(ann)} annular stretch(es), "
            f"{sum(len(x) for x in ann)} points")

    h = git_short_hash()
    if h:
        payload["meta"]["git"] = h
    validate_geometry(payload)
    return payload


# ------------------------------------------------------------- phase 5: checks

class GeometryError(Exception):
    """Generated geometry that must not be written out."""


def _step_km(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    c = (math.sin(p1) * math.sin(p2)
         + math.cos(p1) * math.cos(p2) * math.cos(dl))
    return R_EARTH_KM * math.acos(max(-1.0, min(1.0, c)))


def polylines(payload):
    """Every ordered point sequence in a payload, by name."""
    out = {}
    for side in ("center", "north", "south"):
        out[f"path.{side}"] = payload["path"].get(side) or []
    for i, run in enumerate(payload["path"].get("annular") or []):
        out[f"path.annular[{i}]"] = run
    for lv, c in (payload.get("contours") or {}).items():
        for side in ("north", "south"):
            out[f"contours.{lv}.{side}"] = (c or {}).get(side) or []
    for i, f in enumerate(payload.get("umbra") or []):
        out[f"umbra[{i}].poly"] = f["poly"]
    return out


def validate_geometry(payload):
    """Refuse to write a track that jumps between consecutive points.

    The solver that places the path limits and duration contours can fail near
    the ends of the track, where the umbra degenerates and the cross-track
    profile stops being a clean single hump.  When it does, it does not fail
    loudly — it returns a point somewhere else on Earth, and the map draws a
    line to it.  Three of the 59 catalogued eclipses shipped with exactly that
    defect (a north-limit point at lat 37 on a track confined to 58-86 N, drawn
    as a wedge from the Arctic to Mongolia).

    Checking the finished geometry catches the whole class at generation time,
    whatever the solver does next, so it cannot reach the page again.
    """
    date = payload["meta"]["date"]
    bad = []
    for name, seq in polylines(payload).items():
        for i in range(len(seq) - 1):
            a, b = seq[i], seq[i + 1]
            dlat = abs(b[0] - a[0])
            if dlat > MAX_STEP_LAT_DEG:
                bad.append(f"{name}[{i}]->[{i + 1}]: latitude jumps {dlat:.1f} deg "
                           f"({a[0]:.3f} -> {b[0]:.3f}), limit {MAX_STEP_LAT_DEG:.0f}")
            km = _step_km(a, b)
            if km > MAX_STEP_KM:
                bad.append(f"{name}[{i}]->[{i + 1}]: {km:.0f} km apart "
                           f"({a[0]:.3f},{a[1]:.3f} -> {b[0]:.3f},{b[1]:.3f}), "
                           f"limit {MAX_STEP_KM:.0f}")
    if bad:
        shown = "\n    ".join(bad[:8])
        more = f"\n    ... and {len(bad) - 8} more" if len(bad) > 8 else ""
        raise GeometryError(f"{date}: {len(bad)} implausible step(s) in the "
                            f"generated geometry:\n    {shown}{more}")
    return payload


# --------------------------------------------------------------- entry points

def write_default(payload):
    """The default eclipse keeps its own two files, as the page expects."""
    js = json.dumps(payload, separators=(",", ":"))
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "web"), exist_ok=True)
    with open(os.path.join(HERE, "data", "eclipse2027.json"), "w") as fh:
        fh.write(js)
    with open(os.path.join(HERE, "web", "eclipse2027.js"), "w") as fh:
        fh.write("window.ECLIPSE_DATA=" + js + ";\n")
    return len(js)


def write_bootstrap(payload):
    """The default eclipse, eagerly loaded so the first paint needs no fetch."""
    os.makedirs(os.path.join(HERE, "web"), exist_ok=True)
    js = json.dumps(payload, separators=(",", ":"))
    with open(os.path.join(HERE, "web", "eclipse-default.js"), "w") as fh:
        fh.write("window.ECLIPSE_DATA=" + js + ";\n")


def write_catalogued(payload):
    """One lazy-loaded file per eclipse, handed to the page via a callback."""
    out = os.path.join(HERE, "data", "eclipses")
    os.makedirs(out, exist_ok=True)
    js = json.dumps(payload, separators=(",", ":"))
    with open(os.path.join(out, payload["meta"]["date"] + ".js"), "w") as fh:
        fh.write("window.ECLIPSE_LOAD(" + js + ");\n")
    return len(js)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true",
                    help="generate every eclipse in data/index.json")
    ap.add_argument("--only", metavar="YYYY-MM-DD",
                    help="generate a single catalogued eclipse")
    args = ap.parse_args()

    if not (args.all or args.only):
        # PLAN.md's eclipse, plus the one the page opens with when they differ,
        # so a bare run always leaves a page that works.
        for date in dict.fromkeys([PLAN_DATE, DEFAULT_ECLIPSE]):
            stamp(f"generating {date}")
            payload = generate(date, MARKERS_2027 if date == PLAN_DATE else ())
            if payload is None:
                raise SystemExit("no umbra found on " + date)
            size = write_catalogued(payload)
            if date == PLAN_DATE:
                write_default(payload)
            if date == DEFAULT_ECLIPSE:
                write_bootstrap(payload)
            stamp(f"  wrote data/eclipses/{date}.js ({size / 1024:.0f} kB)")
        return

    index_path = os.path.join(HERE, "data", "index.json")
    if not os.path.exists(index_path):
        raise SystemExit("data/index.json missing - run find_eclipses.py first")
    index = json.load(open(index_path))
    catalog = index["eclipses"]
    if args.only:
        catalog = [e for e in catalog if e["date"] == args.only]
        if not catalog:
            raise SystemExit(args.only + " is not in the catalog")

    total, failed = 0, []
    for n, e in enumerate(catalog, 1):
        date = e["date"]
        stamp(f"[{n}/{len(catalog)}] {date} ({e['type']})")
        try:
            payload = generate(date,
                               MARKERS_2027 if date == PLAN_DATE else (),
                               verbose=False, seed_utc=e.get("greatest_utc"))
        except Exception as exc:                      # keep the batch going
            failed.append((date, repr(exc)))
            stamp(f"    FAILED: {exc!r}")
            continue
        if payload is None:
            failed.append((date, "no umbra on the surface"))
            stamp("    FAILED: no umbra on the surface")
            continue
        size = write_catalogued(payload)
        total += size
        if date == PLAN_DATE:
            write_default(payload)
        if date == DEFAULT_ECLIPSE:
            write_bootstrap(payload)
        # The discovery pass only estimated the duration at the greatest-eclipse
        # point; replace it with the pipeline's own maximum over the centre line.
        m = payload["meta"]
        e["max_duration_s"] = m["max_duration_s"]
        e["greatest_lat"], e["greatest_lon"] = m["max_duration_at"][:2]
        e["frames"] = len(payload["umbra"])
        stamp(f"    {m['max_duration_s']:.0f} s max, "
              f"{len(payload['umbra'])} frames, {size / 1024:.0f} kB")

    if not args.only:
        # Anything that failed to generate has no data file, so it must not stay
        # in the catalogue the page builds its dropdown from.
        index["eclipses"] = [e for e in index["eclipses"]
                             if e["date"] not in {d for d, _ in failed}]
        index["count"] = len(index["eclipses"])
        index["total_bytes"] = total
    index["default"] = DEFAULT_ECLIPSE
    with open(index_path, "w") as fh:
        json.dump(index, fh, indent=1)
    write_index_js(index)

    stamp(f"done: {len(catalog) - len(failed)}/{len(catalog)} generated, "
          f"{total / 1048576:.1f} MB total")
    for date, why in failed:
        stamp(f"  FAILED {date}: {why}")


if __name__ == "__main__":
    main()
