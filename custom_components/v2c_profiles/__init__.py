"""V2C Profiles custom integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import V2CProfilesClient
from .const import (
    CONF_API_KEY,
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
)
from .coordinator import V2CProfilesCoordinator

PLATFORMS = [Platform.SELECT]


@dataclass(slots=True)
class V2CProfilesRuntimeData:
    """Runtime objects for a V2C Profiles config entry."""

    client: V2CProfilesClient
    coordinator: V2CProfilesCoordinator


V2CProfilesConfigEntry = ConfigEntry[V2CProfilesRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant, entry: V2CProfilesConfigEntry
) -> bool:
    """Set up V2C Profiles from a config entry."""

    async def async_store_rotated_refresh_token(refresh_token: str) -> None:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_REFRESH_TOKEN: refresh_token},
        )

    client = V2CProfilesClient(
        async_get_clientsession(hass),
        device_id=entry.data[CONF_DEVICE_ID],
        api_key=entry.data[CONF_API_KEY],
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        email=entry.data.get(CONF_EMAIL),
        password=entry.data.get(CONF_PASSWORD),
        async_refresh_token_callback=async_store_rotated_refresh_token,
    )
    coordinator = V2CProfilesCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = V2CProfilesRuntimeData(
        client=client, coordinator=coordinator
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: V2CProfilesConfigEntry
) -> bool:
    """Unload a V2C Profiles config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
