# Warsaw City Open Data v0.3.2

Fixes CAM events parsing.

The old parser accidentally treated filter headings such as:
- Kalendarz wydarzeń
- Termin
- Kategorie wydarzeń
- Bilety

as events.

v0.3.2 only accepts links to real `/wydarzenie/` detail pages and extracts:
- title
- organizer
- date
- `start` ISO timestamp
- place
- free
- url

The list is sorted chronologically where a date can be parsed.

Overwrite:
- custom_components/warsaw_city/api.py
- custom_components/warsaw_city/manifest.json

Restart Home Assistant after copying.
