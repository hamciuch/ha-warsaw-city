from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import WarsawApi
from .const import DEFAULT_DEPARTURES, DOMAIN

_LOGGER = logging.getLogger(__name__)


class WarsawCoordinator(DataUpdateCoordinator):
    def __init__(
        self,
        hass: HomeAssistant,
        api: WarsawApi,
        stops: list[dict],
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=60),
        )
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
                configured_lines = {
                    str(x)
                    for x in stop.get("lines", [])
                    if x
                }

                deps, lines = await self.api.departures(
                    stop["id"],
                    stop["nr"],
                    DEFAULT_DEPARTURES,
                    configured_lines or None,
                )

                # New configuration: alerts only for chosen lines.
                # Old saved entries without "lines" keep previous
                # behavior and use all lines at the stop.
                active_lines = (
                    sorted(configured_lines)
                    if configured_lines
                    else lines
                )

                all_lines.update(active_lines)

                stop_data[
                    f'{stop["id"]}_{stop["nr"]}'
                ] = {
                    "name": stop["name"],
                    "id": stop["id"],
                    "nr": stop["nr"],
                    "departures": deps,
                    "lines": active_lines,
                }

        except Exception as err:
            raise UpdateFailed(
                f"Warsaw transport update failed: {err}"
            ) from err

        if self._tick % 5 == 0:
            try:
                self._air = await self.api.air_quality(
                    self.hass.config.latitude,
                    self.hass.config.longitude,
                )
            except Exception as err:
                _LOGGER.warning(
                    "Warsaw air quality update failed: %s",
                    err,
                )

            try:
                self._alerts = await self.api.alerts(
                    all_lines
                )
            except Exception as err:
                _LOGGER.warning(
                    "Warsaw WTP alerts update failed: %s",
                    err,
                )

        if self._tick % 30 == 0:
            try:
                self._events = await self.api.events()
            except Exception as err:
                _LOGGER.warning(
                    "Warsaw events update failed: %s",
                    err,
                )

        self._tick += 1

        return {
            "stops": stop_data,
            "air": self._air,
            "events": self._events,
            "alerts": self._alerts,
        }
