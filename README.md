# Warsaw City Open Data v0.3.5

Events regression fix.

v0.3.2-v0.3.4 over-constrained the CAM HTML parser and could return zero events.

v0.3.5 deliberately restores the event scraping logic from v0.3.0 — the version
that was confirmed to populate `sensor.events` on the user's Home Assistant.

Only post-processing is added:
- filters page headings: Kalendarz wydarzeń, Termin, Kategorie wydarzeń, Bilety;
- gathers up to 40 raw entries before filtering;
- derives an optional ISO `start` field for chronological sorting;
- a failed date parse never causes a real event to be dropped;
- returns up to 20 events.

Overwrite:
- custom_components/warsaw_city/api.py
- custom_components/warsaw_city/manifest.json

Restart Home Assistant after copying.
