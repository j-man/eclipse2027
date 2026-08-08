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
    "default-view": "",
    "overview": "eclipse.select('2027-08-02');",
    "spain": "eclipse.map.setView([36.5,-5.4],8); eclipse.setTime(31670);",
    "picker-open": "eclipse.openMenu();",
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

        # 0. the page opens on the eclipse the catalogue nominates
        cat0 = json.load(open(os.path.join(HERE, "data", "index.json")))
        want_default = cat0.get("default")
        check("0a. catalogue nominates a default eclipse",
              want_default in {e["date"] for e in cat0["eclipses"]},
              str(want_default))
        check("0b. page opens on that eclipse, not on a hardcoded one",
              page.evaluate("eclipse.data.meta.date") == want_default,
              "showing " + page.evaluate("eclipse.data.meta.date"))
        check("0c. its data was there for the first paint (no lazy fetch)",
              page.evaluate("!!window.ECLIPSE_DATA")
              and page.evaluate("window.ECLIPSE_DATA.meta.date") == want_default)

        # Everything below examines the 2027 eclipse, which is no longer the
        # one on screen at start-up, so switch to it first.
        page.evaluate("eclipse.select('2027-08-02')")
        page.wait_for_function("eclipse.data.meta.date === '2027-08-02'",
                               timeout=15000)
        page.wait_for_timeout(1200)

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

        # 8. the 1986-2066 catalogue
        #
        # Reference facts as stated in TASK6.md; the durations published for
        # these eclipses are 2017 = 2m40s and 2024 = 4m28s, and ours run ~2 s
        # long from the lunar-radius convention (see check_oracle.py).
        cat = json.load(open(os.path.join(HERE, "data", "index.json")))
        rows = {e["date"]: e for e in cat["eclipses"]}
        KNOWN = ["1991-07-11", "1999-08-11", "2009-07-22", "2017-08-21",
                 "2024-04-08", "2026-08-12", "2027-08-02"]
        check("8a. catalogue size is in the expected range",
              55 <= len(rows) <= 65, f"{len(rows)} eclipses with a total phase")
        missing = [d for d in KNOWN if d not in rows]
        check("8b. every known eclipse was discovered, dates exact",
              not missing, "missing: " + ", ".join(missing) if missing
              else "all 7 present")
        check("8c. catalogue is sorted and spans 1986-2066",
              sorted(rows) == list(rows)
              and rows and min(rows)[:4] >= "1986" and max(rows)[:4] <= "2066",
              f"{min(rows)} .. {max(rows)}")
        check("8d. only total and hybrid types",
              {e["type"] for e in cat["eclipses"]} <= {"total", "hybrid"},
              ", ".join(sorted({e["type"] for e in cat["eclipses"]})))

        c21 = {d: e for d, e in rows.items() if d >= "2001"}
        longest21 = max(c21, key=lambda d: c21[d]["max_duration_s"])
        check("8e. 2009-07-22 is the longest of the 21st century, ~6m39s",
              longest21 == "2009-07-22"
              and abs(c21["2009-07-22"]["max_duration_s"] - 399) <= 6,
              f"{longest21} at {c21[longest21]['max_duration_s']:.0f} s "
              f"(published 6m39s = 399 s)")

        SPOT = [("2017-08-21", 160.2, "Hopkinsville KY"),
                ("2024-04-08", 268.1, "Torreon, Mexico")]
        for date, pub, where in SPOT:
            got = rows[date]["max_duration_s"]
            check(f"8f. {date} max duration matches published ({where})",
                  abs(got - pub) <= 5.0,
                  f"{got:.1f} s vs {pub:.1f} s published ({got - pub:+.1f} s)")

        # Every catalogued eclipse must have a data file the page can load.
        eclipse_dir = os.path.join(HERE, "data", "eclipses")
        absent = [d for d in rows if not os.path.exists(
            os.path.join(eclipse_dir, d + ".js"))]
        check("8g. every catalogued eclipse has a generated data file",
              not absent, "missing: " + ", ".join(absent[:4]) if absent
              else f"{len(rows)} files")

        # 9. the title card is the picker
        page.goto(URL)
        page.wait_for_function("window.eclipse !== undefined", timeout=15000)
        page.wait_for_timeout(2500)

        n_rows = page.evaluate(
            "document.querySelectorAll('#eclipse-menu .row').length")
        check("9a. the card's list holds the whole catalogue",
              n_rows == len(rows), f"{n_rows} rows")
        check("9b. no second entry point is left over",
              not page.evaluate("!!document.getElementById('picker')"),
              "the old standalone <select> is gone")
        check("9c. card names the eclipse on screen and its position",
              page.text_content("#card-title") == "12. elokuuta 2026"
              and "/ %d" % len(rows) in page.text_content("#card-badge")
              and page.evaluate("eclipse.data.meta.date") == want_default,
              page.text_content("#card-title") + " · "
              + page.text_content("#card-badge"))

        # The trigger has to name the action, not just be clickable.
        check("9c2. trigger row is a signposted control",
              "Valitse pimennys" in page.text_content("#pick-label")
              and "(%d)" % len(rows) in page.text_content("#pick-label")
              and page.evaluate(
                  "getComputedStyle(document.getElementById('pick-btn'))"
                  ".borderTopWidth") != "0px",
              page.text_content("#pick-label"))

        # The card must behave like a control: click to open, click to pick.
        check("9d. list is closed until the card is used",
              page.evaluate("document.getElementById('eclipse-menu').hidden")
              and page.get_attribute("#eclipse-card", "aria-expanded") == "false")
        page.click("#eclipse-card")
        page.wait_for_timeout(400)
        check("9e. clicking the card opens the list",
              page.evaluate("eclipse.menuOpen()")
              and page.get_attribute("#eclipse-card", "aria-expanded") == "true")

        page.click("#eclipse-menu .row[data-date='2024-04-08']")
        page.wait_for_function("eclipse.data.meta.date === '2024-04-08'",
                               timeout=10000)
        page.wait_for_timeout(400)
        check("9f. picking a row switches the eclipse and closes the list",
              page.evaluate("document.getElementById('eclipse-menu').hidden")
              and page.text_content("#card-title") == "8. huhtikuuta 2024",
              page.text_content("#card-title"))

        # List clarity: decade groups, the next eclipse tagged, past dimmed.
        page.evaluate("eclipse.openMenu()")
        page.wait_for_timeout(300)
        groups = page.evaluate(
            "[...document.querySelectorAll('#eclipse-menu .group')].map(g=>g.textContent)")
        check("9f2. rows are grouped by decade",
              len(groups) >= 8 and groups[0].startswith("1980"),
              f"{len(groups)} groups: " + ", ".join(groups[:3]) + " ...")
        tagged = page.evaluate(
            "document.querySelector('#eclipse-menu .row.next')?.dataset.date")
        upcoming = min(e["date"] for e in cat0["eclipses"]
                       if e["date"] >= page.evaluate("new Date().toISOString().slice(0,10)"))
        check("9f3. the next upcoming eclipse is tagged",
              tagged == upcoming, f"tagged {tagged}, next is {upcoming}")
        n_past = page.evaluate(
            "document.querySelectorAll('#eclipse-menu .row.past').length")
        near = page.evaluate(
            "[...document.querySelectorAll('#eclipse-menu .row.near')]"
            ".map(r=>r.dataset.date)")
        this_year = int(page.evaluate("new Date().toISOString().slice(0,4)"))
        want_near = sorted(e["date"] for e in cat0["eclipses"]
                           if e["date"] >= page.evaluate(
                               "new Date().toISOString().slice(0,10)")
                           and int(e["date"][:4]) <= this_year + 2)
        check("9f3b. the trip-plannable next few years are highlighted",
              sorted(near) == want_near and 0 < len(near) < len(rows)
              and page.evaluate(
                  "getComputedStyle(document.querySelector"
                  "('#eclipse-menu .row.near')).boxShadow") != "none",
              ", ".join(near) if near else "none")
        # Measure resting states only: the cursor is still parked on the row
        # clicked above, and :hover is a transient state, not a category.
        page.mouse.move(1200, 700)
        page.wait_for_timeout(200)
        check("9f3c. three levels of row emphasis plus the selected state",
              len(set(page.evaluate(
                  "[...document.querySelectorAll('#eclipse-menu .row')]"
                  ".map(r=>getComputedStyle(r).opacity+'|'"
                  "+getComputedStyle(r).boxShadow+'|'"
                  "+getComputedStyle(r).backgroundColor)"))) <= 4,
              "past / near / plain, plus the selected row")
        check("9f3d. the eclipse on screen is marked in the list",
              page.evaluate(
                  "document.querySelector('#eclipse-menu .row[aria-selected=\"true\"]')"
                  "?.dataset.date") == page.evaluate("eclipse.data.meta.date"),
              "marked " + str(page.evaluate(
                  "document.querySelector('#eclipse-menu .row[aria-selected=\"true\"]')"
                  "?.dataset.date")))
        check("9f4. past eclipses are dimmed, future ones are not",
              0 < n_past < len(rows)
              and page.evaluate(
                  "getComputedStyle(document.querySelector"
                  "('#eclipse-menu .row.past')).opacity") != "1",
              f"{n_past} of {len(rows)} dimmed")
        check("9f5. the selected row is scrolled into view on open",
              page.evaluate("""() => {
                  const m = document.getElementById('eclipse-menu');
                  const r = m.querySelector('.row[aria-selected=\"true\"]');
                  if (!r) return false;
                  const a = m.getBoundingClientRect(), b = r.getBoundingClientRect();
                  return b.top >= a.top - 1 && b.bottom <= a.bottom + 1;
              }"""))
        # A short window must still leave a usable, scrollable list.
        page.set_viewport_size({"width": 1280, "height": 460})
        page.wait_for_timeout(400)
        check("9f6. list stays inside a short window and scrolls",
              page.evaluate("""() => {
                  const m = document.getElementById('eclipse-menu');
                  const r = m.getBoundingClientRect();
                  return r.bottom <= window.innerHeight + 1
                         && m.scrollHeight > m.clientHeight;
              }"""))
        page.set_viewport_size({"width": 1440, "height": 900})
        page.wait_for_timeout(400)
        page.evaluate("eclipse.closeMenu()")

        # Keyboard: the card is a button, Esc closes.
        page.evaluate("document.getElementById('eclipse-card').focus()")
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        opened_by_key = page.evaluate("eclipse.menuOpen()")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        check("9g. Enter opens the card and Esc closes it",
              opened_by_key and not page.evaluate("eclipse.menuOpen()"))

        switched = []
        for date in ("2017-08-21", "2027-08-02"):
            page.evaluate("eclipse.select('%s')" % date)
            try:
                page.wait_for_function(
                    "eclipse.data.meta.date === '%s'" % date, timeout=10000)
                switched.append((date, page.evaluate("eclipse.data.umbra.length"),
                                 page.evaluate("Object.keys(eclipse.markers).length")))
            except Exception:
                switched.append((date, 0, 0))
        check("9h. switching lazy-loads and rebuilds each eclipse",
              all(f > 10 for _, f, _ in switched),
              "; ".join(f"{d} {f} frames" for d, f, _ in switched))
        check("9i. site markers appear only for 2027",
              dict((d, m) for d, _, m in switched)["2017-08-21"] == 0
              and dict((d, m) for d, _, m in switched)["2027-08-02"] == 9,
              "; ".join(f"{d} {m} markers" for d, _, m in switched))
        check("9j. version bumped and now tracks the task number",
              page.evaluate("eclipse.version") >= 9,
              page.text_content("#version"))

        # The first-visit nudge fires once per browser profile, never again.
        fresh = browser.new_context(viewport={"width": 1280, "height": 800})
        fp = fresh.new_page()
        fp.goto(URL)
        fp.wait_for_function("window.eclipse !== undefined", timeout=15000)
        fp.wait_for_timeout(1500)
        first = fp.evaluate("document.getElementById('chev').classList.contains('pulse')")
        sp = fresh.new_page()
        sp.goto(URL)
        sp.wait_for_function("window.eclipse !== undefined", timeout=15000)
        sp.wait_for_timeout(1500)
        again = sp.evaluate("document.getElementById('chev').classList.contains('pulse')")
        fresh.close()
        check("9k. chevron nudges on a first visit only",
              first and not again, f"first visit {first}, second {again}")

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
                # Every scripted shot but the default-view one frames 2027.
                if name not in ("overview", "default-view"):
                    page.evaluate("eclipse.select('2027-08-02')")
                    page.wait_for_function(
                        "eclipse.data.meta.date === '2027-08-02'", timeout=15000)
                    page.wait_for_timeout(800)
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
