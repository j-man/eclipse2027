# TASK 8 — clearer dropdown + this year's eclipse as default

Two changes:

## 1. Default eclipse = 2026-08-12

The total eclipse of **August 12, 2026** (Iceland → Spain) is four days away
from today — make it the default that loads first. 2027-08-02 stays in the
list as before. The default lives in one obvious constant.

## 2. The trigger must LOOK like a control (main complaint)

The title card does not read as a dropdown even with the chevron. Fix the
affordance, not the size of the arrow: add a clearly button-styled row INSIDE
the card, under the title — its own background, border, rounded corners,
hover state, larger chevron, and an action verb as label:
`Valitse pimennys (59) ▾`. A thing that looks like a button and says
"choose" is unambiguous; a title that happens to be clickable is not.
The whole card can stay clickable too, but the visible button row is the
signpost. Test at a glance: a first-time user must be able to answer
"how do I see other eclipses?" within two seconds.

## 3. Clearer dropdown list

The open list itself needs more clarity, not just the trigger:

- Each row: date on its own visual weight, then type + max duration + region,
  aligned in columns rather than one run-on string.
- Group headers or a subtle divider between decades (1980s/1990s/…), so 59
  rows are scannable.
- Highlight the currently selected row and the *next upcoming* eclipse
  (relative to today's date) — e.g. a small "next" tag on 2026-08-12.
- Past eclipses slightly dimmed relative to future ones.
- Keep keyboard navigation working (arrows move through rows across groups).
- List must stay usable at small window heights: internal scroll, selected
  row scrolled into view on open.

Update check.py (default eclipse assertion + picker still works), bump
version, one line in STATUS.md.
