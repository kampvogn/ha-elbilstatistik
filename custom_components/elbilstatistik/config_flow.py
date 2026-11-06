"""Config and options flow."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CannotConnect, ElbilstatistikClient, InvalidAuth, RateLimited
from .const import (
    ACCOUNT_URL,
    CONF_API_KEY,
    CONF_CACHE_HOURS,
    CONF_FUZZY,
    DEFAULT_CACHE_HOURS,
    DEFAULT_FUZZY,
    DOMAIN,
)


class ElbilstatistikConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return ElbilstatistikOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            key = (user_input.get(CONF_API_KEY) or "").strip()
            if key:
                client = ElbilstatistikClient(async_get_clientsession(self.hass), key)
                try:
                    await client.check_key()
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except RateLimited:
                    errors["base"] = "rate_limited"
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    errors["base"] = "unknown"
            if not errors:
                return self.async_create_entry(
                    title="Elbilstatistik",
                    data={CONF_API_KEY: key} if key else {},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional(CONF_API_KEY, default=""): str}),
            errors=errors,
            description_placeholders={"account_url": ACCOUNT_URL},
        )


class ElbilstatistikOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CACHE_HOURS,
                    default=opts.get(CONF_CACHE_HOURS, DEFAULT_CACHE_HOURS),
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=720)),
                vol.Required(
                    CONF_FUZZY, default=opts.get(CONF_FUZZY, DEFAULT_FUZZY)
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
