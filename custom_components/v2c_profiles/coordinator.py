"""Data coordinator for V2C Profiles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import V2CAuthError, V2CError, V2CProfilesClient
from .const import DEFAULT_SCAN_INTERVAL_SECONDS, DOMAIN


@dataclass(frozen=True, slots=True)
class V2CProfileSnapshot:
    """Profile names and the profile V2C marks as active."""

    names: tuple[str, ...]
    active: str | None


class V2CProfilesCoordinator(DataUpdateCoordinator[V2CProfileSnapshot]):
    """Keep the select synchronized with V2C Cloud."""

    def __init__(self, hass: HomeAssistant, client: V2CProfilesClient) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        self.client = client

    async def _async_update_data(self) -> V2CProfileSnapshot:
        try:
            profiles = await self.client.async_get_profiles()
        except V2CAuthError as err:
            raise ConfigEntryAuthFailed from err
        except V2CError as err:
            raise UpdateFailed(str(err)) from err

        active = next((profile.name for profile in profiles if profile.active), None)
        return V2CProfileSnapshot(
            names=tuple(profile.name for profile in profiles), active=active
        )
