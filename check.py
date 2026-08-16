#!/usr/bin/env python3
"""Acceptance checks for the eclipse map, run against a real browser.

    .venv/bin/python check.py            # checks only
    .venv/bin/python check.py --shots    # checks + screenshots into shots/

Needs playwright:  pip install playwright && playwright install chromium
"""

import json
import math
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
    # A polar track that crosses the antimeridian: the limits and the duration
    # contours here used to be thrown thousands of kilometres off the path by
    # the terminus solver, drawing a wedge from the Arctic down to Mongolia.
    "alaska-2033": "eclipse.select('2033-03-30');",
    # A hybrid: amber dashed annular ends either side of the total section.
    "hybrid-2050": "eclipse.select('2050-05-20');",
}

results = []


def check(name, ok, detail=""):
    results.append((bool(ok), name, detail))
    print(("  PASS  " if ok else "  FAIL  ") + name + ("  " + detail if detail else ""))


def hms(sec):
    """Seconds of day as the page prints them: round half up, then wrap a day.

    Half-up rather than Python's half-even, because the number being reproduced
    is the one JavaScript's Math.round produced.
    """
    s = int(math.floor(sec + 0.5)) % 86400
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def secs(txt):
    h, m, s = (int(x) for x in txt.split(":"))
    return h * 3600 + m * 60 + s


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
        # The viewer's own zone is part of what the page shows now, so it is
        # pinned rather than inherited from whatever machine runs the tests.
        # Helsinki is an hour off both Spain and Egypt on the eclipse dates,
        # which is what makes the viewer column visible and checkable.
        page = browser.new_page(viewport={"width": 1440, "height": 900},
                                timezone_id="Europe/Helsinki")
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
        # The big reading follows the place last clicked, so the timeline is
        # read off #clock-utc, which is UTC whatever place is selected.
        check("3c. slider scrubs the timeline",
              page.text_content("#clock-utc") == data["umbra"][-11]["t"],
              "clock reads " + page.text_content("#clock-utc"))
        check("3d. with no place picked the clock is plain UTC",
              page.text_content("#clock-time") == data["umbra"][-11]["t"]
              and page.text_content("#clock-zone") == "UTC",
              page.text_content("#clock-time") + " "
              + page.text_content("#clock-zone"))

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
            best, bt = 1e9, None
            for p in centre:
                dy = p[0] - lat
                dx = (p[1] - lon) * math.cos(math.radians(lat))
                d = dy * dy + dx * dx
                if d < best:
                    best, bt = d, p[2]
            return bt

        def clock_seconds():
            """The clock's UTC reading, whichever place's zone is on show."""
            h, m, s = (int(x) for x in page.text_content("#clock-utc").split(":"))
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

        # Cairo is well north of the 2027 path: no totality, but a large
        # partial eclipse, which is what the click must now report. (Before,
        # a click outside the path moved the clock and said nothing, which is
        # exactly the complaint this behaviour answers.)
        page.evaluate("eclipse.map.setView([28,31],5)")
        page.wait_for_timeout(800)
        before = clock_seconds()
        click_at(30.04, 31.24)
        cairo = page.query_selector(".click-popup")
        cairo_text = " ".join(cairo.inner_text().split()) if cairo else ""
        check("6e. a click outside the path sets the time and reports the partial",
              cairo is not None and clock_seconds() != before
              and "OSITTAINEN" in cairo_text.upper() and "%" in cairo_text,
              (cairo_text[:80] or "no popup") + " · clock " + page.text_content("#clock-time"))

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

        # 10. local wall-clock time of the place, not of the viewer's browser
        #
        # No offset is ever stored. The page carries an IANA zone name and asks
        # the browser's own tz database what that zone is on at the eclipse's
        # instant, so summer time follows the eclipse's date and not today's.
        page.evaluate("eclipse.select('2027-08-02')")
        page.wait_for_function("eclipse.data.meta.date === '2027-08-02'",
                               timeout=15000)
        page.wait_for_timeout(900)

        WANT_TZ = {"Sevilla": "Europe/Madrid", "Malaga": "Europe/Madrid",
                   "Cadiz": "Europe/Madrid", "Gibraltar": "Europe/Gibraltar",
                   "Tarifa": "Europe/Madrid", "Ceuta": "Africa/Ceuta",
                   "Sfax": "Africa/Tunis", "Luxor": "Africa/Cairo",
                   "Wadi Lahmy Azur Resort": "Africa/Cairo"}
        got_tz = {m["name"]: m.get("tz") for m in data["markers"]}
        check("10a. every marked site carries an explicit IANA zone",
              got_tz == WANT_TZ,
              ", ".join(f"{n}={v}" for n, v in got_tz.items() if WANT_TZ.get(n) != v)
              or f"{len(got_tz)} sites")
        stale = [m["name"] for m in data["markers"]
                 if "tz_offset_h" in m or "tz_name" in m]
        check("10b. no fixed offset survives in the stored data",
              not stale, "; ".join(stale) or "zone names only, times still UTC")

        tarifa = next(m for m in data["markers"] if m["name"] == "Tarifa")
        st = page.evaluate("([z, s]) => eclipse.stampFor(z, s)",
                           ["Europe/Madrid", tarifa["total_start"]])
        check("10c. Tarifa reads as CEST, exactly UTC+2 on 2027-08-02",
              st["exact"] and st["offset"] == 7200 and st["label"] == "UTC+2"
              and st["abbr"] == "CEST" and st["dayShift"] == 0
              and hms(st["localSec"]) == hms(tarifa["total_start"] + 7200),
              f"totality from {hms(st['localSec'])} {st['label']} "
              f"({st['abbr']}) = {hms(tarifa['total_start'])} UTC")

        # TASK10 expects UTC+2 at Luxor on the grounds that Egypt keeps no
        # summer time. It has kept it again since 2023, and the tz database puts
        # 2027-08-02 inside EEST, so the DST-correct answer is UTC+3; asserting
        # +2 would be pinning a rule that has already changed. What the page
        # must never do is disagree with the database it is reading, so that is
        # the check, with today's answer pinned next to it.
        luxor = next(m for m in data["markers"] if m["name"] == "Luxor")
        st = page.evaluate("([z, s]) => eclipse.stampFor(z, s)",
                           ["Africa/Cairo", luxor["max_s"]])
        db = page.evaluate("""() => new Intl.DateTimeFormat('en-GB', {
              timeZone: 'Africa/Cairo', timeZoneName: 'longOffset' })
            .formatToParts(new Date(Date.UTC(2027, 7, 2, 10, 5, 19)))
            .find(p => p.type === 'timeZoneName').value""")
        check("10d. Luxor follows Africa/Cairo as the tz database has it",
              st["exact"] and st["zone"] == "Africa/Cairo"
              and st["offset"] == int(db[3:6]) * 3600 and st["offset"] == 10800,
              f"{st['label']}, database says {db} — Egypt has had summer time "
              f"again since 2023, so the eclipse date is EEST, not UTC+2")

        # Iceland: same mechanism, a zone that happens to sit on UTC in August.
        page.evaluate("eclipse.select('2026-08-12')")
        page.wait_for_function("eclipse.data.meta.date === '2026-08-12'",
                               timeout=15000)
        page.wait_for_timeout(900)
        st = page.evaluate("() => eclipse.stampAt(64.146, -21.94)")
        check("10e. a point in Iceland resolves to Atlantic/Reykjavik, UTC+0",
              st["zone"] == "Atlantic/Reykjavik" and st["exact"]
              and st["offset"] == 0 and st["label"] == "UTC+0",
              f"{st['zone']} {st['label']}")

        page.evaluate("eclipse.map.setView([64.146,-21.94],7)")
        page.wait_for_timeout(800)
        click_at(64.146, -21.94)
        check("10f. clicking there leaves local and UTC identical, both labelled",
              page.text_content("#clock-zone") == "UTC+0"
              and page.text_content("#clock-time") == page.text_content("#clock-utc"),
              page.text_content("#clock-time") + " "
              + page.text_content("#clock-zone") + " · "
              + page.text_content("#clock-utc") + " UTC")

        # Back to 2027, and a click on the Spanish coast clear of every marker.
        page.evaluate("eclipse.select('2027-08-02')")
        page.wait_for_function("eclipse.data.meta.date === '2027-08-02'",
                               timeout=15000)
        page.wait_for_timeout(900)
        page.evaluate("eclipse.map.setView([36.20,-5.85],8)")
        page.wait_for_timeout(800)
        click_at(36.20, -5.85)
        loc, utc = (page.text_content("#clock-time"),
                    page.text_content("#clock-utc"))
        check("10g. a click in Spain puts the clock on CEST, UTC beside it",
              page.text_content("#clock-zone") == "UTC+2"
              and secs(loc) - secs(utc) == 7200,
              f"{loc} (UTC+2) — {utc} UTC")
        pop = page.query_selector(".click-popup")
        txt = " ".join((pop.inner_text() if pop else "").split())
        # Place, viewer, UTC in that order; the place column is CEST, so it runs
        # two hours ahead of the UTC column on the same row.
        got = re.search(r"MAKSIMI (\d\d:\d\d:\d\d) (\d\d:\d\d:\d\d) "
                        r"(\d\d:\d\d:\d\d)", txt, re.I)
        check("10h. the popup leads with local time and names the zone",
              got is not None and "UTC+2" in txt and "Europe/Madrid" in txt
              and secs(got.group(1)) - secs(got.group(3)) == 7200,
              txt[:96])

        # Off the coast of Africa there is no zone to name, so the offset comes
        # from the longitude and must wear a tilde.
        st = page.evaluate("() => eclipse.stampAt(31.0, -40.0)")
        check("10i. mid-Atlantic falls back to a longitude estimate",
              st["zone"] is None and not st["exact"]
              and st["offset"] == -3 * 3600 and st["label"].startswith("~UTC"),
              st["label"])
        page.evaluate("eclipse.map.setView([31,-40],5)")
        page.wait_for_timeout(800)
        click_at(31.0, -40.0)
        check("10j. an estimated offset is never presented as exact",
              page.text_content("#clock-zone").startswith("~UTC")
              and "arvioitu" in (page.get_attribute("#clock", "title") or ""),
              page.text_content("#clock-zone") + " · "
              + str(page.get_attribute("#clock", "title")))

        popups = page.evaluate(
            "Object.entries(eclipse.markers).map(([n,mk]) =>"
            "  [n, mk.getPopup().getContent()])")
        guessed = [n for n, html in popups if "~UTC" in html]
        unnamed = [n for n, html in popups if WANT_TZ[n] not in html]
        check("10k. marked sites never guess, and each names its zone",
              not guessed and not unnamed,
              "; ".join(guessed + unnamed) or f"{len(popups)} sites")

        # Presentation only: the displayed UTC value is still exactly the
        # number gen_data.py computed, and the local one is that plus an offset.
        page.evaluate("eclipse.map.setView([25.7,32.6],7)")
        page.wait_for_timeout(800)
        before = clock_seconds()
        page.evaluate("eclipse.markers.Luxor.openPopup()")
        page.wait_for_timeout(400)
        shown = " ".join(
            page.query_selector(".leaflet-popup-content").inner_text().split())
        # Egypt and the pinned viewer zone are both +3 on this date, so the
        # viewer column is dropped and the row is just place and UTC.
        want = f"{hms(luxor['max_s'] + 10800)} {hms(luxor['max_s'])}"
        check("10l. displayed times are the stored UTC seconds, shifted to show",
              want in shown and "UTC+3" in shown
              and "SINUN" not in shown.upper(), want)
        check("10m. opening a site retunes the clock without moving the timeline",
              page.text_content("#clock-zone") == "UTC+3"
              and clock_seconds() == before
              and "Africa/Cairo" in (page.get_attribute("#clock", "title") or ""),
              page.text_content("#clock-time") + " UTC+3, timeline still at "
              + page.text_content("#clock-utc"))

        # 11. three clocks: the place, the viewer, UTC
        #
        # The viewer's zone comes from the browser, so it is forced here rather
        # than assumed. A Finn planning the Tarifa trip is the case in the task:
        # place 11:07 (+2), sinun aikasi 12:07 (+3), UTC 09:07.
        hctx = browser.new_context(viewport={"width": 1280, "height": 900},
                                   timezone_id="Europe/Helsinki")
        hp = hctx.new_page()
        hp.goto(URL)
        hp.wait_for_function("window.eclipse !== undefined", timeout=15000)
        hp.evaluate("eclipse.select('2027-08-02')")
        hp.wait_for_function("eclipse.data.meta.date === '2027-08-02'",
                             timeout=15000)
        hp.wait_for_timeout(1200)
        hp.evaluate("eclipse.map.setView([35.9,-5.6],9)")
        hp.wait_for_timeout(600)
        hp.evaluate("eclipse.markers.Tarifa.openPopup()")
        hp.wait_for_timeout(400)
        tar = " ".join(
            hp.query_selector(".leaflet-popup-content").inner_text().split())

        head = re.search(r"PAIKALLINEN (UTC[+−]\S+) SINUN AIKASI (UTC[+−]\S+) UTC",
                         tar, re.I)
        check("11a. three clocks are headed place, viewer, UTC, with offsets",
              head is not None and head.group(1) == "UTC+2"
              and head.group(2) == "UTC+3", tar[:70])

        got = re.search(r"MAKSIMI (\d\d:\d\d:\d\d) (\d\d:\d\d:\d\d) "
                        r"(\d\d:\d\d:\d\d)", tar, re.I)
        check("11b. Tarifa: place +2, viewer +3, UTC, in that order",
              got is not None
              and got.group(1) == hms(tarifa["max_s"] + 7200)
              and got.group(2) == hms(tarifa["max_s"] + 10800)
              and got.group(3) == hms(tarifa["max_s"]),
              " / ".join(got.groups()) if got else "no row parsed")

        rows = hp.evaluate(
            "[...document.querySelectorAll('.leaflet-popup-content .times tr')]"
            ".map(r => r.children.length)")
        check("11c. every event keeps all three clocks on one line",
              len(rows) == 6 and set(rows) == {4},
              f"{len(rows)} rows of {sorted(set(rows))} cells")
        check("11d. the viewer's zone is named, and it is the browser's own",
              "Europe/Helsinki" in tar
              and hp.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone")
              == "Europe/Helsinki",
              tar[-58:])

        # A viewer already on the place's offset would be shown the same numbers
        # twice, so that column goes away.
        cctx = browser.new_context(viewport={"width": 1280, "height": 900},
                                   timezone_id="Africa/Cairo")
        cp = cctx.new_page()
        cp.goto(URL)
        cp.wait_for_function("window.eclipse !== undefined", timeout=15000)
        cp.evaluate("eclipse.select('2027-08-02')")
        cp.wait_for_function("eclipse.data.meta.date === '2027-08-02'",
                             timeout=15000)
        cp.wait_for_timeout(1200)
        cp.evaluate("eclipse.map.setView([25.7,32.6],8)")
        cp.wait_for_timeout(600)
        cp.evaluate("eclipse.markers.Luxor.openPopup()")
        cp.wait_for_timeout(400)
        lux = " ".join(
            cp.query_selector(".leaflet-popup-content").inner_text().split())
        cells = cp.evaluate(
            "[...document.querySelectorAll('.leaflet-popup-content .times tr')]"
            ".map(r => r.children.length)")
        check("11e. a viewer on the place's own offset gets no duplicate column",
              "SINUN" not in lux.upper() and set(cells) == {3}
              and f"{hms(luxor['max_s'] + 10800)} {hms(luxor['max_s'])}" in lux,
              lux[:70])

        # Same three clocks for a clicked point, not just for the marked sites.
        hp.evaluate("eclipse.map.closePopup(); eclipse.map.setView([36.20,-5.85],8)")
        hp.wait_for_timeout(700)
        xy = hp.evaluate("([a,b]) => { const p ="
                         " eclipse.map.latLngToContainerPoint(L.latLng(a,b));"
                         " return [p.x, p.y]; }", [36.20, -5.85])
        hp.mouse.click(xy[0], xy[1])
        hp.wait_for_timeout(500)
        clicked = " ".join(
            hp.query_selector(".click-popup").inner_text().split())
        crow = re.search(r"MAKSIMI (\d\d:\d\d:\d\d) (\d\d:\d\d:\d\d) "
                         r"(\d\d:\d\d:\d\d)", clicked, re.I)
        check("11f. a clicked point gets the same three clocks",
              crow is not None
              and secs(crow.group(1)) - secs(crow.group(3)) == 7200
              and secs(crow.group(2)) - secs(crow.group(3)) == 10800
              and "SINUN AIKASI" in clicked.upper(),
              clicked[:80])
        hctx.close()
        cctx.close()

        # 12. local circumstances for any clicked point, not just inside the path
        #
        # The reference numbers below were not taken on trust: they are
        # recomputed here from JPL DE440s through eclipse_core (the same route
        # gen_data uses) and cross-checked against a second, independent
        # calculation straight from skyfield's apparent topocentric positions —
        # separation of the two centres against their apparent radii. Both
        # agree to better than 0.001 in magnitude and a second in time. No
        # published table was consulted: this machine has no network. The
        # agreed values for Helsinki (60.17N, 24.94E) on 2026-08-12 are
        # magnitude 0.8331 at 17:52:42 UTC, and the Sun is 2.4 degrees high at
        # that moment — it sets while the eclipse is still running.
        import numpy as np
        from eclipse_core import R_MOON_KM, R_SUN_KM, SkyTable, eph, local_circumstances
        from eclipse_core import ts as ec_ts
        from skyfield.api import wgs84 as ec_wgs84

        HELSINKI = (60.17, 24.94)
        t0 = ec_ts.utc(2026, 8, 12, 0, 0, 0)
        sky = SkyTable(t0, np.arange(14 * 3600, 21 * 3600, 10.0))
        truth = local_circumstances(sky, *HELSINKI)

        # ...and the same quantity the other way round, from apparent positions.
        here = eph["earth"] + ec_wgs84.latlon(*HELSINKI)
        tmax = ec_ts.utc(2026, 8, 12, 0, 0, truth["max_s"])
        seen = here.at(tmax)
        sun_v = seen.observe(eph["sun"]).apparent()
        moon_v = seen.observe(eph["moon"]).apparent()
        sep = sun_v.separation_from(moon_v).radians
        rs = np.arcsin(R_SUN_KM / sun_v.distance().km)
        rm = np.arcsin(R_MOON_KM / moon_v.distance().km)
        mag2 = float((rs + rm - sep) / (2 * rs))
        alt = float(sun_v.altaz()[0].degrees)

        check("12a. the two independent calculations agree on Helsinki",
              abs(truth["max_magnitude"] - mag2) < 0.001,
              "core %.4f vs apparent %.4f at %s"
              % (truth["max_magnitude"], mag2, hms(truth["max_s"])))
        check("12b. Helsinki sees a deep partial eclipse on 2026-08-12",
              abs(truth["max_magnitude"] - 0.833) < 0.005
              and abs(truth["max_s"] - (17 * 3600 + 52 * 60 + 42)) < 60,
              "magnitude %.4f, max %s UTC" % (truth["max_magnitude"], hms(truth["max_s"])))
        check("12c. and the Sun is low enough to set during it",
              0 < alt < 5, "%.2f deg at maximum" % alt)

        # The page must reach the same answer, in the browser, from the data
        # file alone.
        page.evaluate("eclipse.select('2026-08-12')")
        page.wait_for_function("eclipse.data.meta.date === '2026-08-12'", timeout=15000)
        page.wait_for_timeout(800)
        js = page.evaluate("eclipse.circumstancesAt(60.17, 24.94)")
        check("12d. the page computes local circumstances outside the path",
              js is not None and js.get("visible") is True,
              str(js)[:90])
        check("12e. and gets the same magnitude as the ephemeris",
              js and abs(js["magnitude"] - truth["max_magnitude"]) < 0.01,
              "page %.4f vs %.4f" % (js["magnitude"], truth["max_magnitude"]) if js else "none")
        check("12f. and the same time of maximum, to the minute",
              js and abs(js["max"] - truth["max_s"]) < 60,
              "page %s vs %s" % (hms(js["max"]), hms(truth["max_s"])) if js else "none")
        check("12g. obscuration is reported as well as magnitude",
              js and 0.70 < js["obscuration"] < js["magnitude"],
              "%.3f of the disc" % js["obscuration"] if js else "none")
        check("12h. the Sun setting mid-eclipse is called out",
              js and js.get("cutByHorizon") is True,
              "cut by horizon: %s" % (js.get("cutByHorizon") if js else "none"))

        # A point that sees nothing at all must say so rather than stay silent.
        far = page.evaluate("eclipse.circumstancesAt(-33.87, 151.21)")   # Sydney
        check("12i. a point the eclipse never reaches says so",
              far is not None and far.get("visible") is False,
              str(far))

        # And the popup itself, clicked on the map.
        page.evaluate("eclipse.map.closePopup(); eclipse.map.setView([60.17,24.94],6)")
        page.wait_for_timeout(700)
        hxy = page.evaluate("([a,b]) => { const p ="
                            " eclipse.map.latLngToContainerPoint(L.latLng(a,b));"
                            " return [p.x, p.y]; }", [60.17, 24.94])
        page.mouse.click(hxy[0], hxy[1])
        page.wait_for_timeout(600)
        pop = page.query_selector(".click-popup")
        text = " ".join(pop.inner_text().split()) if pop else ""
        check("12j. clicking Finland opens a popup that answers the question",
              "OSITTAINEN" in text.upper() and "%" in text
              and re.search(r"MAKSIMI \d\d:\d\d:\d\d", text, re.I) is not None,
              text[:100])
        check("12k. and it names the sunset",
              "AURINKO LASKEE" in text.upper(), text[:100])

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
                # Scripted shots frame 2027 unless they pick an eclipse
                # themselves, which they say by calling eclipse.select.
                if js and "eclipse.select(" not in js:
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
