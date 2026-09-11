---
type: fix
scope: deploy
issue: 326
---

### Fixed

- deploy templates now pass one shared source/wheel/sdist artifact gate; install and upgrade preflight and render all templates before host-side writes, with single-JSON template failures and honest partial-I/O reports.
- packaging acceptance tests now install the `build` frontend before pytest; recursive template data requires `setuptools>=62.3`, and the source checker distinguishes truly empty directories from non-template files.
