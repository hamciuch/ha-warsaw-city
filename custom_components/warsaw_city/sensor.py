from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        WarsawStopSensor(coordinator, key)
        for key in coordinator.data.get("stops", {})
    ]

    entities += [
        WarsawAirIndexSensor(coordinator),
        WarsawEventsSensor(coordinator),
        WarsawAlertsSensor(coordinator),
    ]

    for code in (
        coordinator.data.get("air", {})
        .get("measurements", {})
        or {}
    ):
        entities.append(
            WarsawPollutantSensor(
                coordinator,
                code,
            )
        )

    async_add_entities(entities)


class WarsawBase(CoordinatorEntity):
    _attr_has_entity_name = True


class WarsawStopSensor(WarsawBase, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:bus-clock"

    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        self.key = key
        stop = coordinator.data["stops"][key]
        self._attr_unique_id = f"warsaw_stop_{key}"
        self._attr_name = f'{stop["name"]} {stop["nr"]}'

    @property
    def native_value(self):
        departures = (
            self.coordinator.data["stops"]
            .get(self.key, {})
            .get("departures", [])
        )
        upcoming = [
            departure
            for departure in departures
            if not departure.get("is_past", False)
        ]

        return (
            upcoming[0]["minutes"]
            if upcoming
            else None
        )

    @property
    def available(self):
        return (
            super().available
            and self.key
            in self.coordinator.data.get("stops", {})
        )

    @property
    def extra_state_attributes(self):
        stop = (
            self.coordinator.data.get("stops", {})
            .get(self.key, {})
        )

        lines = set(stop.get("lines", []))
        alerts = [
            alert
            for alert
            in self.coordinator.data.get("alerts", [])
            if lines & set(alert.get("lines", []))
        ]

        return {
            "stop_id": stop.get("id"),
            "stop_nr": stop.get("nr"),
            "lines": stop.get("lines", []),
            "departures": stop.get("departures", []),
            "alerts": alerts,
        }


class WarsawAirIndexSensor(WarsawBase, SensorEntity):
    _attr_icon = "mdi:air-filter"
    _attr_name = "Air quality"
    _attr_unique_id = "warsaw_air_quality_index"

    @property
    def native_value(self):
        return (
            self.coordinator.data
            .get("air", {})
            .get("index")
        )

    @property
    def available(self):
        return (
            super().available
            and bool(
                self.coordinator.data.get("air", {})
            )
        )

    @property
    def extra_state_attributes(self):
        air = self.coordinator.data.get("air", {})

        return {
            key: air.get(key)
            for key in (
                "station",
                "station_id",
                "distance_km",
                "address",
                "index_value",
                "critical_pollutant",
                "source",
            )
        }


class WarsawPollutantSensor(WarsawBase, SensorEntity):
    _attr_icon = "mdi:molecule"

    def __init__(
        self,
        coordinator,
        code,
    ):
        super().__init__(coordinator)
        self.code = code
        self._attr_unique_id = f"warsaw_air_{code}"

        measurement = (
            coordinator.data.get("air", {})
            .get("measurements", {})
            .get(code, {})
        )
        label = measurement.get(
            "name",
            code.upper(),
        )
        self._attr_name = f"Air {label}"

    @property
    def native_value(self):
        return (
            self.coordinator.data.get("air", {})
            .get("measurements", {})
            .get(self.code, {})
            .get("value")
        )

    @property
    def native_unit_of_measurement(self):
        return (
            self.coordinator.data.get("air", {})
            .get("measurements", {})
            .get(self.code, {})
            .get("unit")
        )

    @property
    def available(self):
        measurement = (
            self.coordinator.data.get("air", {})
            .get("measurements", {})
            .get(self.code, {})
        )

        return (
            super().available
            and measurement.get("value") is not None
        )

    @property
    def extra_state_attributes(self):
        return (
            self.coordinator.data.get("air", {})
            .get("measurements", {})
            .get(self.code, {})
        )


class WarsawEventsSensor(WarsawBase, SensorEntity):
    _attr_icon = "mdi:calendar-star"
    _attr_name = "Events"
    _attr_unique_id = "warsaw_events"

    @property
    def native_value(self):
        events = self.coordinator.data.get(
            "events",
            [],
        )
        return len(events)

    @property
    def available(self):
        return (
            super().available
            and self.coordinator.data.get("events")
            is not None
        )

    @property
    def extra_state_attributes(self):
        return {
            "source": "CAM Warszawa",
            "events": self.coordinator.data.get(
                "events",
                [],
            )[:20],
        }


class WarsawAlertsSensor(WarsawBase, SensorEntity):
    _attr_icon = "mdi:alert-circle-outline"
    _attr_name = "WTP alerts"
    _attr_unique_id = "warsaw_wtp_alerts"

    @property
    def native_value(self):
        return len(
            self.coordinator.data.get(
                "alerts",
                [],
            )
        )

    @property
    def extra_state_attributes(self):
        return {
            "alerts": self.coordinator.data.get(
                "alerts",
                [],
            )
        }
