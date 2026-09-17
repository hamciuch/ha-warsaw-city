from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WarsawApi, WarsawApiError
from .const import CONF_API_KEY, CONF_STOPS, DOMAIN


class WarsawCityConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            api = WarsawApi(async_get_clientsession(self.hass), user_input[CONF_API_KEY])
            try:
                await api.validate()
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Warsaw City Open Data", data=user_input)
        return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return WarsawOptionsFlow(config_entry)


class WarsawOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry
        self.matches = []
        self.selected = None

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=["add_stop", "remove_stop"])

    async def async_step_add_stop(self, user_input=None):
        errors = {}
        if user_input:
            api = WarsawApi(async_get_clientsession(self.hass), self.config_entry.data[CONF_API_KEY])
            self.matches = await api.find_stop_groups(user_input["query"])
            if not self.matches:
                errors["base"] = "stop_not_found"
            else:
                return await self.async_step_choose_stop()
        return self.async_show_form(step_id="add_stop", data_schema=vol.Schema({vol.Required("query"): str}), errors=errors)

    async def async_step_choose_stop(self, user_input=None):
        if user_input:
            stop_id = user_input["stop"]
            self.selected = next(x for x in self.matches if x["id"] == stop_id)
            api = WarsawApi(async_get_clientsession(self.hass), self.config_entry.data[CONF_API_KEY])
            posts = await api.stop_posts(stop_id)
            if not posts:
                return self.async_abort(reason="no_posts")
            self._posts = posts
            return await self.async_step_choose_post()
        choices = {x["id"]: f'{x["name"]} ({x["id"]})' for x in self.matches}
        return self.async_show_form(step_id="choose_stop", data_schema=vol.Schema({vol.Required("stop"): vol.In(choices)}))

    async def async_step_choose_post(self, user_input=None):
        if user_input:
            stops = list(self.config_entry.options.get(CONF_STOPS, []))
            item = {"id": self.selected["id"], "name": self.selected["name"], "nr": user_input["post"]}
            if item not in stops:
                stops.append(item)
            return self.async_create_entry(title="", data={CONF_STOPS: stops})
        return self.async_show_form(step_id="choose_post", data_schema=vol.Schema({vol.Required("post"): vol.In(self._posts)}))

    async def async_step_remove_stop(self, user_input=None):
        stops = list(self.config_entry.options.get(CONF_STOPS, []))
        if not stops:
            return self.async_abort(reason="no_stops")
        choices = {f'{s["id"]}_{s["nr"]}': f'{s["name"]} {s["nr"]}' for s in stops}
        if user_input:
            key = user_input["stop"]
            stops = [s for s in stops if f'{s["id"]}_{s["nr"]}' != key]
            return self.async_create_entry(title="", data={CONF_STOPS: stops})
        return self.async_show_form(step_id="remove_stop", data_schema=vol.Schema({vol.Required("stop"): vol.In(choices)}))
