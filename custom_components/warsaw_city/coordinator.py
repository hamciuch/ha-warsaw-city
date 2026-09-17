from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WarsawApi
from .const import DEFAULT_DEPARTURES, DOMAIN


class WarsawCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, api: WarsawApi, stops: list[dict]) -> None:
        super().__init__(hass, logger=__import__("logging").getLogger(__name__), name=DOMAIN, update_interval=timedelta(seconds=60))
        self.api = api
        self.stops = stops
        self._tick = 0
        self._events = []
        self._air = {}
        self._alerts = []

    async def _async_update_data(self):
        try:
            stop_data = {}
            all_lines: set[str] = set()
            for stop in self.stops:
                deps, lines = await self.api.departures(stop["id"], stop["nr"], DEFAULT_DEPARTURES)
                all_lines.update(lines)
                stop_data[f'{stop["id"]}_{stop["nr"]}'] = {
                    "name": stop["name"], "id": stop["id"], "nr": stop["nr"], "departures": deps, "lines": lines
                }

            if self._tick % 5 == 0:
                self._air = await self.api.air_quality(self.hass.config.latitude, self.hass.config.longitude)
                self._alerts = await self.api.alerts(all_lines)
            if self._tick % 30 == 0:
                self._events = await self.api.events()
            self._tick += 1
            return {"stops": stop_data, "air": self._air, "events": self._events, "alerts": self._alerts}
        except Exception as err:
            raise UpdateFailed(str(err)) from err
