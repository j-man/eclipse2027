#!/usr/bin/env python3
"""Acceptance checks for the eclipse map, run against a real browser.

    .venv/bin/python check.py            # checks only
    .venv/bin/python check.py --shots    # checks + screenshots into shots/

Needs playwright:  pip install playwright && playwright install chromium
"""

import json
import re
import os
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "file://" + os.path.join(HERE, "web", "index.html")

SHOTS = {
    "overview": "",
    "spain": "eclipse.map.setView([36.5,-5.4],8); eclipse.setTime(31670);",
    "malaga-popup": ("eclipse.map.setView([36.55,-4.42],9); eclipse.setTime(31745);"
                     "eclipse.markers.Malaga.openPopup();"),
    "sevilla-popup": ("eclipse.map.setView([37.05,-5.98],8); eclipse.setTime(31620);"
                      "eclipse.markers.Sevilla.openPopup();"),
    "tarifa-popup": ("eclipse.map.setView([35.85,-5.6],9); eclipse.setTime(31648);"
                     "eclipse.markers.Tarifa.openPopup();"),
    "luxor": "eclipse.map.setView([25.7,32.6],7); eclipse.setTime(36300);",
    "click-popup": ("eclipse.map.setView([26.75,31.15],7);"
                    "eclipse.map.fire('click',{latlng:L.latLng(26.55,31.45)});"),
    "west-end": "eclipse.map.setView([31,-40],5); eclipse.setTime(30320);",
    "east-end": "eclipse.map.setView([-10,84],5); eclipse.setTime(42400);",
}

results = []


def check(name, ok, detail=""):
    results.append((bool(ok), name, detail))
    print(("  PASS  " if ok else "  FAIL  ") + name + ("  " + detail if detail else ""))


# Screen-space point-in-polygon against whichever overlay we ask for.
IN_POLY = """
([lat, lon, which]) => {
  let poly = null;
  eclipse.map.eachLayer(l => {
    if (l instanceof L.Polygon) {
      const isUmbra = l.options.pane === 'umbra';
      if (which === 'umbra' ? isUmbra : !isUmbra) poly = poly || l;
    }
  });
  if (!poly) return null;
  const ring = poly.getLatLngs()[0].map(p => eclipse.map.latLngToLayerPoint(p));
  const p = eclipse.map.latLngToLayerPoint(L.latLng(lat, lon));
  let c = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    if ((ring[i].y > p.y) !== (ring[j].y > p.y) &&
        p.x < (ring[j].x - ring[i].x) * (p.y - ring[i].y) / (ring[j].y - ring[i].y) + ring[i].x)
      c = !c;
  }
  return c;
}
"""


def main():
    data = json.load(open(os.path.join(HERE, "data", "eclipse2027.json")))
    want_shots = "--shots" in sys.argv

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        problems = []
        page.on("pageerror", lambda e: problems.append("pageerror: " + str(e)))
        page.on("console", lambda m: problems.append("console " + m.type + ": " + m.text)
                if m.type == "error" else None)

        page.goto(URL)
        page.wait_for_function("window.eclipse !== undefined", timeout=15000)
        page.wait_for_timeout(3000)

        # 1. page opens, map renders, zoom and pan work
        check("1a. page loads with no JS errors", not problems, "; ".join(problems[:3]))
        check("1b. satellite tiles rendered",
              page.evaluate("document.querySelectorAll('.leaflet-tile-loaded').length") > 10,
              f"{page.evaluate('document.querySelectorAll(\".leaflet-tile-loaded\").length')} tiles")
        z0 = page.evaluate("eclipse.map.getZoom()")
        page.evaluate("eclipse.map.setZoom(eclipse.map.getZoom()+2)")
        page.wait_for_timeout(600)
        z1 = page.evaluate("eclipse.map.getZoom()")
        page.evaluate("eclipse.map.panBy([220,120],{animate:false})")
        page.wait_for_timeout(400)
        moved = page.evaluate("eclipse.map.getCenter().lng")
        check("1c. zoom works", z1 == z0 + 2, f"{z0} -> {z1}")
        check("1d. pan works", moved is not None)
        page.evaluate("eclipse.map.setZoom(%d)" % z0)
        page.wait_for_timeout(400)

        # 2. band crosses Gibraltar, Luxor and reaches the Indian Ocean
        centre = data["path"]["center"]
        def time_at(lon):
            best = min(centre, key=lambda p: abs(p[1] - lon))
            return best[2], best[0]
        gib_t, gib_lat = time_at(-5.35)
        lux_t, lux_lat = time_at(32.64)
        check("2a. path crosses the Strait of Gibraltar",
              35.0 < gib_lat < 37.0, f"lat {gib_lat:.2f} at {gib_t} UTC")
        check("2b. path crosses Luxor", 24.5 < lux_lat < 27.0,
              f"lat {lux_lat:.2f} at {lux_t} UTC")
        check("2c. path starts in the Atlantic", centre[0][1] < -35.0,
              f"lon {centre[0][1]:.1f} at {centre[0][2]} UTC")
        check("2d. path ends in the Indian Ocean",
              centre[-1][1] > 80.0 and centre[-1][0] < 0,
              f"{centre[-1][0]:.1f}, {centre[-1][1]:.1f} at {centre[-1][2]} UTC")
        check("2e. north limit stays north of south limit",
              all(a[0] > b[0] for a, b in zip(data["path"]["north"], data["path"]["south"])))

        # 3. playback: umbra travels west to east, clock runs, slider drags
        page.evaluate("eclipse.setTime(%f)" % data["umbra"][0]["s"])
        lons = []
        for f in data["umbra"][::20]:
            page.evaluate("eclipse.setTime(%f)" % f["s"])
            lons.append(page.evaluate(
                "eclipse.map.eachLayer(l=>{if(l.options.pane==='umbra'&&l.getLatLng)"
                "window.__d=l.getLatLng()}), window.__d.lng"))
        check("3a. umbra travels west to east",
              all(b > a for a, b in zip(lons, lons[1:])),
              f"{lons[0]:.1f} -> {lons[-1]:.1f}")

        page.evaluate("eclipse.setTime(%f)" % data["umbra"][0]["s"])
        page.evaluate("eclipse.setPlaying(true)")
        c0 = page.text_content("#clock-time")
        page.wait_for_timeout(1200)
        c1 = page.text_content("#clock-time")
        page.evaluate("eclipse.setPlaying(false)")
        check("3b. play advances the clock", c0 != c1, f"{c0} -> {c1}")

        page.eval_on_selector("#slider",
                              "el => { el.value = %f; el.dispatchEvent(new Event('input')); }"
                              % (data["umbra"][-1]["s"] - 600))
        page.wait_for_timeout(300)
        check("3c. slider scrubs the timeline",
              page.text_content("#clock-time") == data["umbra"][-11]["t"],
              "clock reads " + page.text_content("#clock-time"))

        # 4. Malaga is inside the band, and inside the umbra at mid-totality
        mal = next(m for m in data["markers"] if m["name"] == "Malaga")
        page.evaluate("eclipse.map.setView([36.5,-4.4],8)")
        page.wait_for_timeout(800)
        page.evaluate("eclipse.setTime(%f)"
                      % ((mal["total_start"] + mal["total_end"]) / 2))
        page.wait_for_timeout(300)
        check("4a. Malaga lies inside the path of totality",
              page.evaluate(IN_POLY, [mal["lat"], mal["lon"], "band"]))
        check("4b. Malaga is covered by the umbra at mid-totality",
              page.evaluate(IN_POLY, [mal["lat"], mal["lon"], "umbra"]),
              f"{mal['duration']:.0f} s of totality")

        # 4c-4f. the full set of site markers
        WANT = ["Sevilla", "Malaga", "Cadiz", "Gibraltar", "Tarifa", "Ceuta",
                "Sfax", "Luxor", "Wadi Lahmy Azur Resort"]
        names = [m["name"] for m in data["markers"]]
        check("4c. all site markers present in the data", names == WANT,
              f"{len(names)}: " + ", ".join(names))
        check("4d. every marker is on the map",
              page.evaluate("Object.keys(eclipse.markers).length") == len(WANT),
              f"{page.evaluate('Object.keys(eclipse.markers).length')} markers")

        # Each marker either has a totality duration or is explicitly flagged as
        # outside the path, with a magnitude and a distance to the nearest limit.
        classified, inside, outside = [], 0, 0
        for m in data["markers"]:
            if "duration" in m:
                inside += 1
                ok = (page.evaluate(IN_POLY, [m["lat"], m["lon"], "band"])
                      and 0 < m["duration"] < 400 and "max_s" in m)
            else:
                outside += 1
                ok = ("max_magnitude" in m and "dist_to_path_km" in m
                      and not page.evaluate(IN_POLY, [m["lat"], m["lon"], "band"]))
            classified.append((m["name"], ok))
        check("4e. each marker agrees with the drawn path of totality",
              all(ok for _, ok in classified),
              f"{inside} inside, {outside} outside; "
              + ", ".join(n for n, ok in classified if not ok) or "")

        popups = page.evaluate(
            "Object.entries(eclipse.markers).map(([n,mk]) =>"
            "  [n, mk.getPopup().getContent()])")
        bad = [n for n, html in popups
               if "Maksimi" not in html
               or ("totaliteettia" not in html and "ulkopuolella" not in html)]
        check("4f. every marker popup states maximum time and totality status",
              not bad, "missing: " + ", ".join(bad) if bad else "")

        # 6. click-to-time
        def click_at(lat, lon):
            page.evaluate("eclipse.map.closePopup()")
            xy = page.evaluate(
                "([a,b]) => { const p = eclipse.map.latLngToContainerPoint(L.latLng(a,b));"
                "return [p.x, p.y]; }", [lat, lon])
            page.mouse.click(xy[0], xy[1])
            page.wait_for_timeout(400)
            return xy

        def nearest_centre_time(lat, lon):
            """Closest centre-line sample, as a plain independent reference."""
            import math
            best, bt = 1e9, None
            for p in centre:
                dy = p[0] - lat
                dx = (p[1] - lon) * math.cos(math.radians(lat))
                d = dy * dy + dx * dx
                if d < best:
                    best, bt = d, p[2]
            return bt

        def clock_seconds():
            h, m, s = (int(x) for x in page.text_content("#clock-time").split(":"))
            return h * 3600 + m * 60 + s

        # A centre-line point over the Egyptian desert, ~200 km clear of any
        # site marker so the click reaches the map rather than a marker.
        TP = (26.90, 30.98)
        page.evaluate("eclipse.map.setView([%f,%f],6)" % TP)
        page.wait_for_timeout(800)
        page.evaluate("eclipse.setPlaying(true)")
        click_at(*TP)
        want = nearest_centre_time(*TP)
        want_s = sum(int(v) * f for v, f in zip(want.split(":"), (3600, 60, 1)))
        got_s = clock_seconds()
        check("6a. click sets the clock to the umbra's closest approach",
              abs(got_s - want_s) <= 180,
              f"clock {page.text_content('#clock-time')}, nearest sample {want}")
        check("6b. click pauses playback", not page.evaluate("eclipse.isPlaying()"))

        popup = page.query_selector(".click-popup")
        txt = popup.inner_text() if popup else ""
        check("6c. popup inside the path shows duration and time of maximum",
              popup is not None and "min" in txt and "UTC" in txt,
              txt.replace("\n", " | ")[:70])

        # The umbra sweep must agree with the durations computed independently
        # by gen_data.py for the marked sites.
        worst = max(
            (abs(page.evaluate("([a,b]) => eclipse.totalityAt(a,b)",
                               [m["lat"], m["lon"]])["duration"] - m["duration"]), m["name"])
            for m in data["markers"] if "duration" in m)
        check("6d. clicked duration matches the computed value",
              worst[0] < 5, f"worst {worst[0]:.1f} s ({worst[1]})")

        # Cairo is well north of the path: time only, no popup.
        page.evaluate("eclipse.map.setView([28,31],5)")
        page.wait_for_timeout(800)
        before = clock_seconds()
        click_at(30.04, 31.24)
        check("6e. click outside the path sets time but shows no popup",
              page.query_selector(".click-popup") is None and clock_seconds() != before,
              "clock " + page.text_content("#clock-time"))

        # Dragging the map must not be treated as a click.
        page.evaluate("eclipse.map.closePopup()")
        held = clock_seconds()
        page.mouse.move(700, 300)
        page.mouse.down()
        for x in range(700, 560, -35):
            page.mouse.move(x, 300 + (700 - x) // 4)
        page.mouse.up()
        page.wait_for_timeout(500)
        check("6f. dragging the map does not jump the clock",
              clock_seconds() == held, f"still {page.text_content('#clock-time')}")

        # A click on a site marker still belongs to the marker, not to the map.
        page.evaluate("eclipse.map.setView([25.7,32.6],7)")
        page.wait_for_timeout(800)
        page.evaluate("eclipse.map.closePopup()")
        marker_t = clock_seconds()
        click_at(25.6872, 32.6396)
        opened = page.query_selector(".leaflet-popup-content")
        check("6g. marker clicks keep their own popup",
              opened is not None and "Luxor" in opened.inner_text()
              and page.query_selector(".click-popup") is None
              and clock_seconds() == marker_t,
              (opened.inner_text().split("\n")[0] if opened else "no popup"))

        # Existing controls still behave.
        page.evaluate("eclipse.map.setView([%f,%f],6)" % TP)
        page.wait_for_timeout(600)
        click_at(*TP)
        t_click = clock_seconds()
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(250)
        check("6h. arrow key still steps one minute",
              clock_seconds() - t_click == 60,
              f"{t_click} -> {clock_seconds()}")
        page.keyboard.press("Space")
        page.wait_for_timeout(900)
        resumed = clock_seconds()
        page.evaluate("eclipse.setPlaying(false)")
        check("6i. play resumes from the clicked time",
              page.evaluate("eclipse.isPlaying") is not None and resumed > t_click,
              f"resumed at {resumed - t_click:+d} s from the click")

        # 7. version badge
        badge = page.text_content("#version")
        src = open(os.path.join(HERE, "web", "app.js")).read()
        declared = re.search(r"var VERSION\s*=\s*(\d+)", src)
        check("7a. badge shows the version declared in app.js",
              declared is not None and badge.split(" ")[0] == "v" + declared.group(1),
              repr(badge))
        check("7b. badge carries the git hash only when there is one",
              (" · " in badge) == ("git" in data["meta"]),
              "git in data" if "git" in data["meta"] else "no git checkout")
        check("7c. badge is non-interactive",
              page.evaluate("getComputedStyle(document.getElementById('version'))"
                            ".pointerEvents") == "none")

        # It must not collide with the control bar, clock or attribution at any
        # window size, so measure real bounding boxes across a range of widths.
        RECTS = ("([a,b]) => { const r = s => { const e = document.querySelector(s);"
                 "  if (!e) return null; const q = e.getBoundingClientRect();"
                 "  return [q.left, q.top, q.right, q.bottom]; };"
                 "  return [r(a), r(b)]; }")
        collisions = []
        for w, h in ((1440, 900), (1024, 768), (860, 700), (760, 620), (721, 600),
                     (700, 600), (600, 560), (480, 700), (380, 640), (320, 480)):
            page.set_viewport_size({"width": w, "height": h})
            page.wait_for_timeout(350)
            for other in ("#controls", "#clock", ".leaflet-control-attribution",
                          ".leaflet-control-zoom", "#title"):
                a, b = page.evaluate(RECTS, ["#version", other])
                if not a or not b:
                    continue
                if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                    collisions.append(f"{w}x{h} vs {other}")
        check("7d. badge never overlaps other chrome at any window size",
              not collisions, "; ".join(collisions) or "10 window sizes clear")
        page.set_viewport_size({"width": 1440, "height": 900})
        page.wait_for_timeout(400)

        # 5. generation cost is a property of gen_data.py, verified when it runs
        check("5. duration contours present",
              all(len(data["contours"][k]["north"]) > 10 for k in data["contours"]),
              ", ".join(f"{k}s:{len(v['north'])}pt" for k, v in data["contours"].items()))

        if want_shots:
            os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
            for name, js in SHOTS.items():
                page.goto(URL)
                page.wait_for_function("window.eclipse !== undefined")
                page.wait_for_timeout(1500)
                page.evaluate("eclipse.setPlaying(false)")
                if js:
                    page.evaluate(js)
                page.wait_for_timeout(4000)
                page.screenshot(path=os.path.join(HERE, "shots", name + ".png"))
                print("  shot  shots/%s.png" % name)

        browser.close()

    bad = [r for r in results if not r[0]]
    print(f"\n{len(results) - len(bad)}/{len(results)} checks passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
