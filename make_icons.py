#!/usr/bin/env python3
"""Render the app icons from web/icons/icon.svg.

    .venv/bin/python make_icons.py

Writes into web/icons/: icon-180.png (apple-touch-icon), icon-192.png,
icon-512.png, icon-maskable-512.png and favicon-32.png. The browser that
check.py already uses does the drawing, so the PNGs look exactly like the
SVG does in a browser, gradients and all.

The maskable icon is the same picture with #art shrunk by a further tenth,
because Android crops a maskable icon to whatever shape the launcher uses and
only promises the safe circle (the middle 80 %). #art already ends at that
circle in icon.svg; the margin keeps a tight launcher shape from cutting the
corona's faint edge. The background still runs to the edges.
"""

import os
import re
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = os.path.join(HERE, "web", "icons")
SOURCE = os.path.join(ICONS, "icon.svg")

# file -> (pixels, maskable)
OUTPUTS = {
    "icon-180.png": (180, False),
    "icon-192.png": (192, False),
    "icon-512.png": (512, False),
    "icon-maskable-512.png": (512, True),
    "favicon-32.png": (32, False),
}
# #art reaches 205 px from the centre of 512; the safe circle is 204.8 px.
MASKABLE_SCALE = 0.9


def maskable(svg):
    """The same SVG with #art shrunk about the centre into the safe circle."""
    scaled, n = re.subn(
        r'<g id="art">',
        '<g id="art" transform="translate(256 256) scale(%g) translate(-256 -256)">'
        % MASKABLE_SCALE, svg)
    if n != 1:
        raise SystemExit("icon.svg has no single <g id=\"art\"> to scale")
    return scaled


def render(page, svg, size, path):
    sized = re.sub(r'width="\d+" height="\d+"', 'width="%d" height="%d"' % (size, size),
                   svg, count=1)
    page.set_viewport_size({"width": size, "height": size})
    page.set_content('<!doctype html><html><body style="margin:0;background:#000">%s'
                     '</body></html>' % sized)
    page.locator("svg").screenshot(path=path)


def main():
    svg = open(SOURCE, encoding="utf-8").read()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(device_scale_factor=1)
        for name, (size, is_maskable) in OUTPUTS.items():
            path = os.path.join(ICONS, name)
            render(page, maskable(svg) if is_maskable else svg, size, path)
            print("  %s  %d px%s" % (name, size, ", maskable" if is_maskable else ""))
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
