from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    c = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WarsawAlertBinary(c)])

class WarsawAlertBinary(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "WTP relevant alert"
    _attr_icon = "mdi:alert"
    _attr_unique_id = "warsaw_wtp_relevant_alert"
    @property
    def is_on(self): return bool(self.coordinator.data.get("alerts"))
    @property
    def extra_state_attributes(self): return {"count": len(self.coordinator.data.get("alerts", []))}
