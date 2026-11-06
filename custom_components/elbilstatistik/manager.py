"""Lookup logic: cache, de-duplication, back-off, event and sensor update."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .api import (
    ApiError,
    ElbilstatistikClient,
    InvalidAuth,
    InvalidPlate,
    RateLimited,
    normalize_plate,
)
from .const import EVENT_VEHICLE, SIGNAL_UPDATED

_LOGGER = logging.getLogger(__name__)


def _now() -> float:
    return time.monotonic()


def compact(plate: str, answer: dict[str, Any] | None) -> dict[str, Any]:
    """Map the API answer to the small dict used by service, event and sensor."""
    v = (answer or {}).get("vehicle") or {}
    status = v.get("status_display") or v.get("status")
    return {
        "plate": v.get("plate") or plate,
        "found": bool(v),
        "make": v.get("make"),
        "model": v.get("model"),
        "variant": v.get("variant"),
        "colour": v.get("color"),
        "fuel": v.get("fuel"),
        "is_electric": v.get("is_electric"),
        "status": status,
        "first_registration": v.get("first_registration"),
        "model_year": v.get("model_year"),
        "vehicle_type": v.get("vehicle_type"),
        "data_date": (answer or {}).get("data_date"),
        # "fuzzy": the camera's reading was corrected (0/O, 1/I ...) to find it
        "match": (answer or {}).get("match"),
    }


class LookupManager:
    """One per config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ElbilstatistikClient,
        cache_hours: float,
        fuzzy: bool,
    ) -> None:
        self.hass = hass
        self.client = client
        self.cache_seconds = float(cache_hours) * 3600
        self.fuzzy_default = fuzzy
        self.last: dict[str, Any] | None = None
        self._cache: dict[tuple[str, bool], tuple[float, dict[str, Any]]] = {}
        self._inflight: dict[tuple[str, bool], asyncio.Future] = {}
        self._blocked_until = 0.0

    async def lookup(self, plate: str, fuzzy: bool | None = None) -> dict[str, Any]:
        norm = normalize_plate(plate)
        if not norm:
            raise ServiceValidationError("The plate is empty")
        use_fuzzy = self.fuzzy_default if fuzzy is None else bool(fuzzy)
        key = (norm, use_fuzzy)

        hit = self._cache.get(key)
        if hit and _now() - hit[0] < self.cache_seconds:
            result = hit[1]
        elif key in self._inflight:
            result = await asyncio.shield(self._inflight[key])
        else:
            fut: asyncio.Future = self.hass.loop.create_future()
            self._inflight[key] = fut
            try:
                result = await self._fetch(norm, use_fuzzy)
                self._cache[key] = (_now(), result)
                fut.set_result(result)
            except BaseException as err:
                fut.set_exception(err)
                fut.exception()  # mark as retrieved; nobody may be waiting
                raise
            finally:
                self._inflight.pop(key, None)

        result = dict(result)
        self.last = result
        self.hass.bus.async_fire(EVENT_VEHICLE, result)
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)
        return result

    async def _fetch(self, norm: str, fuzzy: bool) -> dict[str, Any]:
        remaining = self._blocked_until - _now()
        if remaining > 0:
            raise HomeAssistantError(
                f"elbilstatistik.dk quota used up; try again in {int(remaining) + 1} s"
            )
        try:
            answer = await self.client.plate(norm, fuzzy)
        except RateLimited as err:
            _LOGGER.warning(
                "elbilstatistik.dk says the quota is used up (HTTP 429); "
                "pausing lookups for %s s",
                err.retry_after,
            )
            self._blocked_until = _now() + err.retry_after
            raise HomeAssistantError(
                f"elbilstatistik.dk quota used up; try again in {err.retry_after} s"
            ) from err
        except InvalidPlate as err:
            raise ServiceValidationError(f"'{norm}' is not a valid plate") from err
        except InvalidAuth as err:
            raise HomeAssistantError("The elbilstatistik.dk API key was rejected") from err
        except ApiError as err:
            raise HomeAssistantError(f"Lookup failed: {err}") from err
        return compact(norm, answer)
