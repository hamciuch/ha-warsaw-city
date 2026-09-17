from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    c = hass.data[DOMAIN][entry.entry_id]
    entities = [WarsawStopSensor(c, key) for key in c.data.get("stops", {})]
    entities += [WarsawAirIndexSensor(c), WarsawEventsSensor(c), WarsawAlertsSensor(c)]
    for code in (c.data.get("air", {}).get("measurements", {}) or {}):
        entities.append(WarsawPollutantSensor(c, code))
    async_add_entities(entities)

class WarsawBase(CoordinatorEntity):
    _attr_has_entity_name = True

class WarsawStopSensor(WarsawBase, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:bus-clock"
    def __init__(self, coordinator, key):
        super().__init__(coordinator); self.key = key
        stop = coordinator.data["stops"][key]
        self._attr_unique_id = f"warsaw_stop_{key}"
        self._attr_name = f'{stop["name"]} {stop["nr"]}'
    @property
    def native_value(self):
        d = self.coordinator.data["stops"].get(self.key, {}).get("departures", [])
        return d[0]["minutes"] if d else None
    @property
    def extra_state_attributes(self):
        s = self.coordinator.data["stops"].get(self.key, {})
        lines = set(s.get("lines", []))
        alerts = [a for a in self.coordinator.data.get("alerts", []) if lines & set(a.get("lines", []))]
        return {"stop_id": s.get("id"), "stop_nr": s.get("nr"), "lines": s.get("lines", []), "departures": s.get("departures", []), "alerts": alerts}

class WarsawAirIndexSensor(WarsawBase, SensorEntity):
    _attr_icon = "mdi:air-filter"
    _attr_name = "Air quality"
    _attr_unique_id = "warsaw_air_quality_index"
    @property
    def native_value(self): return self.coordinator.data.get("air", {}).get("index")
    @property
    def extra_state_attributes(self):
        a = self.coordinator.data.get("air", {})
        return {k: a.get(k) for k in ("station", "station_id", "distance_km", "address", "recommendations")}

class WarsawPollutantSensor(WarsawBase, SensorEntity):
    _attr_icon = "mdi:molecule"
    def __init__(self, coordinator, code):
        super().__init__(coordinator); self.code = code
        self._attr_unique_id = f"warsaw_air_{code}"
        self._attr_name = f"Air {code.upper()}"
    @property
    def native_value(self): return self.coordinator.data.get("air", {}).get("measurements", {}).get(self.code, {}).get("value")
    @property
    def native_unit_of_measurement(self): return self.coordinator.data.get("air", {}).get("measurements", {}).get(self.code, {}).get("unit")
    @property
    def extra_state_attributes(self): return self.coordinator.data.get("air", {}).get("measurements", {}).get(self.code, {})

class WarsawEventsSensor(WarsawBase, SensorEntity):
    _attr_icon = "mdi:calendar-star"
    _attr_name = "Events"
    _attr_unique_id = "warsaw_events"
    @property
    def native_value(self): return len(self.coordinator.data.get("events", []))
    @property
    def extra_state_attributes(self): return {"events": self.coordinator.data.get("events", [])[:20]}

class WarsawAlertsSensor(WarsawBase, SensorEntity):
    _attr_icon = "mdi:alert-circle-outline"
    _attr_name = "WTP alerts"
    _attr_unique_id = "warsaw_wtp_alerts"
    @property
    def native_value(self): return len(self.coordinator.data.get("alerts", []))
    @property
    def extra_state_attributes(self): return {"alerts": self.coordinator.data.get("alerts", [])}
