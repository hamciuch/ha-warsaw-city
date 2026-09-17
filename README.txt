Warsaw City Open Data v0.3.7

Changes:
- filters senior-focused CAM events;
- exposes up to 30 filtered events;
- increases departures per stop from 6 to 15;
- includes the fixed CAM parser and urljoin import.

Fastest way to apply and push:
  unzip ha-warsaw-city-v0.3.7.zip -d /tmp/warsaw037
  bash /tmp/warsaw037/ha-warsaw-city-v0.3.7/apply-and-push.sh ~/warsaw_city

Then update/reload the integration in Home Assistant and restart HA.
