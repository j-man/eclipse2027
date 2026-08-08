"""Shared eclipse geometry.

The umbra criterion and the local-circumstances calculation live here so that
gen_data.py (which builds the map data) and check_oracle.py (which compares
that calculation against published predictions) exercise exactly the same code.

A point on Earth is inside the umbra at time t when, as seen by an observer
standing there:

    separation(Sun, Moon) + angular_radius(Sun) < angular_radius(Moon)

with angular_radius = asin(R / distance), and the Sun above the horizon.
"""

import numpy as np
from skyfield.api import load, wgs84
from skyfield.framelib import itrs

R_SUN_KM = 696000.0
R_MOON_KM = 1737.4
R_EARTH_KM = 6371.0

ts = load.timescale()
eph = load("de440s.bsp")
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

    `epoch` is a skyfield Time; `sec` are offsets from it in seconds.
    """

    def __init__(self, epoch, sec):
        self.epoch = epoch
        self.sec = np.asarray(sec, dtype=float)
        t = ts.tt_jd(epoch.tt + self.sec / 86400.0)
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


# --------------------------------------------------------------- shadow axis
#
# The axis is the line from the Sun's centre through the Moon's centre. Where it
# meets the ellipsoid is the deepest point of the shadow, so testing the umbra
# criterion there answers "is anyone seeing totality right now" exactly, for an
# umbra of any size. A lat/lon grid coarse enough to sweep decades would step
# straight over the few-kilometre umbra of a barely-total hybrid eclipse.

A_KM, F = 6378.137, 1.0 / 298.257223563
B_KM = A_KM * (1.0 - F)
E2 = 2 * F - F * F


def axis_surface_point(S, M):
    """Where the Sun-Moon axis meets the WGS84 ellipsoid, in GCRS km.

    Returns (P, hits): P is the sunward intersection, or the closest point on
    the ellipsoid when the axis misses it entirely (a grazing eclipse can still
    put part of the umbra on the limb).  Scaling z by a/b turns the ellipsoid
    into a sphere, so the ray test is the ordinary quadratic.
    """
    k = A_KM / B_KM
    Ss = np.array([S[0], S[1], S[2] * k])
    Ms = np.array([M[0], M[1], M[2] * k])
    d = Ms - Ss
    u = d / np.linalg.norm(d, axis=0)
    b = (Ms * u).sum(axis=0)
    c = (Ms * Ms).sum(axis=0) - A_KM ** 2
    disc = b * b - c
    hits = disc >= 0.0
    t_hit = -b - np.sqrt(np.maximum(disc, 0.0))
    perp = Ms - b * u
    perp_len = np.linalg.norm(perp, axis=0)
    P_miss = perp * (A_KM / np.where(perp_len > 0, perp_len, 1.0))
    P = np.where(hits, Ms + t_hit * u, P_miss)
    return np.array([P[0], P[1], P[2] / k]), hits


def classify(S, M):
    """total / annular flags at the axis point, for each column of S and M.

    Also returns how far the axis passes from the Earth's centre, which is the
    standard definition of the instant of greatest eclipse.
    """
    P, hits = axis_surface_point(S, M)
    sv, mv = S - P, M - P
    sd = np.linalg.norm(sv, axis=0)
    md = np.linalg.norm(mv, axis=0)
    sep = np.arccos(np.clip((sv * mv).sum(axis=0) / (sd * md), -1.0, 1.0))
    rs = np.arcsin(R_SUN_KM / sd)
    rm = np.arcsin(R_MOON_KM / md)
    up = P / np.linalg.norm(P, axis=0)
    sunlit = (up * sv).sum(axis=0) > 0
    total = (rm - rs - sep > 0) & sunlit
    annular = (rs - rm - sep > 0) & sunlit & hits

    u = (M - S) / np.linalg.norm(M - S, axis=0)
    axis_dist = np.linalg.norm(M - (M * u).sum(axis=0) * u, axis=0)
    return P, total, annular, axis_dist


def geodetic(P, t):
    """GCRS km -> (lat, lon) degrees on the WGS84 ellipsoid.

    rotation_at gives GCRS -> ITRS, so the contraction runs over the matrix's
    column index; contracting the row index instead applies the inverse and
    silently mirrors every longitude.
    """
    rot = itrs.rotation_at(t)
    xyz = rot @ P if rot.ndim == 2 else np.einsum("rci,ci->ri", rot, P)
    x, y, z = xyz
    lon = np.degrees(np.arctan2(y, x))
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1 - E2))
    for _ in range(5):                                    # Bowring iteration
        n = A_KM / np.sqrt(1 - E2 * np.sin(lat) ** 2)
        lat = np.arctan2(z + n * E2 * np.sin(lat), p)
    return np.degrees(lat), (lon + 540.0) % 360.0 - 180.0


def edge_cross(sec, f, i, forward):
    """Time where f crosses zero next to index i, by linear interpolation."""
    j = i + 1 if forward else i - 1
    if j < 0 or j >= f.size or f[i] == f[j]:
        return float(sec[i])
    return float(sec[i] + (sec[j] - sec[i]) * f[i] / (f[i] - f[j]))


def local_circumstances(sky, lat, lon):
    """Contact times, totality duration, peak magnitude and time of maximum.

    `sky` must be a SkyTable whose grid covers the whole partial phase at this
    location.  Times are returned as seconds from the table's epoch.
    """
    sec = sky.sec
    m, sep, sd, md = sky.margin(lat, lon, 0, sec.size)
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
        # Eclipse magnitude: the fraction of the Sun's *diameter* covered at its
        # deepest, which is what "NN % partial" normally quotes.
        mag = (rs[p] + rm[p] - sep[p]) / (2 * rs[p])
        k = p[int(np.argmax(mag))]
        out["max_magnitude"] = float(np.clip(mag.max(), 0.0, 1.0))
        # Refine the instant of maximum with a parabola through its neighbours.
        if 0 < k < sec.size - 1:
            y0, y1, y2 = -sep[k - 1], -sep[k], -sep[k + 1]
            den = y0 - 2 * y1 + y2
            shift = 0.5 * (y0 - y2) / den if den != 0 else 0.0
            out["max_s"] = float(sec[k] + np.clip(shift, -1, 1) * (sec[1] - sec[0]))
        else:
            out["max_s"] = float(sec[k])
    if (m > 0).any():
        q = np.where(m > 0)[0]
        out["total_start"] = edge_cross(sec, m, q[0], False)
        out["total_end"] = edge_cross(sec, m, q[-1], True)
        out["duration"] = out["total_end"] - out["total_start"]
    return out
