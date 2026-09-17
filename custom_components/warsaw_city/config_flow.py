from __future__ import annotations

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WarsawApi, WarsawApiAuthError, WarsawApiError
from .const import CONF_API_KEY, CONF_STOPS, DOMAIN


class WarsawCityConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            api = WarsawApi(
                async_get_clientsession(self.hass),
                user_input[CONF_API_KEY],
            )
            try:
                await api.validate()
            except WarsawApiAuthError:
                errors["base"] = "invalid_auth"
            except (WarsawApiError, aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Warsaw City Open Data",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_API_KEY): str}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        # HA 2025.12+ injects config_entry into OptionsFlow.
        # Do not pass/set it manually.
        return WarsawOptionsFlow()


class WarsawOptionsFlow(config_entries.OptionsFlow):
    def __init__(self) -> None:
        self.matches = []
        self.selected = None
        self._posts = []
        self._selected_post = None
        self._lines = []

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_stop", "remove_stop"],
        )

    async def async_step_add_stop(self, user_input=None):
        errors = {}

        if user_input:
            api = WarsawApi(
                async_get_clientsession(self.hass),
                self.config_entry.data[CONF_API_KEY],
            )
            try:
                self.matches = await api.find_stop_groups(user_input["query"])
            except WarsawApiAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                if not self.matches:
                    errors["base"] = "stop_not_found"
                else:
                    return await self.async_step_choose_stop()

        return self.async_show_form(
            step_id="add_stop",
            data_schema=vol.Schema(
                {vol.Required("query"): str}
            ),
            errors=errors,
        )

    async def async_step_choose_stop(self, user_input=None):
        if user_input:
            stop_id = user_input["stop"]
            self.selected = next(
                x for x in self.matches if x["id"] == stop_id
            )

            api = WarsawApi(
                async_get_clientsession(self.hass),
                self.config_entry.data[CONF_API_KEY],
            )
            self._posts = await api.stop_posts(stop_id)

            if not self._posts:
                return self.async_abort(reason="no_posts")

            return await self.async_step_choose_post()

        choices = {
            x["id"]: f'{x["name"]} ({x["id"]})'
            for x in self.matches
        }

        return self.async_show_form(
            step_id="choose_stop",
            data_schema=vol.Schema(
                {vol.Required("stop"): vol.In(choices)}
            ),
        )

    async def async_step_choose_post(self, user_input=None):
        if user_input:
            self._selected_post = user_input["post"]

            api = WarsawApi(
                async_get_clientsession(self.hass),
                self.config_entry.data[CONF_API_KEY],
            )

            self._lines = await api.stop_lines(
                self.selected["id"],
                self._selected_post,
            )

            if not self._lines:
                return self.async_abort(reason="no_lines")

            return await self.async_step_choose_lines()

        return self.async_show_form(
            step_id="choose_post",
            data_schema=vol.Schema(
                {vol.Required("post"): vol.In(self._posts)}
            ),
        )

    async def async_step_choose_lines(self, user_input=None):
        if user_input:
            chosen_lines = sorted(
                {str(x) for x in user_input["lines"]}
            )

            stops = list(
                self.config_entry.options.get(CONF_STOPS, [])
            )

            item = {
                "id": self.selected["id"],
                "name": self.selected["name"],
                "nr": self._selected_post,
                "lines": chosen_lines,
            }

            # Replace configuration for the same physical stop/post
            # instead of creating duplicates.
            stops = [
                s
                for s in stops
                if not (
                    str(s.get("id")) == str(item["id"])
                    and str(s.get("nr")).zfill(2)
                    == str(item["nr"]).zfill(2)
                )
            ]
            stops.append(item)

            return self.async_create_entry(
                title="",
                data={CONF_STOPS: stops},
            )

        options = [
            selector.SelectOptionDict(value=line, label=line)
            for line in self._lines
        ]

        return self.async_show_form(
            step_id="choose_lines",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "lines",
                        default=list(self._lines),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_remove_stop(self, user_input=None):
        stops = list(
            self.config_entry.options.get(CONF_STOPS, [])
        )

        if not stops:
            return self.async_abort(reason="no_stops")

        choices = {}
        for stop in stops:
            lines = ", ".join(stop.get("lines", [])) or "wszystkie"
            key = f'{stop["id"]}_{stop["nr"]}'
            choices[key] = (
                f'{stop["name"]} {stop["nr"]} — {lines}'
            )

        if user_input:
            key = user_input["stop"]
            stops = [
                s
                for s in stops
                if f'{s["id"]}_{s["nr"]}' != key
            ]
            return self.async_create_entry(
                title="",
                data={CONF_STOPS: stops},
            )

        return self.async_show_form(
            step_id="remove_stop",
            data_schema=vol.Schema(
                {vol.Required("stop"): vol.In(choices)}
            ),
        )
