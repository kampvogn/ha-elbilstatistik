"""All HTTP is mocked; the real API is never called."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.elbilstatistik.const import DOMAIN, EVENT_VEHICLE

BASE = "https://api.elbilstatistik.dk/v1"
PLATE_URL = f"{BASE}/plates/AB12345"

ANSWER = {
    "data_date": "2026-11-01",
    "query": "AB12345",
    "match": "exact",
    "vehicle": {
        "id": 1,
        "plate": "AB12345",
        "vin": "X",
        "make": "Tesla",
        "model": "Model 3",
        "variant": "Long Range",
        "vehicle_type": "Personbil",
        "fuel": "El",
        "is_electric": True,
        "color": "Hvid",
        "status": "Registreret",
        "status_display": "Registreret",
        "first_registration": "2021-03-04",
        "model_year": 2021,
    },
}


async def setup(hass, data=None, options=None):
    entry = MockConfigEntry(domain=DOMAIN, data=data or {}, options=options or {})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def call(hass, plate="ab 123-45", **extra):
    return await hass.services.async_call(
        DOMAIN, "lookup_plate", {"plate": plate, **extra},
        blocking=True, return_response=True,
    )


# ---- config flow ----

async def start(hass, key):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert r["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(r["flow_id"], {"api_key": key})


async def test_flow_no_key_makes_no_call(hass, aioclient_mock):
    r = await start(hass, "")
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["data"] == {}
    assert aioclient_mock.call_count == 0


async def test_flow_good_key_404_is_fine(hass, aioclient_mock):
    aioclient_mock.get(f"{BASE}/vehicles/1", status=404)
    r = await start(hass, "secret-key")
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["data"] == {"api_key": "secret-key"}
    assert aioclient_mock.call_count == 1
    assert aioclient_mock.mock_calls[0][3]["X-API-Key"] == "secret-key"


async def test_flow_bad_key(hass, aioclient_mock):
    aioclient_mock.get(f"{BASE}/vehicles/1", status=401)
    r = await start(hass, "nope")
    assert r["type"] is FlowResultType.FORM
    assert r["errors"] == {"base": "invalid_auth"}


async def test_flow_network_error(hass, aioclient_mock):
    import aiohttp
    aioclient_mock.get(f"{BASE}/vehicles/1", exc=aiohttp.ClientError)
    r = await start(hass, "k")
    assert r["errors"] == {"base": "cannot_connect"}


async def test_options_flow(hass):
    entry = await setup(hass)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], {"cache_hours": 2, "fuzzy": False}
    )
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"cache_hours": 2.0, "fuzzy": False}


# ---- service ----

async def test_lookup_maps_fields_event_and_sensor(hass, aioclient_mock):
    aioclient_mock.get(PLATE_URL, json=ANSWER)
    await setup(hass)
    events = async_capture_events(hass, EVENT_VEHICLE)
    res = await call(hass)
    assert res == {
        "plate": "AB12345", "found": True, "make": "Tesla", "model": "Model 3",
        "variant": "Long Range", "colour": "Hvid", "fuel": "El", "is_electric": True,
        "status": "Registreret", "first_registration": "2021-03-04", "model_year": 2021,
        "vehicle_type": "Personbil", "data_date": "2026-11-01", "match": "exact",
    }
    await hass.async_block_till_done()
    assert len(events) == 1 and events[0].data == res
    st = hass.states.get("sensor.elbilstatistik_last_vehicle")
    assert st.state == "Tesla Model 3"
    assert st.attributes["colour"] == "Hvid"
    # fuzzy defaults to on
    assert aioclient_mock.mock_calls[0][1].query == {"fuzzy": "true"}


async def test_not_found_cached_too(hass, aioclient_mock):
    aioclient_mock.get(PLATE_URL, status=404)
    await setup(hass)
    res = await call(hass)
    assert res["found"] is False and res["plate"] == "AB12345" and res["make"] is None
    await call(hass)
    assert aioclient_mock.call_count == 1
    assert hass.states.get("sensor.elbilstatistik_last_vehicle").state in ("Unknown", "Ukendt")


async def test_cache_hit_and_expiry(hass, aioclient_mock):
    aioclient_mock.get(PLATE_URL, json=ANSWER)
    await setup(hass)
    await call(hass)
    await call(hass, plate="AB12345")
    assert aioclient_mock.call_count == 1
    with patch("custom_components.elbilstatistik.manager._now", return_value=1e9):
        await call(hass)
    assert aioclient_mock.call_count == 2


async def test_fuzzy_parameter(hass, aioclient_mock):
    aioclient_mock.get(PLATE_URL, json=ANSWER)
    await setup(hass, options={"fuzzy": False})
    await call(hass)
    assert aioclient_mock.mock_calls[0][1].query == {}
    await call(hass, fuzzy=True)
    assert aioclient_mock.call_count == 2
    assert aioclient_mock.mock_calls[1][1].query == {"fuzzy": "true"}


async def test_api_key_header_only_when_set(hass, aioclient_mock):
    aioclient_mock.get(PLATE_URL, json=ANSWER)
    await setup(hass, data={"api_key": "abc"})
    await call(hass)
    assert aioclient_mock.mock_calls[0][3]["X-API-Key"] == "abc"


async def test_concurrent_lookups_share_one_call(hass, aioclient_mock):
    import asyncio
    aioclient_mock.get(PLATE_URL, json=ANSWER)
    await setup(hass)
    a, b = await asyncio.gather(call(hass), call(hass))
    assert a == b
    assert aioclient_mock.call_count == 1


async def test_429_backoff(hass, aioclient_mock, caplog):
    aioclient_mock.get(PLATE_URL, status=429, headers={"Retry-After": "120"})
    await setup(hass, data={"api_key": "topsecret"})
    with patch("custom_components.elbilstatistik.manager._now", return_value=1000.0):
        with pytest.raises(HomeAssistantError):
            await call(hass)
        with pytest.raises(HomeAssistantError):
            await call(hass)
        assert aioclient_mock.call_count == 1
    with patch("custom_components.elbilstatistik.manager._now", return_value=1100.0):
        with pytest.raises(HomeAssistantError):
            await call(hass)
        assert aioclient_mock.call_count == 1
    aioclient_mock.clear_requests()
    aioclient_mock.get(PLATE_URL, json=ANSWER)
    with patch("custom_components.elbilstatistik.manager._now", return_value=1121.0):
        assert (await call(hass))["found"] is True
    assert aioclient_mock.call_count == 1
    warnings = [r for r in caplog.records if r.levelname == "WARNING" and "429" in r.getMessage()]
    assert len(warnings) == 1
    assert "topsecret" not in caplog.text


async def test_invalid_plate_400(hass, aioclient_mock):
    aioclient_mock.get(PLATE_URL, status=400)
    await setup(hass)
    with pytest.raises(ServiceValidationError):
        await call(hass)
