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
