# TASK 4 — version number in the corner

Tiny one. Show a version indicator in a bottom corner of the page (opposite
corner from the existing attribution line, so they don't collide).

- Format: `v<N> · <short git hash>` — e.g. `v3 · 4f2a1c9`. N is a simple
  integer you bump by hand in one obvious place (top of app.js or a
  `<meta>`/constant in index.html).
- The git hash: inject at commit time is overkill — read it at *data/page
  generation* if trivial, otherwise leave just `v<N>` and skip the hash.
  Don't build any tooling for this.
- Style: same muted look as the attribution line, small, non-interactive,
  doesn't overlap controls at any window size.
- Bump to the current version counting the milestones so far (initial=1,
  click-to-time=2, markers=3 → this task makes it 4 if markers are done,
  otherwise number accordingly).
- Update STATUS.md one line.
