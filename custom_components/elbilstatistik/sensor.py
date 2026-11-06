"""The 'last vehicle' sensor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_UPDATED
from .manager import LookupManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([LastVehicleSensor(hass.data[DOMAIN][entry.entry_id], entry)])


class LastVehicleSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "last_vehicle"
    _attr_icon = "mdi:car-search"
    _attr_should_poll = False

    def __init__(self, manager: LookupManager, entry: ConfigEntry) -> None:
        self._manager = manager
        self._attr_unique_id = f"{entry.entry_id}_last_vehicle"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Elbilstatistik",
            manufacturer="elbilstatistik.dk",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATED, self._refresh)
        )

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        last = self._manager.last
        if last is None:
            return None
        if not last["found"]:
            return "Ukendt" if self.hass.config.language.startswith("da") else "Unknown"
        return " ".join(p for p in (last["make"], last["model"]) if p) or last["plate"]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return dict(self._manager.last) if self._manager.last else None
