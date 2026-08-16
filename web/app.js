/* Interactive map of every total solar eclipse from 1986 to 2066.
   All eclipse geometry is computed by gen_data.py; the catalogue of which
   eclipses exist comes from find_eclipses.py. */

(function () {
  'use strict';

  // From here on the version tracks the task number. It had drifted by two:
  // TASK 5 was a validation-only change that never touched the page, and the
  // first working map was v1 before the numbered tasks began.
  var VERSION = 17;

  // Eclipses close enough to plan a trip for: still to come, and within this
  // calendar year plus two. Today that is exactly 2026-2028; deriving it from
  // the clock rather than hardcoding those years keeps it true next year.
  var NEAR_TERM_YEARS = 2;

  var SEEN_KEY = 'eclipse.pickerSeen';

  var FI_MONTHS = ['tammikuuta', 'helmikuuta', 'maaliskuuta', 'huhtikuuta',
                   'toukokuuta', 'kesäkuuta', 'heinäkuuta', 'elokuuta',
                   'syyskuuta', 'lokakuuta', 'marraskuuta', 'joulukuuta'];
  var FI_TYPE = { total: 'täydellinen', hybrid: 'hybridi' };

  // Which eclipse opens first is decided by the catalogue (index.default, set
  // in find_eclipses.py). This literal is only a floor for the case where the
  // catalogue itself failed to load.
  var FALLBACK_DATE = '2027-08-02';
  var ECLIPSE_DIR = '../data/eclipses/';

  var SPEEDS = [1, 60, 300, 600];
  var MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
                'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];

  // `at` staggers the label along each contour so the four levels do not pile
  // up on the same stretch of the path.
  var DUR_STYLE = {
    '60':  { color: '#ff8c42', label: '1m', at: 0.16 },
    '120': { color: '#ffab3d', label: '2m', at: 0.30 },
    '240': { color: '#ffc93c', label: '4m', at: 0.62 },
    '360': { color: '#ffe66d', label: '6m', at: 0.50 }
  };

  // -- helpers -------------------------------------------------------------

  function pad(n) { return (n < 10 ? '0' : '') + n; }

  function hms(sec) {
    sec = Math.max(0, Math.round(sec));
    return pad(Math.floor(sec / 3600) % 24) + ':' +
           pad(Math.floor(sec / 60) % 60) + ':' + pad(sec % 60);
  }

  function mmss(sec) {
    sec = Math.round(sec);
    return Math.floor(sec / 60) + ' min ' + pad(sec % 60) + ' s';
  }

  function shortdur(sec) {
    sec = Math.round(sec);
    return Math.floor(sec / 60) + 'm' + pad(sec % 60) + 's';
  }

  function fiDate(iso) {
    var p = iso.split('-');
    return parseInt(p[2], 10) + '. ' + FI_MONTHS[parseInt(p[1], 10) - 1] +
           ' ' + p[0];
  }

  function wrapLon(lon) { return ((lon + 540) % 360) - 180; }

  // Squared separation in degrees; only ever used to compare two candidates.
  function near2(a, b) {
    var dy = a[0] - b[0], dx = a[1] - b[1];
    return dy * dy + dx * dx;
  }

  // -- local time ----------------------------------------------------------
  //
  // Every time below comes out of tz.js as a "stamp": the wall clock at one
  // place at one instant, with the offset that zone is really on that date.
  // Nothing here converts anything; the numbers being printed are the same UTC
  // seconds the rest of the file works in.

  // A local date one day away from the UTC date is common enough east of
  // Kiribati and west of Alaska that it has to be said out loud.
  function dayTag(st) {
    if (!st.dayShift) return '';
    return ' <span class="dshift">' + (st.dayShift > 0 ? '+' : '−') +
           Math.abs(st.dayShift) + ' pv</span>';
  }

  // Three clocks for every event: the place's, the viewer's own, and UTC. One
  // row per event and one column per clock, with the zones named once in the
  // header - repeating "(UTC+2)" on five rows is five times the ink for one
  // fact, and it is the column of place times that has to stay readable.
  //
  // The viewer's zone comes from the browser itself, not from the box table:
  // Intl already knows where this browser thinks it is.
  function timesTable(pl, rows) {
    var here = TZ.viewer();
    var place0 = TZ.stamp(pl, instant(rows[0][1]));
    var here0 = here.zone ? TZ.stamp(here, instant(rows[0][1])) : null;
    // A viewer on the same offset as the place would read the same numbers
    // twice, so that column is dropped rather than duplicated.
    var showYou = here0 !== null && here0.offset !== place0.offset;

    var html = '<table class="times"><tr class="head"><td></td>' +
               '<td>paikallinen<span>' + place0.label + '</span></td>' +
               (showYou ? '<td>sinun aikasi<span>' + here0.label + '</span></td>'
                        : '') +
               '<td>UTC<span></span></td></tr>';
    rows.forEach(function (r) {
      var st = TZ.stamp(pl, instant(r[1]));
      html += '<tr><td>' + r[0] + '</td>' +
              '<td class="loc">' + hms(st.localSec) + dayTag(st) + '</td>';
      if (showYou) {
        var y = TZ.stamp(here, instant(r[1]));
        html += '<td class="you">' + hms(y.localSec) + dayTag(y) + '</td>';
      }
      html += '<td class="utc">' + hms(r[1]) + '</td></tr>';
    });
    return { html: html + '</table>', you: showYou ? here0 : null };
  }

  // An offset from a named zone is a fact; one from longitude/15 is a guess and
  // says so, here and in the tilde on the label itself.
  function zoneFoot(st, you) {
    return (st.exact
      ? 'paikallinen aika ' + st.zone + (st.abbr ? ' (' + st.abbr + ')' : '')
      : 'paikallisaika arvioitu pituuspiiristä (' + st.label + ')') +
      (you ? ' &nbsp;·&nbsp; sinun aikasi ' + you.zone : '');
  }

  // Paths that cross the antimeridian are stored as continuous longitudes, so a
  // test point has to be moved onto the same turn before it can be compared.
  function sameBranch(lon, ref) {
    return lon + 360 * Math.round((ref - lon) / 360);
  }

  // Ray casting in (lon, lat).
  function pointInRing(lat, lon, ring) {
    var inside = false;
    for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      var yi = ring[i][0], xi = ring[i][1];
      var yj = ring[j][0], xj = ring[j][1];
      if ((yi > lat) !== (yj > lat) &&
          lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) {
        inside = !inside;
      }
    }
    return inside;
  }

  // -- module state --------------------------------------------------------

  var map, umbra, umbraDot, clickPopup;
  var dynamic = [];          // layers belonging to the eclipse on screen
  var siteMarkers = {};
  var cache = {};            // date -> payload
  var data = null, frames = [], t0 = 0, t1 = 0, stepS = 60;
  var now = 0, speedIdx = 2, playing = false, last = 0;
  var el = {};
  var catalog = [], rowFor = {}, menuOpen = false;

  // Presentation only. Stored and computed times are UTC seconds from the
  // eclipse date's midnight throughout; `dayMs` turns one into a real instant,
  // which is what a time zone can be asked about, and `place` is the location
  // whose wall clock the header currently shows (null = plain UTC).
  var dayMs = 0, place = null;

  function instant(sec) { return dayMs + Math.round(sec) * 1000; }

  // -- eclipse geometry ----------------------------------------------------

  // Vertices are stored at the same fixed bearings in every frame, so a
  // straight vertex-by-vertex blend keeps the outline well behaved.
  function shapeAt(t) {
    var x = (Math.min(t1, Math.max(t0, t)) - t0) / stepS;
    var i = Math.min(frames.length - 2, Math.max(0, Math.floor(x)));
    var f = Math.min(1, Math.max(0, x - i));
    var a = frames[i], b = frames[i + 1];
    var ring = new Array(a.poly.length);
    for (var k = 0; k < a.poly.length; k++) {
      ring[k] = [a.poly[k][0] + (b.poly[k][0] - a.poly[k][0]) * f,
                 a.poly[k][1] + (b.poly[k][1] - a.poly[k][1]) * f];
    }
    return { ring: ring, centre: [a.c[0] + (b.c[0] - a.c[0]) * f,
                                  a.c[1] + (b.c[1] - a.c[1]) * f] };
  }

  // Time at which the umbra centre passes closest to (lat, lon): the click is
  // projected onto every leg of the centre track and the nearest projection
  // wins, so the answer moves smoothly rather than snapping to whole frames.
  function closestApproach(lat, lon) {
    var kx = Math.cos(lat * Math.PI / 180);
    var bestD2 = Infinity, bestT = t0;
    for (var i = 0; i < frames.length - 1; i++) {
      var a = frames[i].c, b = frames[i + 1].c;
      var bx = wrapLon(b[1] - a[1]) * kx, by = b[0] - a[0];
      var px = wrapLon(lon - a[1]) * kx, py = lat - a[0];
      var len2 = bx * bx + by * by;
      var u = len2 > 0 ? Math.max(0, Math.min(1, (px * bx + py * by) / len2)) : 0;
      var dx = px - u * bx, dy = py - u * by;
      var d2 = dx * dx + dy * dy;
      if (d2 < bestD2) { bestD2 = d2; bestT = frames[i].s + u * stepS; }
    }
    return bestT;
  }

  // Totality at an arbitrary point, read straight off the umbra outlines: the
  // point is inside the shadow between the two times the moving outline
  // crosses it. The crossings are bisected on the interpolated outline, which
  // is the same geometry the animation draws.
  function totalityAt(lat, lon) {
    var first = -1, last_ = -1;
    for (var i = 0; i < frames.length; i++) {
      if (pointInRing(lat, sameBranch(lon, frames[i].c[1]), frames[i].poly)) {
        if (first < 0) first = i;
        last_ = i;
      }
    }
    if (first < 0) return null;

    function crossing(tIn, tOut) {
      if (tIn === tOut) return tIn;
      for (var k = 0; k < 16; k++) {
        var m = (tIn + tOut) / 2;
        var s = shapeAt(m);
        if (pointInRing(lat, sameBranch(lon, s.centre[1]), s.ring)) tIn = m;
        else tOut = m;
      }
      return (tIn + tOut) / 2;
    }

    var t_in = crossing(frames[first].s, frames[first === 0 ? 0 : first - 1].s);
    var t_out = crossing(frames[last_].s,
                         frames[last_ === frames.length - 1 ? last_ : last_ + 1].s);
    // Truncated by the ends of the computed path rather than by the shadow.
    var clipped = (first === 0) || (last_ === frames.length - 1);
    return { start: t_in, end: t_out, duration: t_out - t_in,
             max: (t_in + t_out) / 2, clipped: clipped };
  }

  // -- local circumstances anywhere ----------------------------------------
  //
  // The path arrays only describe the umbra, so a click away from it had
  // nothing to answer with. data.local carries the Sun and the Moon in the
  // Earth-fixed frame once a minute across the whole partial phase; from those
  // two vectors the geometry for any point is the same three lines the
  // generator uses: separation against the two angular radii, with the Sun
  // required to be above the horizon.

  var WGS84_A = 6378.137, WGS84_F = 1 / 298.257223563;

  function observerXYZ(lat, lon) {
    var e2 = 2 * WGS84_F - WGS84_F * WGS84_F;
    var la = lat * Math.PI / 180, lo = lon * Math.PI / 180;
    var sinLa = Math.sin(la), cosLa = Math.cos(la);
    var n = WGS84_A / Math.sqrt(1 - e2 * sinLa * sinLa);
    return [n * cosLa * Math.cos(lo), n * cosLa * Math.sin(lo), n * (1 - e2) * sinLa];
  }

  function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
  function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
  function norm(a) { return Math.sqrt(dot(a, a)); }

  // How much of the Sun's disc the Moon covers: the area of the lens between
  // two circles, over the Sun's area. Magnitude is the fraction of the
  // *diameter* and is what "83 %" usually means in a forecast; obscuration is
  // the fraction of the *area*, which is what the light actually does.
  function obscuration(rs, rm, d) {
    if (d >= rs + rm) return 0;
    if (d <= Math.abs(rs - rm)) return rm >= rs ? 1 : (rm * rm) / (rs * rs);
    var c1 = (d * d + rs * rs - rm * rm) / (2 * d * rs);
    var c2 = (d * d + rm * rm - rs * rs) / (2 * d * rm);
    var area = rs * rs * Math.acos(Math.min(1, Math.max(-1, c1))) +
               rm * rm * Math.acos(Math.min(1, Math.max(-1, c2))) -
               0.5 * Math.sqrt(Math.max(0, (-d + rs + rm) * (d + rs - rm) *
                                           (d - rs + rm) * (d + rs + rm)));
    return area / (Math.PI * rs * rs);
  }

  // The state of the eclipse at one instant, for one observer.
  function sampleAt(local, p, up, i) {
    var sv = sub(local.sun[i], p), mv = sub(local.moon[i], p);
    var sd = norm(sv), md = norm(mv);
    var sep = Math.acos(Math.min(1, Math.max(-1, dot(sv, mv) / (sd * md))));
    var rs = Math.asin(local.r_sun_km / sd), rm = Math.asin(local.r_moon_km / md);
    return {
      s: local.t0_s + i * local.step_s,
      f: rs + rm - sep,                       // > 0 while any of the Sun is hidden
      mag: (rs + rm - sep) / (2 * rs),
      obsc: obscuration(rs, rm, sep),
      alt: Math.asin(dot(up, sv) / sd) * 180 / Math.PI,
      total: rm - rs - sep > 0
    };
  }

  // Linear crossing of f = 0 between two samples, which is where a contact is.
  function contactBetween(a, b) {
    if (a.f === b.f) return a.s;
    return a.s + (b.s - a.s) * (0 - a.f) / (b.f - a.f);
  }

  function circumstancesAt(lat, lon) {
    var local = data && data.local;
    if (!local || !local.sun || !local.sun.length) return null;
    var p = observerXYZ(lat, lon);
    var up = [p[0] / norm(p), p[1] / norm(p), p[2] / norm(p)];

    var best = null, first = -1, last_ = -1, firstUp = -1, lastUp = -1;
    var prev = null, c1 = null, c4 = null;
    var everUp = false, everCovered = false;
    for (var i = 0; i < local.sun.length; i++) {
      var now_ = sampleAt(local, p, up, i);
      if (now_.f > 0) {
        everCovered = true;
        if (first < 0) first = i;
        last_ = i;
        if (prev && prev.f <= 0) c1 = contactBetween(prev, now_);
        if (now_.alt > 0) {
          everUp = true;
          if (firstUp < 0) firstUp = i;
          lastUp = i;
          if (!best || now_.mag > best.mag) best = now_;
        }
      } else if (prev && prev.f > 0 && c4 === null) {
        c4 = contactBetween(prev, now_);
      }
      prev = now_;
    }
    if (!everCovered) return { visible: false, anywhere: false };
    if (!everUp) return { visible: false, anywhere: true };  // it happens, below the horizon

    // What the observer actually sees: the eclipse, clipped by the horizon.
    var startS = firstUp === first && c1 !== null ? c1 : local.t0_s + firstUp * local.step_s;
    var endS = lastUp === last_ && c4 !== null ? c4 : local.t0_s + lastUp * local.step_s;
    return {
      visible: true,
      anywhere: true,
      start: startS,
      max: best.s,
      end: endS,
      magnitude: Math.min(1, best.mag),
      obscuration: Math.min(1, best.obsc),
      total: best.total,
      altMax: best.alt,
      // the horizon, not the geometry, ended (or began) it
      cutByHorizon: lastUp !== last_,
      startedBelow: firstUp !== first
    };
  }

  // -- rendering -----------------------------------------------------------

  function clearEclipse() {
    dynamic.forEach(function (l) { map.removeLayer(l); });
    dynamic = [];
    siteMarkers = {};
    if (clickPopup) map.closePopup(clickPopup);
  }

  function add(layer) { layer.addTo(map); dynamic.push(layer); return layer; }

  // -- the high-latitude fade -----------------------------------------------
  //
  // Web Mercator stretches without limit towards the poles, and a track that
  // runs into the high arctic arrives as jagged crossing lines that read as a
  // drawing bug rather than as a shadow. Nobody watches totality from 85 N, so
  // above FADE_FROM the geometry is faded out instead of drawn, and by FADE_TO
  // it is gone. Presentation only: the data is untouched, and the umbra itself
  // still travels the whole path.
  var FADE_FROM = 72.0, FADE_TO = 80.0;
  // Opacity is quantised so a track becomes a handful of layers rather than one
  // per segment. It has to be fine enough that the steps do not show: the band
  // is a fill, and over Antarctic ice a coarse ramp reads as grey rectangles.
  var FADE_STEPS = 24;

  function fadeAt(lat) {
    var a = Math.abs(lat);
    if (a <= FADE_FROM) return 1;
    if (a >= FADE_TO) return 0;
    return (FADE_TO - a) / (FADE_TO - FADE_FROM);
  }

  // A segment is drawn at the weaker of its two ends, so nothing that touches
  // anything above FADE_TO survives.
  function fadeOf(a, b) {
    return Math.round(Math.min(fadeAt(a), fadeAt(b)) * FADE_STEPS) / FADE_STEPS;
  }

  // Split a line into runs of equal fade. Consecutive runs share the point
  // between them, so the pieces join without a gap.
  function fadeRuns(pts) {
    var runs = [], cur = null;
    for (var i = 0; i < pts.length - 1; i++) {
      var f = fadeOf(pts[i][0], pts[i + 1][0]);
      if (!cur || f !== cur.f) { cur = { f: f, pts: [pts[i]] }; runs.push(cur); }
      cur.pts.push(pts[i + 1]);
    }
    return runs.filter(function (r) { return r.f > 0; });
  }

  function addFadedLine(pts, style) {
    if (!pts || pts.length < 2) return;
    var base = style.opacity === undefined ? 1 : style.opacity;
    fadeRuns(pts).forEach(function (run) {
      var o = {};
      for (var k in style) o[k] = style[k];
      o.opacity = base * run.f;
      add(L.polyline(run.pts, o));
    });
  }

  // The shadow itself goes on the same ramp. It is one layer redrawn every
  // frame rather than a set of static ones, so its opacity is not quantised —
  // it dissolves smoothly — and it is driven by the outline's most extreme
  // point, the same "weakest end wins" rule the static geometry uses. Playback
  // over a wholly arctic stretch therefore ends in an empty map, which is the
  // point: above FADE_TO there is nothing to see but projection artefacts.
  var UMBRA_STYLE = { opacity: 0.55, fillOpacity: 0.62 };

  function fadeUmbra(ring) {
    var worst = 0;
    for (var i = 0; i < ring.length; i++) {
      var a = Math.abs(ring[i][0]);
      if (a > worst) worst = a;
    }
    var f = fadeAt(worst);
    umbra.setStyle({ opacity: UMBRA_STYLE.opacity * f,
                     fillOpacity: UMBRA_STYLE.fillOpacity * f });
    umbraDot.setStyle({ opacity: f, fillOpacity: f });
  }

  // The limits are sampled independently and need not be the same length, so
  // the band between them is walked by position along each line rather than by
  // index, and emitted as one ribbon per fade level.
  function pointAt(line, t) {
    var x = t * (line.length - 1);
    var i = Math.min(line.length - 2, Math.max(0, Math.floor(x)));
    var f = Math.min(1, Math.max(0, x - i));
    return [line[i][0] + (line[i + 1][0] - line[i][0]) * f,
            line[i][1] + (line[i + 1][1] - line[i][1]) * f];
  }

  function addFadedBand(north, south, style) {
    if (!north || !south || north.length < 2 || south.length < 2) return;
    var n = Math.max(north.length, south.length);
    var base = style.fillOpacity === undefined ? 1 : style.fillOpacity;
    var run = null;
    for (var i = 0; i < n - 1; i++) {
      var t0 = i / (n - 1), t1 = (i + 1) / (n - 1);
      var a0 = pointAt(north, t0), a1 = pointAt(north, t1);
      var b0 = pointAt(south, t0), b1 = pointAt(south, t1);
      var f = Math.min(fadeOf(a0[0], a1[0]), fadeOf(b0[0], b1[0]));
      if (!run || f !== run.f) {
        run = { f: f, north: [a0], south: [b0] };
        if (f > 0) {
          (function (r, style_) {
            var o = {};
            for (var k in style_) o[k] = style_[k];
            o.fillOpacity = base * r.f;
            r.layer = add(L.polygon([[]], o));
          })(run, style);
        }
      }
      run.north.push(a1);
      run.south.push(b1);
      if (run.layer) run.layer.setLatLngs([run.north.concat(run.south.slice().reverse())]);
    }
  }

  function buildEclipse(d) {
    var north = d.path.north, south = d.path.south, centre = d.path.center;

    // The band between the two limits, as a ribbon that fades out to the north.
    addFadedBand(north, south, {
      pane: 'overlayPane', stroke: false,
      fillColor: '#000913', fillOpacity: 0.42, interactive: false
    });

    [north, south].forEach(function (line) {
      addFadedLine(line, {
        color: '#ffd24a', weight: 1.6, opacity: 0.95, interactive: false
      });
    });

    Object.keys(DUR_STYLE).forEach(function (lv) {
      var c = d.contours[lv];
      if (!c) return;
      var st = DUR_STYLE[lv];
      ['north', 'south'].forEach(function (side) {
        var pts = c[side];
        if (!pts || pts.length < 2) return;
        addFadedLine(pts, {
          color: st.color, weight: 1.1, opacity: 0.8, interactive: false
        });
        var at = side === 'north' ? st.at : 1 - st.at;
        var mid = pts[Math.min(pts.length - 1, Math.floor(pts.length * at))];
        // A label belonging to a stretch that has faded away goes with it.
        if (fadeAt(mid[0]) <= 0) return;
        add(L.marker(mid, {
          interactive: false, opacity: fadeAt(mid[0]),
          icon: L.divIcon({ className: 'dur-label', html: st.label, iconSize: null })
        }));
      });
    });

    var centrePts = centre.map(function (p) { return [p[0], p[1]]; });
    addFadedLine(centrePts, {
      color: '#ff4b3e', weight: 1.5, opacity: 0.95, interactive: false
    });

    // A hybrid's central line runs on past the total section at both ends, with
    // the antumbra on the ground instead of the umbra. Same line, different
    // eclipse: amber rather than red, and dashed, because there is no totality
    // to be had along it. Each stretch is joined to the nearer end of the total
    // section so the track reads as one continuous path rather than three.
    (d.path.annular || []).forEach(function (run) {
      var pts = run.map(function (p) { return [p[0], p[1]]; });
      var last = centrePts[centrePts.length - 1];
      if (near2(pts[pts.length - 1], centrePts[0]) <= near2(pts[0], last)) {
        pts.push(centrePts[0]);
      } else {
        pts.unshift(last);
      }
      fadeRuns(pts).forEach(function (piece) {
        add(L.polyline(piece.pts, {
          color: '#ffb03a', weight: 1.5, opacity: 0.9 * piece.f,
          dashArray: '5 4'
        }).bindTooltip('rengasmainen tällä osuudella', { sticky: true }));
      });
    });

    umbra = add(L.polygon([frames[0].poly], {
      pane: 'umbra', color: '#cfe4ff', weight: 1, interactive: false,
      opacity: UMBRA_STYLE.opacity, fillColor: '#000308',
      fillOpacity: UMBRA_STYLE.fillOpacity
    }));
    umbraDot = add(L.circleMarker(frames[0].c, {
      pane: 'umbra', radius: 2.6, color: '#ffd24a', weight: 1.4,
      fillColor: '#ffd24a', fillOpacity: 1, interactive: false
    }));
    fadeUmbra(frames[0].poly);

    // Dots only, no permanent labels: six of the 2027 sites sit within 200 km
    // of each other and any always-on text turns to mush when zoomed out.
    (d.markers || []).forEach(function (m) {
      siteMarkers[m.name] = add(L.marker([m.lat, m.lon], {
        icon: L.divIcon({
          className: 'site-dot' + (m.duration ? '' : ' site-dot-partial'),
          iconSize: [10, 10]
        }),
        title: m.name, riseOnHover: true
      }).bindTooltip(m.name, { direction: 'top', offset: [0, -7] })
        // Wide enough for three clocks side by side without wrapping a column.
        .bindPopup(popupHtml(m), { maxWidth: popupMax() })
        // Opening a site hands its zone to the header clock. The time itself is
        // deliberately left alone: a marker click is a request to read, not to
        // move the timeline.
        .on('popupopen', function () { setPlace(TZ.named(m.tz, m.lon)); }));
    });
  }

  function showEclipse(d) {
    data = d;
    // Marked here rather than in selectEclipse: the eclipse loaded eagerly at
    // start-up reaches this point directly, and its row must be marked too.
    markSelected(d.meta.date);
    frames = d.umbra;
    t0 = frames[0].s;
    t1 = frames[frames.length - 1].s;
    stepS = d.meta.step_s;
    // Set before the popups are built: they need a real instant to ask the tz
    // database about. A new eclipse starts with no place chosen.
    dayMs = Date.parse(d.meta.date + 'T00:00:00Z');
    place = null;

    clearEclipse();
    buildEclipse(d);

    el.cardTitle.textContent = fiDate(d.meta.date);
    var i = catalog.findIndex(function (e) { return e.date === d.meta.date; });
    var kind = i >= 0 ? (FI_TYPE[catalog[i].type] || catalog[i].type) : '';
    el.cardBadge.textContent = (i >= 0 ? (i + 1) + ' / ' + catalog.length +
                                ' pimennystä' : '') + (kind ? ' · ' + kind : '');
    el.titleInfo.textContent = 'kesto keskilinjalla enintään ' +
                               mmss(d.meta.max_duration_s);
    el.version.textContent = 'v' + VERSION + (d.meta.git ? ' · ' + d.meta.git : '');

    el.slider.min = t0;
    el.slider.max = t1;
    el.slider.step = 1;

    // Web Mercator cannot draw past about 85 degrees, so a path that runs to
    // the pole would otherwise fit the map to a band of empty space.
    var pts = d.path.north.concat(d.path.south).map(function (p) {
      return [Math.max(-84, Math.min(84, p[0])), p[1]];
    });
    map.fitBounds(L.latLngBounds(pts), { padding: [30, 90], animate: false });

    setTime(t0);
    setPlaying(true);
    window.eclipse.data = d;
    window.eclipse.markers = siteMarkers;
  }

  // -- lazy loading --------------------------------------------------------

  // -- the picker: the title card is the trigger, the list hangs under it ----

  function buildMenu() {
    catalog = (window.ECLIPSE_INDEX && window.ECLIPSE_INDEX.eclipses) || [];
    if (!catalog.length) catalog = [{ date: FALLBACK_DATE, type: 'total',
                                      max_duration_s: 0, regions: '' }];

    // "Next" is relative to whenever the page is opened, not to build time.
    var today = new Date().toISOString().slice(0, 10);
    var nextIdx = catalog.findIndex(function (e) { return e.date >= today; });
    var lastNearYear = parseInt(today.slice(0, 4), 10) + NEAR_TERM_YEARS;

    var decade = null;
    catalog.forEach(function (e, i) {
      var dec = e.date.slice(0, 3) + '0';
      if (dec !== decade) {
        decade = dec;
        var h = document.createElement('div');
        h.className = 'group';
        h.textContent = dec + '-luku';
        el.menu.appendChild(h);
      }
      var past = e.date < today;
      var near = !past && parseInt(e.date.slice(0, 4), 10) <= lastNearYear;
      var row = document.createElement('div');
      row.className = 'row' + (past ? ' past' : '') + (near ? ' near' : '') +
                      (i === nextIdx ? ' next' : '');
      row.setAttribute('role', 'option');
      row.dataset.date = e.date;
      row.dataset.i = i;
      row.title = e.date + ' · ' + (FI_TYPE[e.type] || e.type) + ' · ' +
                  shortdur(e.max_duration_s) + ' · ' + e.regions;
      row.innerHTML =
        '<span class="d">' + e.date + '</span>' +
        '<span class="k' + (e.type === 'hybrid' ? ' hyb' : '') + '">' +
        (FI_TYPE[e.type] || e.type) + '</span>' +
        '<span class="d n">' + shortdur(e.max_duration_s) + '</span>' +
        '<span class="g">' + e.regions + '</span>' +
        (i === nextIdx ? '<span class="tag">seuraava</span>' : '<span></span>');
      row.onclick = function () { closeMenu(); selectEclipse(e.date); };
      el.menu.appendChild(row);
      rowFor[e.date] = row;
    });
    el.pickLabel.textContent = 'Valitse pimennys (' + catalog.length + ')';
  }

  function openMenu() {
    if (menuOpen) return;
    menuOpen = true;
    el.menu.hidden = false;
    el.card.setAttribute('aria-expanded', 'true');
    stopPulse();
    var cur = rowFor[pending];
    if (cur) cur.scrollIntoView({ block: 'center' });
  }

  function closeMenu() {
    if (!menuOpen) return;
    menuOpen = false;
    el.menu.hidden = true;
    el.card.setAttribute('aria-expanded', 'false');
  }

  function stopPulse() { el.chev.classList.remove('pulse'); }

  // A single gentle nudge the first time this browser ever sees the page. The
  // flag is written as soon as the cue starts, not when it ends, so closing the
  // page mid-animation still counts as having been shown it.
  function maybePulse() {
    var seen;
    try { seen = localStorage.getItem(SEEN_KEY); } catch (err) { seen = '1'; }
    if (seen) return;
    try { localStorage.setItem(SEEN_KEY, '1'); } catch (err) { /* private mode */ }
    el.chev.classList.add('pulse');
    setTimeout(stopPulse, 3000);
  }

  function moveActive(delta) {
    var rows = el.menu.querySelectorAll('.row');
    var cur = el.menu.querySelector('.row.active') || rowFor[pending];
    var i = cur ? parseInt(cur.dataset.i, 10) : 0;
    i = Math.max(0, Math.min(rows.length - 1, i + delta));
    rows.forEach(function (r) { r.classList.remove('active'); });
    rows[i].classList.add('active');
    rows[i].scrollIntoView({ block: 'nearest' });
  }

  var pending = null;        // the eclipse the user last asked for

  function markSelected(date) {
    Object.keys(rowFor).forEach(function (d) {
      rowFor[d].setAttribute('aria-selected', d === date ? 'true' : 'false');
      rowFor[d].classList.remove('active');
    });
  }

  function selectEclipse(date) {
    pending = date;
    markSelected(date);
    if (cache[date]) { showEclipse(cache[date]); return; }
    el.titleInfo.textContent = 'ladataan ' + date + '…';
    var s = document.createElement('script');
    s.src = ECLIPSE_DIR + date + '.js';
    s.onerror = function () {
      if (pending === date) {
        el.titleInfo.textContent = date + ': dataa ei löytynyt — aja gen_data.py --all';
      }
    };
    document.head.appendChild(s);
  }

  // Each generated file calls this with its payload. A slow load that has been
  // superseded by another pick is kept in the cache but not shown.
  window.ECLIPSE_LOAD = function (payload) {
    cache[payload.meta.date] = payload;
    if (payload.meta.date === pending) showEclipse(payload);
  };

  // -- playback ------------------------------------------------------------

  function setTime(t, fromSlider) {
    now = Math.min(t1, Math.max(t0, t));
    var s = shapeAt(now);
    umbra.setLatLngs([s.ring]);
    umbraDot.setLatLng(s.centre);
    fadeUmbra(s.ring);
    renderClock();
    if (!fromSlider) el.slider.value = now;
    el.slider.style.setProperty('--fill', ((now - t0) / (t1 - t0) * 100) + '%');
  }

  function dayLabel(ms) {
    var d = new Date(ms);
    return d.getUTCDate() + ' ' + MONTHS[d.getUTCMonth()];
  }

  // With no place chosen the clock is plain UTC, as it was. Once the user picks
  // a point or a site it reads that place's wall clock, and the UTC value moves
  // into the line underneath rather than disappearing.
  function renderClock() {
    el.utc.textContent = hms(now);
    if (!place) {
      el.time.textContent = hms(now);
      el.zone.textContent = 'UTC';
      el.clockDay.textContent = dayLabel(instant(now));
      el.utcWrap.hidden = true;
      el.clock.title = 'Klikkaa karttaa: kello vaihtuu paikalliseen aikaan';
      return;
    }
    var st = TZ.stamp(place, instant(now));
    el.time.textContent = hms(st.localSec);
    el.zone.textContent = st.label;
    el.clockDay.textContent = dayLabel(st.localMs);
    el.utcWrap.hidden = false;
    el.clock.title = (st.exact
      ? st.zone + (st.abbr ? ' (' + st.abbr + ')' : '')
      : 'vyöhyke arvioitu pituuspiiristä') + ' · ' + hms(now) + ' UTC';
  }

  function setPlace(p) {
    place = p;
    renderClock();
  }

  function tick(ms) {
    if (!playing) return;
    var dt = last ? Math.min(0.25, (ms - last) / 1000) : 0;
    last = ms;
    var t = now + dt * SPEEDS[speedIdx];
    if (t >= t1) t = t0;          // loop back to the start of the path
    setTime(t);
    requestAnimationFrame(tick);
  }

  function setPlaying(on) {
    playing = on;
    document.body.classList.toggle('playing', on);
    last = 0;
    if (on) requestAnimationFrame(tick);
  }

  // -- popups --------------------------------------------------------------

  // Three clocks need room, but not more room than the window has: on a phone
  // the popup is capped to the viewport and the table tightens up in CSS.
  function popupMax() {
    // The wrapper adds its own padding and border around this, so the window
    // budget has to be spent with a margin to spare.
    return Math.max(230, Math.min(430, window.innerWidth - 46));
  }

  function popupHtml(m) {
    // Marked sites carry their own IANA zone, so nothing is looked up here.
    var pl = TZ.named(m.tz, m.lon);
    var rows = [];

    function row(label, sec) {
      if (sec !== undefined) rows.push([label, sec]);
    }

    var head, note = '';
    if (m.duration) {
      head = '<div class="big">' + mmss(m.duration) + ' totaliteettia</div>';
    } else {
      head = m.max_magnitude !== undefined
        ? '<div class="big">' + Math.round(m.max_magnitude * 100) + ' % osittainen</div>'
        : '<div class="big">Ei totaliteettia</div>';
      note = '<p class="note">Totaliteettivyöhykkeen ulkopuolella' +
             (m.dist_to_path_km !== undefined
               ? ' &mdash; ' + Math.round(m.dist_to_path_km) + ' km reunasta'
               : '') + '</p>';
    }

    row('Osittainen alkaa', m.partial_start);
    row('Totaliteetti alkaa', m.total_start);
    row('Maksimi', m.max_s);
    row('Totaliteetti loppuu', m.total_end);
    row('Osittainen loppuu', m.partial_end);

    var t = timesTable(pl, rows);
    return '<h3>' + m.name + '</h3>' + head + note + t.html +
           '<p class="foot">' + Math.abs(m.lat).toFixed(4) + '°' +
           (m.lat < 0 ? 'S' : 'N') + ', ' +
           Math.abs(m.lon).toFixed(4) + '°' + (m.lon < 0 ? 'W' : 'E') +
           ' &nbsp;·&nbsp; ' +
           zoneFoot(TZ.stamp(pl, instant(m.max_s)), t.you) + '</p>';
  }

  // -- start up ------------------------------------------------------------

  function init() {
    ['slider', 'play', 'speed', 'jump', 'version', 'chev'].forEach(function (id) {
      el[id] = document.getElementById(id);
    });
    el.time = document.getElementById('clock-time');
    el.clock = document.getElementById('clock');
    el.zone = document.getElementById('clock-zone');
    el.clockDay = document.getElementById('clock-day');
    el.utc = document.getElementById('clock-utc');
    el.utcWrap = document.getElementById('clock-utc-wrap');
    el.titleInfo = document.getElementById('title-info');
    el.card = document.getElementById('eclipse-card');
    el.menu = document.getElementById('eclipse-menu');
    el.cardTitle = document.getElementById('card-title');
    el.cardBadge = document.getElementById('card-badge');
    el.pickLabel = document.getElementById('pick-label');

    map = L.map('map', {
      zoomControl: false,
      // Left false on purpose: paths crossing the antimeridian are drawn with
      // continuous longitudes past +/-180, and wrapping the view would leave
      // them a whole world away from the visible copy.
      worldCopyJump: false,
      minZoom: 2, maxZoom: 17, attributionControl: true
    });
    L.control.zoom({ position: 'topright' }).addTo(map);

    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      { maxZoom: 17,
        attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics ' +
                     '| Pimennysgeometria laskettu skyfield + JPL DE440s' }
    ).addTo(map);

    // Place names sit above the imagery but below the shading.
    map.createPane('labels');
    map.getPane('labels').style.zIndex = 350;
    map.getPane('labels').style.pointerEvents = 'none';
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
      { maxZoom: 17, pane: 'labels', opacity: 0.85 }
    ).addTo(map);

    map.createPane('umbra');
    map.getPane('umbra').style.zIndex = 450;

    clickPopup = L.popup({ maxWidth: popupMax(), className: 'click-popup',
                           autoPan: false });

    buildMenu();
    el.card.onclick = function () { menuOpen ? closeMenu() : openMenu(); };
    // A click anywhere else dismisses it; the card's own click is handled above.
    document.addEventListener('mousedown', function (e) {
      if (menuOpen && !el.menu.contains(e.target) && !el.card.contains(e.target)) {
        closeMenu();
      }
    });

    // Controls.
    el.play.onclick = function () { setPlaying(!playing); };
    el.speed.onclick = function () {
      speedIdx = (speedIdx + 1) % SPEEDS.length;
      el.speed.innerHTML = SPEEDS[speedIdx] + '&times;';
    };
    el.jump.onclick = function () {
      var c = data.path.center, best = 0, bestD = -1;
      for (var i = 0; i < c.length; i++) {
        if (c[i][3] > bestD) { bestD = c[i][3]; best = i; }
      }
      setTime(t0 + best * stepS);
      map.setView([c[best][0], c[best][1]], Math.max(map.getZoom(), 5));
    };
    el.slider.oninput = function () {
      setPlaying(false);
      setTime(parseFloat(el.slider.value), true);
    };

    map.on('click', function (e) {
      var lat = e.latlng.lat, lon = wrapLon(e.latlng.lng);
      setPlaying(false);
      // The zone comes from the point on the ground, never from the browser:
      // the viewer may be in Finland reading times for Egypt.
      var pl = TZ.at(lat, lon);
      setPlace(pl);
      setTime(closestApproach(lat, lon));

      var tot = totalityAt(lat, lon);
      var loc = circumstancesAt(lat, lon);
      var html, rows, stampSec;

      if (tot) {
        // Inside the path: the headline is the length of totality, as before.
        html = tot.clipped
          // The shadow reaches this point outside the computed window, so the
          // duration would be an undercount. Show only what is certain.
          ? '<div class="big">totaliteetti</div>'
          : '<div class="big">' + mmss(tot.duration) + '</div>';
        // Start and end as their own rows rather than a range in one cell: three
        // clocks wide, a range would not fit on a line.
        rows = tot.clipped ? [['Maksimi', tot.max]]
                           : [['Alkaa', tot.start], ['Maksimi', tot.max],
                              ['Loppuu', tot.end]];
        stampSec = tot.max;
      } else if (loc && loc.visible) {
        // Outside the path but the Sun is partly covered here: say by how much
        // and when, which is what most of the map wanted to know.
        html = '<div class="big">Osittainen: ' + Math.round(loc.obscuration * 100) +
               ' % peitto</div>' +
               '<p class="sub">magnitudi ' + loc.magnitude.toFixed(2).replace('.', ',') +
               ' &nbsp;·&nbsp; aurinko ' + Math.round(loc.altMax) + '° korkeudella</p>';
        rows = [['Alkaa', loc.start], ['Maksimi', loc.max], ['Loppuu', loc.end]];
        stampSec = loc.max;
      } else if (loc && loc.anywhere) {
        html = '<div class="big">Ei näy täällä</div>' +
               '<p class="sub">pimennys tapahtuu, mutta aurinko on horisontin alla</p>';
      } else if (loc) {
        html = '<div class="big">Ei näy täällä</div>' +
               '<p class="sub">aurinko ei peity lainkaan tässä pisteessä</p>';
      } else {
        // An older data file without the local block: say so rather than
        // showing an empty popup.
        html = '<div class="big">Ei tietoja</div>' +
               '<p class="sub">tälle pimennykselle ei ole laskettu paikallisia oloja</p>';
      }

      if (loc && loc.visible && loc.cutByHorizon) {
        html += '<p class="sub warn">aurinko laskee kesken pimennyksen</p>';
      }
      if (loc && loc.visible && loc.startedBelow) {
        html += '<p class="sub warn">pimennys on jo alkanut auringon noustessa</p>';
      }

      clickPopup.options.maxWidth = popupMax();
      var foot = Math.abs(lat).toFixed(3) + '°' + (lat < 0 ? 'S' : 'N') + ', ' +
                 Math.abs(lon).toFixed(3) + '°' + (lon < 0 ? 'W' : 'E');
      if (rows) {
        var t = timesTable(pl, rows);
        html += t.html;
        foot += ' &nbsp;·&nbsp; ' + zoneFoot(TZ.stamp(pl, instant(stampSec)), t.you);
      }
      html += '<p class="foot">' + foot + '</p>';
      clickPopup.setLatLng(e.latlng).setContent(html).openOn(map);
    });

    document.addEventListener('keydown', function (e) {
      if (menuOpen) {
        // While the list is open the arrows walk it rather than the timeline.
        if (e.key === 'Escape') { e.preventDefault(); closeMenu(); el.card.focus(); }
        else if (e.key === 'ArrowDown') { e.preventDefault(); moveActive(1); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); moveActive(-1); }
        else if (e.key === 'Enter') {
          var a = el.menu.querySelector('.row.active');
          if (a) { e.preventDefault(); closeMenu(); selectEclipse(a.dataset.date); }
        }
        return;
      }
      // Buttons handle their own Enter/Space; letting the shortcut through as
      // well would fire the action twice and cancel itself out.
      if (e.target.tagName === 'BUTTON' || e.target.tagName === 'SELECT') return;
      if (e.target.tagName === 'INPUT' && e.key !== ' ') return;
      if (e.key === ' ') { e.preventDefault(); setPlaying(!playing); }
      else if (e.key === 'ArrowRight') { setPlaying(false); setTime(now + stepS); }
      else if (e.key === 'ArrowLeft') { setPlaying(false); setTime(now - stepS); }
    });

    // Small handle for scripted checks and for poking at the map from a console.
    window.eclipse = {
      map: map, data: null, setTime: setTime, setPlaying: setPlaying,
      markers: siteMarkers, isPlaying: function () { return playing; },
      time: function () { return now; }, closestApproach: closestApproach,
      totalityAt: totalityAt, circumstancesAt: circumstancesAt, select: selectEclipse,
      index: window.ECLIPSE_INDEX || null, version: VERSION,
      openMenu: openMenu, closeMenu: closeMenu,
      menuOpen: function () { return menuOpen; }, catalog: catalog,
      // Local-time presentation, for scripted checks: the place whose clock is
      // on screen, and the stamp any point on the map would produce.
      place: function () { return place; },
      stampAt: function (lat, lon, sec) {
        return TZ.stamp(TZ.at(lat, wrapLon(lon)),
                        instant(sec === undefined ? now : sec));
      },
      stampFor: function (zone, sec) {
        return TZ.stamp(TZ.named(zone), instant(sec === undefined ? now : sec));
      }
    };

    maybePulse();
    var start = (window.ECLIPSE_INDEX && window.ECLIPSE_INDEX.default) ||
                FALLBACK_DATE;
    pending = start;
    if (window.ECLIPSE_DATA && window.ECLIPSE_DATA.meta.date === start) {
      cache[start] = window.ECLIPSE_DATA;
      showEclipse(window.ECLIPSE_DATA);
    } else {
      if (window.ECLIPSE_DATA) {
        cache[window.ECLIPSE_DATA.meta.date] = window.ECLIPSE_DATA;
      }
      selectEclipse(start);
    }
  }

  init();
})();
