# Warsaw City Open Data v0.3.1

Transit-card support:
- keeps a departure for 5 minutes after its scheduled time;
- exposes signed `minutes_delta` and `is_past`;
- sensor state remains the nearest future departure;
- example Mushroom card:
  - red = departed within the last 5 minutes;
  - green = nearest upcoming departure;
  - blue = later departures within the next 60 minutes;
  - everything else is hidden.

Overwrite:
- custom_components/warsaw_city/api.py
- custom_components/warsaw_city/sensor.py
- custom_components/warsaw_city/manifest.json

Restart Home Assistant afterwards.
