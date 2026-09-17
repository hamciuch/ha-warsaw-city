# Warsaw City Open Data for Home Assistant

Custom Home Assistant integration using the Warsaw Open Data portal.

## v0.2.0

Transport has been migrated from the legacy `api.um.warszawa.pl` authentication to the new `dane.um.warszawa.pl` API:

- JWT/token is sent in the `Authorization` header.
- Token validation uses the current vehicle-location endpoint.
- Stop lookup uses `get_ztm_przystanki_komunikacji_miejskiej`.
- Departures use `get_ztm_odjazdy_linii_z_przystanku`.
- Bus/tram locations use `get_ztm_lokalizacja_pojazdow`.
- Vehicle records older than 3 minutes are ignored when attaching live vehicle data to departures.
- WTP alerts are filtered to lines serving configured stops.

### Current limitation

Warsaw has migrated the transport endpoints to the new portal, but the new action names/schema for the air-quality and city-events datasets still need to be confirmed. In v0.2.0 those two bonus modules return no data instead of making the integration fail. They will be restored once the new portal endpoints are verified.

## Installation

Copy `custom_components/warsaw_city` to your Home Assistant `/config/custom_components/` directory and restart Home Assistant, or install the repository through HACS as a custom repository.

Then add **Warsaw City Open Data** from Settings → Devices & services and enter a token generated at `dane.um.warszawa.pl`.

Use **Configure** on the integration to add or remove WTP stops.
