"""Profile selector for V2C Profiles."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import V2CProfilesConfigEntry
from .api import V2CAuthError, V2CError
from .const import ATTR_DEVICE_ID, ATTR_PROFILE_COUNT
from .coordinator import V2CProfilesCoordinator


async def async_setup_entry(hass, entry: V2CProfilesConfigEntry, async_add_entities):
    """Set up the V2C charging profile select."""
    async_add_entities([V2CProfileSelect(entry)], True)


class V2CProfileSelect(CoordinatorEntity[V2CProfilesCoordinator], SelectEntity):
    """Select the active V2C Cloud charging profile."""

    _attr_has_entity_name = True
    _attr_translation_key = "charge_profile"
    _attr_icon = "mdi:ev-station"

    def __init__(self, entry: V2CProfilesConfigEntry) -> None:
        runtime_data = entry.runtime_data
        super().__init__(runtime_data.coordinator)
        self._client = runtime_data.client
        self._attr_unique_id = f"{self._client.device_id}_charge_profile"

    @property
    def options(self) -> list[str]:
        """Return the live profile names supplied by V2C Cloud."""
        return list(self.coordinator.data.names)

    @property
    def current_option(self) -> str | None:
        """Return the profile that V2C Cloud marks active."""
        return self.coordinator.data.active

    @property
    def extra_state_attributes(self):
        """Expose only non-sensitive synchronization details."""
        return {
            ATTR_DEVICE_ID: self._client.device_id,
            ATTR_PROFILE_COUNT: len(self.coordinator.data.names),
        }

    async def async_select_option(self, option: str) -> None:
        """Activate a profile only after an explicit select action."""
        if option not in self.coordinator.data.names:
            raise HomeAssistantError(f"Unknown V2C profile: {option}")
        try:
            await self._client.async_select_profile(option)
        except V2CAuthError as err:
            raise HomeAssistantError(
                "V2C authentication failed; reconfigure the integration"
            ) from err
        except V2CError as err:
            raise HomeAssistantError("Unable to select the V2C profile") from err

        await self.coordinator.async_request_refresh()
