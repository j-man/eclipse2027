/* Service worker: keeps the app's shell on the phone so the map opens on a
   weak connection, or none.

   The shell (page, scripts, styles, icons, the catalogue and the default
   eclipse) is cached when this worker installs, along with the eclipses near
   enough to plan a trip for. After that, every request for them is answered
   from the cache first. Any other eclipse is cached the first time it is
   opened. Map tiles and everything else go to the network as before.

   VERSION names the cache and must equal VERSION in app.js (check.py holds
   them together): a release changes this file, the browser notices, installs
   the new worker, and the old cache is dropped when it takes over. */

'use strict';

var VERSION = 29;
var CACHE = 'pimennykset-v' + VERSION;

// Relative to this file, which lives in web/ beside index.html.
var SHELL = [
  './',
  'index.html',
  'style.css',
  'app.js',
  'tz.js',
  'eclipse-index.js',
  'eclipse-default.js',
  'manifest.webmanifest',
  'icons/icon.svg',
  'icons/favicon-32.png',
  'icons/icon-180.png',
  'icons/icon-192.png',
  'icons/icon-512.png',
  'icons/icon-maskable-512.png'
];

// From another origin; cached if they can be had, not required to install.
var EXTRA = [
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
];

var CATALOGUE = '../data/index.json';
var ECLIPSE_DIR = '../data/eclipses/';
// The same window app.js offers first: still to come, this year plus two.
var NEAR_TERM_YEARS = 2;

function fresh(url) {
  // past the HTTP cache, so a new release never installs yesterday's files
  return new Request(new URL(url, self.location).href, { cache: 'reload' });
}

// The eclipses the page is likely to open on: still to come and within the
// near-term window, or failing that the next one at all.
function nearTerm(catalogue, today) {
  var dates = (catalogue && catalogue.eclipses || [])
    .map(function (e) { return e.date; }).filter(Boolean).sort();
  var lastYear = parseInt(today.slice(0, 4), 10) + NEAR_TERM_YEARS;
  var near = dates.filter(function (d) {
    return d >= today && parseInt(d.slice(0, 4), 10) <= lastYear;
  });
  if (!near.length) {
    var next = dates.filter(function (d) { return d >= today; })[0] || dates[dates.length - 1];
    if (next) near = [next];
  }
  return near.map(function (d) { return ECLIPSE_DIR + d + '.js'; });
}

function bestEffort(cache, urls) {
  return Promise.all(urls.map(function (url) {
    return fetch(fresh(url)).then(function (response) {
      if (response.ok) return cache.put(new URL(url, self.location).href, response);
    }).catch(function () {});
  }));
}

self.addEventListener('install', function (event) {
  event.waitUntil(caches.open(CACHE).then(function (cache) {
    return cache.addAll(SHELL.map(fresh)).then(function () {
      var today = new Date().toISOString().slice(0, 10);
      return fetch(fresh(CATALOGUE))
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; })
        .then(function (catalogue) {
          return bestEffort(cache, EXTRA.concat(nearTerm(catalogue, today)));
        });
    });
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (event) {
  event.waitUntil(caches.keys().then(function (names) {
    return Promise.all(names.filter(function (name) {
      return name.indexOf('pimennykset-') === 0 && name !== CACHE;
    }).map(function (name) { return caches.delete(name); }));
  }).then(function () { return self.clients.claim(); }));
});

// Which requests this worker answers at all: its own origin's files, and the
// two Leaflet files. Tiles and anything else are left to the network.
function ours(url) {
  return url.origin === self.location.origin || EXTRA.indexOf(url.href) >= 0;
}

function isEclipse(url) {
  return url.origin === self.location.origin &&
    url.pathname.indexOf('/data/eclipses/') >= 0 && /\.js$/.test(url.pathname);
}

self.addEventListener('fetch', function (event) {
  var request = event.request;
  if (request.method !== 'GET') return;
  var url = new URL(request.url);
  if (!ours(url)) return;
  event.respondWith(caches.open(CACHE).then(function (cache) {
    var key = request.mode === 'navigate' ? new URL('index.html', self.location).href : request;
    return cache.match(key, { ignoreSearch: request.mode === 'navigate' }).then(function (hit) {
      if (hit) return hit;
      return fetch(request).then(function (response) {
        // an eclipse opened for the first time is kept for next time
        if (response.ok && isEclipse(url)) cache.put(request, response.clone());
        return response;
      });
    });
  }));
});
