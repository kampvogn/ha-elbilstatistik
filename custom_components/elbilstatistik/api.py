"""Small async client for the elbilstatistik.dk public API."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import API_BASE, DEFAULT_RETRY_AFTER, REQUEST_TIMEOUT


class ApiError(Exception):
    """Any failure talking to the API."""


class CannotConnect(ApiError):
    """Network error or timeout."""


class InvalidAuth(ApiError):
    """The API key was rejected (401)."""


class InvalidPlate(ApiError):
    """The API rejected the plate (400)."""


class RateLimited(ApiError):
    """Quota used up (429)."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


def normalize_plate(plate: str) -> str:
    """Upper-case and strip spaces and hyphens, like the API does."""
    return "".join(ch for ch in str(plate).upper() if ch not in " -\t\n")


def _retry_after(headers: Any) -> int:
    try:
        value = int(float(headers.get("Retry-After", "")))
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER
    return max(1, value)


class ElbilstatistikClient:
    """Thin wrapper; the key is only ever sent as a header."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str | None) -> None:
        self._session = session
        self._api_key = api_key or None

    async def _get(
        self, path: str, params: dict[str, str] | None = None
    ) -> dict[str, Any] | None:
        headers = {
            "Accept": "application/json",
            "User-Agent": "HomeAssistant-elbilstatistik/0.1",
        }
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.get(
                    f"{API_BASE}{path}", params=params, headers=headers
                ) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
                    if resp.status == 404:
                        return None
                    if resp.status == 401:
                        raise InvalidAuth
                    if resp.status == 400:
                        raise InvalidPlate
                    if resp.status == 429:
                        raise RateLimited(_retry_after(resp.headers))
                    raise ApiError(f"unexpected HTTP status {resp.status}")
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise CannotConnect(str(err) or type(err).__name__) from err

    async def check_key(self) -> None:
        """One counted call; 404 with a valid key is fine, 401 raises InvalidAuth."""
        await self._get("/vehicles/1")

    async def plate(self, plate: str, fuzzy: bool) -> dict[str, Any] | None:
        """Return the raw API answer, or None when the plate is not found."""
        params = {"fuzzy": "true"} if fuzzy else None
        return await self._get(f"/plates/{quote(plate, safe='')}", params)
