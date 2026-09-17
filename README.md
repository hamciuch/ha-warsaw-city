# Warsaw City Open Data v0.3.3

Fixes CAM event extraction after v0.3.2 returned an empty list.

Changes:
- event title is taken directly from the `/wydarzenie/` link;
- no dependency on the link being wrapped in h2/h3/h4;
- event metadata is discovered from the nearest ancestor block;
- generic links such as "Zapisz się" are ignored;
- filter headings are still excluded because they are not `/wydarzenie/` links;
- current/future dated events are sorted chronologically.

Overwrite:
- custom_components/warsaw_city/api.py
- custom_components/warsaw_city/manifest.json

Restart Home Assistant afterwards.
