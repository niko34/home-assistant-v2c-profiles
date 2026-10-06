"""Data coordinator for V2C Profiles."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import V2CAuthError, V2CError, V2CProfilesClient, V2CRateLimitError
from .const import (
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    MAX_RATE_LIMIT_BACKOFF_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class V2CProfileSnapshot:
    """Profile names and the profile V2C marks as active."""

    names: tuple[str, ...]
    active: str | None


class V2CProfilesCoordinator(DataUpdateCoordinator[V2CProfileSnapshot]):
    """Keep the select synchronized with V2C Cloud."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: V2CProfilesClient,
        initial_snapshot: V2CProfileSnapshot | None = None,
        async_snapshot_callback: (
            Callable[[V2CProfileSnapshot], Awaitable[None]] | None
        ) = None,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        self.client = client
        self._rate_limit_failures = 0
        self._last_snapshot = initial_snapshot
        self._async_snapshot_callback = async_snapshot_callback

    async def _async_update_data(self) -> V2CProfileSnapshot:
        try:
            profiles = await self.client.async_get_profiles()
        except V2CAuthError as err:
            raise ConfigEntryAuthFailed from err
        except V2CRateLimitError as err:
            self._rate_limit_failures += 1
            fallback_delay = min(
                MAX_RATE_LIMIT_BACKOFF_SECONDS,
                DEFAULT_SCAN_INTERVAL_SECONDS
                * (2 ** min(self._rate_limit_failures, 4)),
            )
            retry_delay = max(
                DEFAULT_SCAN_INTERVAL_SECONDS,
                err.retry_after_seconds or fallback_delay,
            )
            self.update_interval = timedelta(seconds=retry_delay)
            snapshot = self.data or self._last_snapshot
            if snapshot is not None:
                _LOGGER.warning(
                    "V2C Cloud rate limit reached; retaining the last profile "
                    "snapshot and retrying in %s seconds",
                    retry_delay,
                )
                return snapshot
            raise UpdateFailed(
                f"V2C Cloud rate limit reached; retry in {retry_delay} seconds"
            ) from err
        except V2CError as err:
            snapshot = self.data or self._last_snapshot
            if snapshot is not None:
                _LOGGER.warning(
                    "Unable to refresh V2C profiles; retaining the last "
                    "successful profile snapshot: %s",
                    err,
                )
                return snapshot
            raise UpdateFailed(str(err)) from err

        self._rate_limit_failures = 0
        self.update_interval = timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS)
        active = next((profile.name for profile in profiles if profile.active), None)
        snapshot = V2CProfileSnapshot(
            names=tuple(profile.name for profile in profiles), active=active
        )
        self._last_snapshot = snapshot
        if self._async_snapshot_callback is not None:
            await self._async_snapshot_callback(snapshot)
        return snapshot
