# Warsaw City Open Data v0.3.0

## New in 0.3.0

- Air quality is now populated from the official GIOŚ v1 API.
- The nearest GIOŚ station is selected from Home Assistant latitude/longitude.
- Air entities may include PM2.5, PM10, NO2, O3, SO2 and CO depending on the nearest station.
- `sensor.warsaw_air_quality_index` exposes station metadata and GIOŚ index details.
- Events are populated from the official CAM Warsaw event calendar.
- `sensor.warsaw_events` exposes up to 20 current/upcoming events in the `events` attribute.
- Empty bonus-module sensors now report unavailable instead of misleading empty/unknown data where possible.
- Includes the v0.2.4 departures parser fix.

## Files to overwrite

- `custom_components/warsaw_city/api.py`
- `custom_components/warsaw_city/sensor.py`
- `custom_components/warsaw_city/manifest.json`

Restart Home Assistant after copying.

## Sources

Transport: dane.um.warszawa.pl
Air quality: GIOŚ public API v1
Events: cam.warszawa.pl
