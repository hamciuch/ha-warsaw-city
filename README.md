# Warsaw City Open Data – Home Assistant

Custom integration for Warsaw Open Data, distributed through GitHub/HACS.

## v0.1.0
- WTP stop sensors with next departures, line, direction, scheduled time and minutes to departure.
- Stop search by name and stop-post selection.
- WTP alerts filtered to lines serving configured stops.
- Warsaw municipal Air Quality: nearest station to Home Assistant coordinates, city index and pollutant sensors.
- Warsaw Events sensor with upcoming events.

## Installation with HACS
1. HACS → Integrations → menu → Custom repositories.
2. Add `https://github.com/hamciuch/ha-warsaw-city` as an **Integration** repository.
3. Install **Warsaw City Open Data**.
4. Restart Home Assistant.
5. Settings → Devices & services → Add integration → **Warsaw City Open Data**.

An API key from Warsaw Open Data (`api.um.warszawa.pl`) is required.

After setup, open **Configure** to add one or more stops by name and choose the specific stop post (`01`, `02`, ...).

## Main entities
- stop sensor: minutes to next scheduled departure; attributes include up to six departures with line, direction, route, brigade and scheduled time
- Air Quality index sensor
- pollutant sensors exposed by the nearest city station
- Warsaw events sensor
- WTP alerts sensor filtered to configured-stop lines
- relevant WTP alert binary sensor

## Roadmap
### v0.2
- live vehicle positions from `busestrams_get`
- predicted ETA and delay versus timetable
- richer dashboard/card data

## Notes
v0.1.0 uses timetable departures. Live GPS is not yet used to calculate predicted ETA.
