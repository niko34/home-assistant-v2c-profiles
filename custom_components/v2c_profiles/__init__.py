"""V2C Profiles custom integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.recorder import get_instance, history
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import V2CProfilesClient
from .const import (
    CONF_API_KEY,
    CONF_CACHED_ACTIVE_PROFILE,
    CONF_CACHED_PROFILES,
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
)
from .coordinator import V2CProfileSnapshot, V2CProfilesCoordinator

PLATFORMS = [Platform.SELECT]
_LOGGER = logging.getLogger(__name__)
_PROFILE_ENTITY_ID = "select.profil_de_charge"


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

    async def async_store_snapshot(snapshot: V2CProfileSnapshot) -> None:
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_CACHED_PROFILES: list(snapshot.names),
                CONF_CACHED_ACTIVE_PROFILE: snapshot.active,
            },
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
    cached_names = entry.data.get(CONF_CACHED_PROFILES)
    initial_snapshot = None
    if isinstance(cached_names, list) and all(
        isinstance(name, str) for name in cached_names
    ):
        cached_active = entry.data.get(CONF_CACHED_ACTIVE_PROFILE)
        initial_snapshot = V2CProfileSnapshot(
            names=tuple(cached_names),
            active=cached_active if isinstance(cached_active, str) else None,
        )
    else:
        restored = hass.states.get(_PROFILE_ENTITY_ID)
        restored_names = restored.attributes.get("options") if restored else None
        if isinstance(restored_names, list) and all(
            isinstance(name, str) for name in restored_names
        ):
            restored_active = restored.state
            initial_snapshot = V2CProfileSnapshot(
                names=tuple(restored_names),
                active=(
                    restored_active
                    if restored_active not in {"unknown", "unavailable"}
                    else None
                ),
            )

    # A restored select may already provide the profile names while its state is
    # unavailable. In that case, still consult recorder history to recover the
    # last genuinely selected profile.
    if (
        (initial_snapshot is None or initial_snapshot.active is None)
        and "recorder" in hass.config.components
    ):
        try:
            state_changes = await get_instance(hass).async_add_executor_job(
                history.get_last_state_changes,
                hass,
                100,
                _PROFILE_ENTITY_ID,
            )
            valid_states = [
                previous_state
                for previous_state in state_changes.get(_PROFILE_ENTITY_ID, [])
                if previous_state.state not in {"unknown", "unavailable"}
                and isinstance(previous_state.attributes.get("options"), list)
                and all(
                    isinstance(name, str)
                    for name in previous_state.attributes["options"]
                )
            ]
            if valid_states:
                previous_state = max(
                    valid_states, key=lambda state: state.last_changed
                )
                initial_snapshot = V2CProfileSnapshot(
                    names=tuple(previous_state.attributes["options"]),
                    active=previous_state.state,
                )
        except Exception:  # noqa: BLE001 - recorder fallback must not block setup
            _LOGGER.warning(
                "Unable to restore the last V2C profile snapshot from history",
                exc_info=True,
            )

    if initial_snapshot is not None and (
        not isinstance(cached_names, list)
        or entry.data.get(CONF_CACHED_ACTIVE_PROFILE) != initial_snapshot.active
    ):
        await async_store_snapshot(initial_snapshot)

    coordinator = V2CProfilesCoordinator(
        hass,
        client,
        initial_snapshot=initial_snapshot,
        async_snapshot_callback=async_store_snapshot,
    )
    if initial_snapshot is None:
        await coordinator.async_config_entry_first_refresh()
    else:
        # Make the entity available immediately from the persisted snapshot.
        # The regular coordinator schedule will refresh it from V2C Cloud later,
        # without allowing a temporary 429 to block integration setup.
        coordinator.async_set_updated_data(initial_snapshot)

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
