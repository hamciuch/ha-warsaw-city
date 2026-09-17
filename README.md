# Warsaw City Open Data v0.2.1 fix

Patch for:
- HA 2025.12+ OptionsFlow (`self.config_entry` is read-only)
- stop selection in UI
- stop-post selection in UI
- multi-select monitored lines
- departures filtered to selected lines
- WTP alerts filtered to selected lines

Copy these files over the matching files in:
`custom_components/warsaw_city/`

Then restart Home Assistant.
