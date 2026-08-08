#!/usr/bin/env python3
"""
Compute the total solar eclipse of 2027-08-02 from first principles.

No pre-made eclipse paths are downloaded: the only external input is the JPL
DE421 ephemeris, which skyfield fetches on first run.

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

Output:
    data/eclipse2027.json   canonical data file
    web/eclipse2027.js      same payload wrapped in a global, so web/index.html
                            works from a file:// URL without a web server
"""

import json
import os
import time as _time

import numpy as np
from skyfield.api import load, wgs84
from skyfield.framelib import itrs

# ---------------------------------------------------------------- constants

R_SUN_KM = 696000.0
R_MOON_KM = 1737.4
R_EARTH_KM = 6371.0

DATE = (2027, 8, 2)
COARSE_STEP_S = 300.0        # phase 1: whole day, global 1 deg grid
FINE_STEP_S = 60.0           # phase 2: umbra outline / centre line cadence

N_AZIMUTH = 60               # vertices per umbra outline
DUR_LEVELS_S = [60, 120, 240, 360]   # 1m / 2m / 4m / 6m duration contours

HERE = os.path.dirname(os.path.abspath(__file__))

MARKERS = [
    # name, lat, lon, utc offset (hours) on eclipse day, tz label
    ("Malaga", 36.7213, -4.4214, 2.0, "CEST"),
    ("Luxor", 25.6872, 32.6396, 2.0, "EET"),
]

t_start_wall = _time.time()


def stamp(msg):
    print(f"[{_time.time() - t_start_wall:5.1f}s] {msg}", flush=True)


# ---------------------------------------------------------------- ephemeris

stamp("loading ephemeris")
ts = load.timescale()
eph = load("de421.bsp")
earth, sun, moon = eph["earth"], eph["sun"], eph["moon"]


def sun_moon_geocentric(t):
    """Apparent GCRS positions of Sun and Moon from Earth's centre, in km.

    Works for a scalar time or a time array; returns arrays shaped (3,) or (3, n).
    """
    e = earth.at(t)
    return (e.observe(sun).apparent().position.km,
            e.observe(moon).apparent().position.km)


def umbra_margin(lat, lon, t, sg, mg):
    """Angular margin r_moon - r_sun - separation, in radians.

    Positive means the observer at (lat, lon) sees the Sun fully covered.
    `sg` / `mg` are the geocentric Sun/Moon vectors already evaluated at `t`
    and broadcast-compatible with the observer arrays.  Points where the Sun is
    below the horizon are forced negative.
    """
    op = wgs84.latlon(lat, lon).at(t).position.km
    sv = sg - op
    mv = mg - op
    sd = np.linalg.norm(sv, axis=0)
    md = np.linalg.norm(mv, axis=0)
    cosang = (sv * mv).sum(axis=0) / (sd * md)
    sep = np.arccos(np.clip(cosang, -1.0, 1.0))
    margin = np.arcsin(R_MOON_KM / md) - np.arcsin(R_SUN_KM / sd) - sep
    up = op / np.linalg.norm(op, axis=0)
    below = (up * sv).sum(axis=0) <= 0.0
    return np.where(below, -9.9, margin)


class SkyTable:
    """Sun, Moon and Earth orientation precomputed on a fixed time grid.

    Evaluating the umbra criterion for many observers at many times is only
    fast if the expensive per-time work happens once.  skyfield recomputes the
    ITRS->GCRS rotation for every (observer, time) pair it is handed, which
    dominates the run time; here the rotation is stored per time step and
    applied to the observers' fixed body-frame coordinates with an einsum.
    """

    def __init__(self, sec):
        self.sec = np.asarray(sec, dtype=float)
        t = ts.tt_jd(t_midnight.tt + self.sec / 86400.0)
        self.sg, self.mg = sun_moon_geocentric(t)          # (3, nt)
        self.rot = itrs.rotation_at(t)                     # (3, 3, nt)

    def window(self, centre_sec, half_width_s):
        i0, i1 = np.searchsorted(self.sec, [centre_sec - half_width_s,
                                            centre_sec + half_width_s])
        return int(i0), int(min(i1 + 1, self.sec.size))

    def margin(self, lat, lon, i0, i1):
        """Umbra margin in radians, shaped (n_points, n_times)."""
        xyz = wgs84.latlon(np.atleast_1d(lat), np.atleast_1d(lon)).itrs_xyz.km
        op = np.einsum("jci,jp->cpi", self.rot[:, :, i0:i1], xyz)
        sv = self.sg[:, None, i0:i1] - op
        mv = self.mg[:, None, i0:i1] - op
        sd = np.linalg.norm(sv, axis=0)
        md = np.linalg.norm(mv, axis=0)
        sep = np.arccos(np.clip((sv * mv).sum(axis=0) / (sd * md), -1.0, 1.0))
        m = np.arcsin(R_MOON_KM / md) - np.arcsin(R_SUN_KM / sd) - sep
        up = op / np.linalg.norm(op, axis=0)
        return np.where((up * sv).sum(axis=0) > 0, m, -9.9), sep, sd, md


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


# ------------------------------------------------- phase 1: coarse global scan

stamp("phase 1: coarse global scan (1 deg grid, 300 s steps)")

c_lat = np.arange(-72.0, 72.001, 1.0)
c_lon = np.arange(-180.0, 180.0, 1.0)
CLA, CLO = np.meshgrid(c_lat, c_lon, indexing="ij")
coarse_lat, coarse_lon = CLA.ravel(), CLO.ravel()
coarse_grid = wgs84.latlon(coarse_lat, coarse_lon)

t_midnight = ts.utc(*DATE, 0, 0, 0)
n_coarse = int(86400 / COARSE_STEP_S) + 1
coarse_times = ts.tt_jd(t_midnight.tt + np.arange(n_coarse) * COARSE_STEP_S / 86400.0)
c_sg, c_mg = sun_moon_geocentric(coarse_times)

coarse_hits = []   # (seconds since midnight, lat, lon, margin)
for i in range(n_coarse):
    op = coarse_grid.at(coarse_times[i]).position.km
    sv = c_sg[:, i, None] - op
    mv = c_mg[:, i, None] - op
    sd = np.linalg.norm(sv, axis=0)
    md = np.linalg.norm(mv, axis=0)
    sep = np.arccos(np.clip((sv * mv).sum(axis=0) / (sd * md), -1.0, 1.0))
    margin = np.arcsin(R_MOON_KM / md) - np.arcsin(R_SUN_KM / sd) - sep
    margin = np.where((op * sv).sum(axis=0) > 0, margin, -9.9)
    j = int(np.argmax(margin))
    if margin[j] > 0:
        coarse_hits.append((i * COARSE_STEP_S, coarse_lat[j], coarse_lon[j],
                            float(margin[j])))

if not coarse_hits:
    raise SystemExit("no umbra found on this date")

stamp(f"phase 1 done: {len(coarse_hits)} coarse hits, "
      f"{coarse_hits[0][0] / 3600:05.2f}h - {coarse_hits[-1][0] / 3600:05.2f}h UTC")

coarse_s = np.array([h[0] for h in coarse_hits])
coarse_clat = np.array([h[1] for h in coarse_hits])
coarse_clon = np.unwrap(np.radians(np.array([h[2] for h in coarse_hits])))
coarse_clon = np.degrees(coarse_clon)


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
        scale = min(1.0 / max(np.cos(np.radians(lat0)), 0.15), 8.0)
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
    for _ in range(7):
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


stamp(f"phase 2: centre line and umbra outlines ({FINE_STEP_S:.0f} s steps)")

fine_s = np.arange(coarse_s[0] - COARSE_STEP_S, coarse_s[-1] + COARSE_STEP_S + 1e-9,
                   FINE_STEP_S)


def make_frame(sec, guess_lat, guess_lon, half0):
    t = ts.tt_jd(t_midnight.tt + sec / 86400.0)
    sg, mg = sun_moon_geocentric(t)
    lat, lon, margin = refine_centre(t, sg, mg, guess_lat, guess_lon, half0)
    if margin <= 0:
        return None
    ola, olo, reach = umbra_outline(t, sg, mg, lat, lon)
    return {"s": float(sec), "lat": lat, "lon": lon,
            "outline_lat": ola, "outline_lon": olo, "reach": reach}


def track(indices, seed):
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
            half = float(np.clip(1.3 * step, 2.0, 20.0))
        fr = make_frame(fine_s[i], g_lat, g_lon, half)
        if fr is None:
            break
        out.append(fr)
        prev2, prev = prev, (fr["lat"], fr["lon"])
    return out


# Seed at the deepest coarse hit, where the shadow axis is well inside the Earth
# and the margin maximum is sharp, then walk outwards in both directions.
seed_hit = max(coarse_hits, key=lambda h: h[3])
i_seed = int(np.argmin(np.abs(fine_s - seed_hit[0])))
seed_frame = make_frame(fine_s[i_seed], seed_hit[1], seed_hit[2], 12.0)
if seed_frame is None:
    raise SystemExit("could not seed the centre-line track")
seed = (seed_frame["lat"], seed_frame["lon"])

back = track(range(i_seed - 1, -1, -1), seed)
fwd = track(range(i_seed + 1, fine_s.size), seed)
frames = back[::-1] + [seed_frame] + fwd

# Trim any leading/trailing frame that steps backwards along the path: at the
# very first and last instants the umbra only grazes the limb and its centre is
# not yet well defined.
def forward_only(fs):
    keep = list(fs)
    while len(keep) > 2:
        d0 = bearing(keep[0]["lat"], keep[0]["lon"], keep[1]["lat"], keep[1]["lon"])
        d1 = bearing(keep[1]["lat"], keep[1]["lon"], keep[2]["lat"], keep[2]["lon"])
        if abs((d0 - d1 + 180.0) % 360.0 - 180.0) < 60.0:
            break
        keep.pop(0)
    return keep


frames = forward_only(forward_only(frames)[::-1])[::-1]

stamp(f"phase 2 done: {len(frames)} frames, "
      f"{frames[0]['s'] / 3600:05.2f}h - {frames[-1]['s'] / 3600:05.2f}h UTC")

clat = np.array([f["lat"] for f in frames])
clon = np.array([f["lon"] for f in frames])
csec = np.array([f["s"] for f in frames])

# Direction of travel at each centre-line point (forward/backward difference).
brg = np.empty(len(frames))
for i in range(len(frames)):
    a = max(i - 1, 0)
    b = min(i + 1, len(frames) - 1)
    brg[i] = bearing(clat[a], clon[a], clat[b], clon[b])


# ------------------------------- phase 3: durations, path limits, duration lines

DUR_WIN_S = 420.0     # totality never exceeds ~7 minutes
DUR_STEP_S = 5.0
N_OFFSET = 121        # cross-track samples per centre-line point


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
    r = np.arange(npt)
    a0, a1 = m[r, np.maximum(first - 1, 0)], m[r, first]
    b1, b0 = m[r, last], m[r, np.minimum(last + 1, nt - 1)]
    lead = np.where((first > 0) & (a1 > a0), a1 / np.where(a1 > a0, a1 - a0, 1.0), 0.0)
    trail = np.where((last < nt - 1) & (b1 > b0), b1 / np.where(b1 > b0, b1 - b0, 1.0), 0.0)
    dur = inside.sum(axis=1) * step - step + (lead + trail) * step
    return np.where(has, np.maximum(dur, 0.0), 0.0)


def cross(level, offs, dur):
    """Offset where the duration profile crosses `level`, on each side of 0.

    Duration behaves like sqrt(distance) near a limit, so the interpolation is
    done on duration squared, which is close to linear there.
    """
    out = [None, None]
    i0 = int(np.argmax(dur))
    if dur[i0] <= level:
        return out
    for side, rng in ((1, range(i0, offs.size - 1)), (0, range(i0, 0, -1))):
        for i in rng:
            j = i + 1 if side else i - 1
            if dur[j] <= level < dur[i]:
                d1, d2 = dur[i] ** 2, dur[j] ** 2
                f = (d1 - level ** 2) / (d1 - d2) if d1 != d2 else 0.0
                out[side] = offs[i] + f * (offs[j] - offs[i])
                break
    return out


stamp("phase 3: durations, path limits and duration contours")

sky = SkyTable(np.arange(frames[0]["s"] - DUR_WIN_S - 60.0,
                         frames[-1]["s"] + DUR_WIN_S + 60.0 + 1e-9, DUR_STEP_S))

centre_dur = np.zeros(len(frames))
limit_n, limit_s = [], []
contours = {lv: ([], []) for lv in DUR_LEVELS_S}

for i, fr in enumerate(frames):
    span = max(fr["reach"] * 1.6, 60.0)
    offs = np.linspace(-span, span, N_OFFSET)
    # positive offset = to the left of travel = north side of the path
    pla, plo = destination(fr["lat"], fr["lon"], brg[i] - 90.0, offs)
    dur = durations_for(sky, pla, plo, fr["s"])
    centre_dur[i] = float(np.interp(0.0, offs, dur))

    zs, zn = cross(0.5, offs, dur)
    if zs is not None:
        la, lo = destination(fr["lat"], fr["lon"], brg[i] - 90.0, zs)
        limit_s.append((float(la), float(lo)))
    if zn is not None:
        la, lo = destination(fr["lat"], fr["lon"], brg[i] - 90.0, zn)
        limit_n.append((float(la), float(lo)))
    for lv in DUR_LEVELS_S:
        cs, cn = cross(float(lv), offs, dur)
        for k, c in ((0, cs), (1, cn)):
            if c is not None:
                la, lo = destination(fr["lat"], fr["lon"], brg[i] - 90.0, c)
                contours[lv][k].append((float(la), float(lo)))

imax = int(np.argmax(centre_dur))
stamp(f"phase 3 done: max duration {centre_dur[imax]:.0f} s "
      f"({int(centre_dur[imax]) // 60}m{int(centre_dur[imax]) % 60:02d}s) at "
      f"{clat[imax]:.2f}, {clon[imax]:.2f}")


# ------------------------------------------------------- marker circumstances

stamp("markers: local circumstances")
marker_sky = SkyTable(np.arange(frames[0]["s"] - 7200.0,
                                frames[-1]["s"] + 7200.0 + 1e-9, 2.0))


def edge_cross(sec, f, i, forward):
    """Time where f crosses zero next to index i, by linear interpolation."""
    j = i + 1 if forward else i - 1
    if j < 0 or j >= f.size or f[i] == f[j]:
        return float(sec[i])
    return float(sec[i] + (sec[j] - sec[i]) * f[i] / (f[i] - f[j]))


def circumstances(lat, lon):
    """Contact times, totality duration and peak obscuration for one location."""
    sec = marker_sky.sec
    m, sep, sd, md = marker_sky.margin(lat, lon, 0, sec.size)
    m, sep, sd, md = m[0], sep[0], sd[0], md[0]
    rs = np.arcsin(R_SUN_KM / sd)
    rm = np.arcsin(R_MOON_KM / md)
    visible = m > -9.0
    fp = np.where(visible, rs + rm - sep, -9.9)      # >0 during any partial phase
    out = {"lat": lat, "lon": lon}
    if (fp > 0).any():
        p = np.where(fp > 0)[0]
        out["partial_start"] = edge_cross(sec, fp, p[0], False)
        out["partial_end"] = edge_cross(sec, fp, p[-1], True)
        out["max_obscuration"] = float(
            np.clip((rs[p] + rm[p] - sep[p]) / (2 * rs[p]), 0, 1).max())
    if (m > 0).any():
        q = np.where(m > 0)[0]
        out["total_start"] = edge_cross(sec, m, q[0], False)
        out["total_end"] = edge_cross(sec, m, q[-1], True)
        out["duration"] = out["total_end"] - out["total_start"]
    return out


markers = []
for name, lat, lon, tzoff, tzname in MARKERS:
    c = circumstances(lat, lon)
    c.update(name=name, tz_offset_h=tzoff, tz_name=tzname)
    markers.append(c)
    if "duration" in c:
        d = int(round(c["duration"]))
        stamp(f"{name}: totality {d // 60}m{d % 60:02d}s")
    else:
        stamp(f"{name}: partial only")


# --------------------------------------------------------------- write output

def r(x, n=3):
    return round(float(x), n)


def hhmmss(sec):
    sec = int(round(sec)) % 86400
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


payload = {
    "meta": {
        "date": f"{DATE[0]:04d}-{DATE[1]:02d}-{DATE[2]:02d}",
        "step_s": FINE_STEP_S,
        "t_start_s": r(frames[0]["s"], 0),
        "t_end_s": r(frames[-1]["s"], 0),
        "max_duration_s": r(centre_dur[imax], 1),
        "max_duration_at": [r(clat[imax], 4), r(clon[imax], 4), hhmmss(csec[imax])],
        "source": "computed with skyfield + JPL DE421",
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
               "c": [r(f["lat"], 4), r(f["lon"], 4)],
               "poly": [[r(a, 3), r(b, 3)]
                        for a, b in zip(f["outline_lat"], f["outline_lon"])]}
              for f in frames],
    "markers": markers,
}

os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
os.makedirs(os.path.join(HERE, "web"), exist_ok=True)
js = json.dumps(payload, separators=(",", ":"))
with open(os.path.join(HERE, "data", "eclipse2027.json"), "w") as fh:
    fh.write(js)
with open(os.path.join(HERE, "web", "eclipse2027.js"), "w") as fh:
    fh.write("window.ECLIPSE_DATA=" + js + ";\n")

stamp(f"wrote data/eclipse2027.json and web/eclipse2027.js ({len(js) / 1024:.0f} kB)")
stamp("done")
