# TASK 7 — make the eclipse picker discoverable

User feedback: the eclipse dropdown is invisible unless you already know it's
there. Fix by merging it with the title card.

## Spec

1. The top-left title card (the one showing the eclipse name/date) becomes the
   picker trigger: whole card clickable, visible ▾ chevron after the title,
   and a small muted badge line like `1 / 59 eclipses` (or Finnish, match the
   card's current language).
2. Hover/focus state on the card so it reads as interactive (slight lift or
   border glow, consistent with the existing dark style).
3. Clicking opens the existing eclipse list anchored under the card — reuse
   the current dropdown contents, don't rebuild the list logic.
4. One-time attention cue: on first visit (localStorage flag) the chevron
   pulses gently for ~3 s, then never again.
5. Keyboard/A11y: the card is a button (Enter/Space opens), Esc closes.
6. Remove or hide the old standalone dropdown control so there aren't two
   entry points.
7. Update check.py: picker opens from the title card, selection still switches
   eclipses; bump the version number; one line in STATUS.md.
