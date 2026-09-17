# Warsaw City Open Data v0.3.4

CAM Events parser rewrite.

Why v0.3.3 still returned zero:
the parser depended too much on link/container structure.

v0.3.4:
- detects actual event H2/H3/H4 headings;
- explicitly ignores CAM filter headings;
- requires a real date block (day + Polish month abbreviation);
- only accepts the smallest ancestor containing exactly one `Organizator:`;
- extracts title/date/time/place/organizer/free/url;
- sorts current/future events chronologically.

Overwrite:
- custom_components/warsaw_city/api.py
- custom_components/warsaw_city/manifest.json

Restart Home Assistant.
