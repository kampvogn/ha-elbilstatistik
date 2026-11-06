"""Elbilstatistik: look up Danish number plates from Home Assistant."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import ElbilstatistikClient
from .const import (
    CONF_API_KEY,
    CONF_CACHE_HOURS,
    CONF_FUZZY,
    DEFAULT_CACHE_HOURS,
    DEFAULT_FUZZY,
    DOMAIN,
    SERVICE_LOOKUP_PLATE,
)
from .manager import LookupManager

PLATFORMS = ["sensor"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

LOOKUP_SCHEMA = vol.Schema(
    {vol.Required("plate"): cv.string, vol.Optional("fuzzy"): cv.boolean}
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the service once; it uses whichever entry is loaded."""

    async def handle_lookup(call: ServiceCall) -> ServiceResponse:
        managers = hass.data.get(DOMAIN, {})
        if not managers:
            raise ServiceValidationError("Elbilstatistik is not set up")
        manager: LookupManager = next(iter(managers.values()))
        return await manager.lookup(call.data["plate"], call.data.get("fuzzy"))

    hass.services.async_register(
        DOMAIN,
        SERVICE_LOOKUP_PLATE,
        handle_lookup,
        schema=LOOKUP_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = ElbilstatistikClient(
        async_get_clientsession(hass), entry.data.get(CONF_API_KEY)
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = LookupManager(
        hass,
        client,
        entry.options.get(CONF_CACHE_HOURS, DEFAULT_CACHE_HOURS),
        entry.options.get(CONF_FUZZY, DEFAULT_FUZZY),
    )
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
