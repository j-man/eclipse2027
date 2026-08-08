/* Interactive map of the total solar eclipse of 2 August 2027.
   All eclipse geometry comes from data/eclipse2027.json, computed by gen_data.py. */

(function () {
  'use strict';

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

  // -- data loading --------------------------------------------------------
  // eclipse2027.js defines window.ECLIPSE_DATA, which works over file:// too.
  // If the page is served over http and that file is missing, fall back to the
  // canonical JSON next door.

  if (window.ECLIPSE_DATA) {
    start(window.ECLIPSE_DATA);
  } else {
    fetch('../data/eclipse2027.json')
      .then(function (r) { return r.json(); })
      .then(start)
      .catch(function () {
        document.body.innerHTML =
          '<p style="padding:2rem;font:14px system-ui">Dataa ei löytynyt. ' +
          'Aja ensin <code>python3 gen_data.py</code>.</p>';
      });
  }

  // -- helpers -------------------------------------------------------------

  function pad(n) { return (n < 10 ? '0' : '') + n; }

  function hms(sec) {
    sec = Math.max(0, Math.round(sec));
    return pad(Math.floor(sec / 3600) % 24) + ':' +
           pad(Math.floor(sec / 60) % 60) + ':' + pad(sec % 60);
  }

  function hm(sec) {
    sec = Math.max(0, Math.round(sec));
    return pad(Math.floor(sec / 3600) % 24) + ':' + pad(Math.floor(sec / 60) % 60);
  }

  function mmss(sec) {
    sec = Math.round(sec);
    return Math.floor(sec / 60) + ' min ' + pad(sec % 60) + ' s';
  }

  // -- main ----------------------------------------------------------------

  function start(data) {
    var frames = data.umbra;
    var t0 = frames[0].s;
    var t1 = frames[frames.length - 1].s;
    var stepS = data.meta.step_s;

    var map = L.map('map', {
      zoomControl: false,
      worldCopyJump: true,
      minZoom: 2,
      maxZoom: 17,
      attributionControl: true
    });
    L.control.zoom({ position: 'topright' }).addTo(map);

    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      {
        maxZoom: 17,
        attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics ' +
                     '| Pimennysgeometria laskettu skyfield + JPL DE421'
      }
    ).addTo(map);

    // Place names sit above the imagery but below the shading, as in the reference.
    map.createPane('labels');
    map.getPane('labels').style.zIndex = 350;
    map.getPane('labels').style.pointerEvents = 'none';
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
      { maxZoom: 17, pane: 'labels', opacity: 0.85 }
    ).addTo(map);

    map.createPane('umbra');
    map.getPane('umbra').style.zIndex = 450;

    // -- path of totality --------------------------------------------------

    var north = data.path.north;
    var south = data.path.south;
    var centre = data.path.center;

    // The band between the two limits, drawn as one closed ring.
    L.polygon([north.concat(south.slice().reverse())], {
      pane: 'overlayPane',
      stroke: false,
      fillColor: '#000913',
      fillOpacity: 0.42,
      interactive: false
    }).addTo(map);

    [north, south].forEach(function (line) {
      L.polyline(line, {
        color: '#ffd24a', weight: 1.6, opacity: 0.95, interactive: false
      }).addTo(map);
    });

    // Duration contours, outermost first so the shortest sits under the rest.
    Object.keys(DUR_STYLE).forEach(function (lv) {
      var c = data.contours[lv];
      if (!c) return;
      var st = DUR_STYLE[lv];
      ['north', 'south'].forEach(function (side) {
        var pts = c[side];
        if (!pts || pts.length < 2) return;
        L.polyline(pts, {
          color: st.color, weight: 1.1, opacity: 0.8, interactive: false
        }).addTo(map);
        var at = side === 'north' ? st.at : 1 - st.at;
        var mid = pts[Math.min(pts.length - 1, Math.floor(pts.length * at))];
        L.marker(mid, {
          interactive: false,
          icon: L.divIcon({ className: 'dur-label', html: st.label, iconSize: null })
        }).addTo(map);
      });
    });

    L.polyline(centre.map(function (p) { return [p[0], p[1]]; }), {
      color: '#ff4b3e', weight: 1.5, opacity: 0.95, interactive: false
    }).addTo(map);

    // -- moving umbra ------------------------------------------------------

    var umbra = L.polygon([frames[0].poly], {
      pane: 'umbra',
      color: '#cfe4ff',
      weight: 1,
      opacity: 0.55,
      fillColor: '#000308',
      fillOpacity: 0.62,
      interactive: false
    }).addTo(map);

    var umbraDot = L.circleMarker(frames[0].c, {
      pane: 'umbra',
      radius: 2.6,
      color: '#ffd24a',
      weight: 1.4,
      fillColor: '#ffd24a',
      fillOpacity: 1,
      interactive: false
    }).addTo(map);

    // -- observing sites ---------------------------------------------------

    var siteMarkers = {};
    (data.markers || []).forEach(function (m) {
      siteMarkers[m.name] = L.marker([m.lat, m.lon], {
        icon: L.divIcon({ className: 'site-dot', iconSize: [11, 11] }),
        title: m.name
      }).addTo(map).bindPopup(popupHtml(m), { maxWidth: 300 });
    });

    // -- initial view ------------------------------------------------------

    map.fitBounds(L.latLngBounds(north.concat(south)), {
      padding: [30, 90], animate: false
    });

    // -- clock, slider, playback ------------------------------------------

    var elPlay = document.getElementById('play');
    var elSpeed = document.getElementById('speed');
    var elJump = document.getElementById('jump');
    var elSlider = document.getElementById('slider');
    var elTime = document.getElementById('clock-time');
    var elDate = document.getElementById('clock-date');
    var titleMax = document.getElementById('title-max');

    var d = new Date(data.meta.date + 'T00:00:00Z');
    elDate.textContent = 'UTC · ' + d.getUTCDate() + ' ' + MONTHS[d.getUTCMonth()];
    titleMax.textContent = 'kesto keskilinjalla enintään ' +
                           mmss(data.meta.max_duration_s);

    elSlider.min = t0;
    elSlider.max = t1;
    elSlider.step = 1;

    var now = t0;
    var speedIdx = 2;
    var playing = false;
    var last = 0;

    function setTime(t, fromSlider) {
      now = Math.min(t1, Math.max(t0, t));
      var x = (now - t0) / stepS;
      var i = Math.min(frames.length - 2, Math.max(0, Math.floor(x)));
      var f = Math.min(1, Math.max(0, x - i));
      var a = frames[i], b = frames[i + 1];

      // Vertices are stored at the same fixed bearings in every frame, so a
      // straight vertex-by-vertex blend keeps the outline well behaved.
      var ring = new Array(a.poly.length);
      for (var k = 0; k < a.poly.length; k++) {
        ring[k] = [a.poly[k][0] + (b.poly[k][0] - a.poly[k][0]) * f,
                   a.poly[k][1] + (b.poly[k][1] - a.poly[k][1]) * f];
      }
      umbra.setLatLngs([ring]);
      umbraDot.setLatLng([a.c[0] + (b.c[0] - a.c[0]) * f,
                          a.c[1] + (b.c[1] - a.c[1]) * f]);

      elTime.textContent = hms(now);
      if (!fromSlider) elSlider.value = now;
      elSlider.style.setProperty('--fill', ((now - t0) / (t1 - t0) * 100) + '%');
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

    elPlay.onclick = function () { setPlaying(!playing); };

    elSpeed.onclick = function () {
      speedIdx = (speedIdx + 1) % SPEEDS.length;
      elSpeed.innerHTML = SPEEDS[speedIdx] + '&times;';
    };

    elJump.onclick = function () {
      var best = 0, bestD = -1;
      for (var i = 0; i < centre.length; i++) {
        if (centre[i][3] > bestD) { bestD = centre[i][3]; best = i; }
      }
      setTime(t0 + best * stepS);
      map.setView([centre[best][0], centre[best][1]], Math.max(map.getZoom(), 5));
    };

    elSlider.oninput = function () {
      setPlaying(false);
      setTime(parseFloat(elSlider.value), true);
    };

    document.addEventListener('keydown', function (e) {
      if (e.target.tagName === 'INPUT' && e.key !== ' ') return;
      if (e.key === ' ') { e.preventDefault(); setPlaying(!playing); }
      else if (e.key === 'ArrowRight') { setPlaying(false); setTime(now + stepS); }
      else if (e.key === 'ArrowLeft') { setPlaying(false); setTime(now - stepS); }
    });

    setTime(t0);
    setPlaying(true);

    // Small handle for scripted checks and for poking at the map from a console.
    window.eclipse = { map: map, data: data, setTime: setTime, setPlaying: setPlaying,
                       markers: siteMarkers };
  }

  // -- popup ---------------------------------------------------------------

  function popupHtml(m) {
    var off = (m.tz_offset_h || 0) * 3600;
    var tz = m.tz_name || 'UTC';
    var rows = '';

    function row(label, sec) {
      if (sec === undefined) return;
      rows += '<tr><td>' + label + '</td><td>' + hms(sec) + ' UTC &nbsp;·&nbsp; ' +
              hm(sec + off) + ' ' + tz + '</td></tr>';
    }

    var head;
    if (m.duration) {
      head = '<div class="big">' + mmss(m.duration) + ' totaliteettia</div>';
    } else {
      head = '<div class="big">' +
             Math.round((m.max_obscuration || 0) * 100) + ' % osittainen</div>';
    }

    row('Osittainen alkaa', m.partial_start);
    row('Totaliteetti alkaa', m.total_start);
    row('Totaliteetti päättyy', m.total_end);
    row('Osittainen päättyy', m.partial_end);

    return '<h3>' + m.name + '</h3>' + head +
           '<table>' + rows + '</table>' +
           '<p class="foot">' + m.lat.toFixed(4) + '°N, ' +
           Math.abs(m.lon).toFixed(4) + '°' + (m.lon < 0 ? 'W' : 'E') + '</p>';
  }
})();
