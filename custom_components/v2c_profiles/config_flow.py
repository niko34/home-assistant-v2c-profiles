"""Config flow for V2C Profiles."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import V2CAuthError, V2CConnectionError, V2CError, V2CProfilesClient
from .const import (
    CONF_API_KEY,
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    DEFAULT_DEVICE_ID,
    DOMAIN,
)


def _secret_text_selector() -> selector.TextSelector:
    return selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
    )


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_DEVICE_ID,
                default=defaults.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID),
            ): selector.TextSelector(),
            vol.Required(CONF_API_KEY): _secret_text_selector(),
            vol.Required(CONF_EMAIL): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
            ),
            vol.Required(CONF_PASSWORD): _secret_text_selector(),
        }
    )


async def _async_validate_and_rotate(
    hass,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Validate read-only access first, then rotate OAuth exactly once."""
    client = V2CProfilesClient(
        async_get_clientsession(hass),
        device_id=data[CONF_DEVICE_ID],
        api_key=data[CONF_API_KEY],
        refresh_token="",
    )
    # This read has no effect on the charger and validates the device/API key.
    await client.async_get_profiles()
    # Do this last. Credentials are persisted only after the OAuth exchange succeeds.
    await client.async_login(data[CONF_EMAIL], data[CONF_PASSWORD])
    return {
        CONF_DEVICE_ID: client.device_id,
        CONF_API_KEY: data[CONF_API_KEY].strip(),
        CONF_EMAIL: data[CONF_EMAIL].strip(),
        CONF_PASSWORD: data[CONF_PASSWORD],
        CONF_REFRESH_TOKEN: client.refresh_token,
    }


class V2CProfilesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle V2C Profiles configuration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = await _async_validate_and_rotate(self.hass, user_input)
            except V2CAuthError:
                errors["base"] = "invalid_auth"
            except V2CConnectionError:
                errors["base"] = "cannot_connect"
            except V2CError:
                errors["base"] = "unknown"
            except Exception:  # noqa: BLE001 - config flows must fail safely
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(data[CONF_DEVICE_ID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"V2C {data[CONF_DEVICE_ID]}", data=data
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Start credential replacement after an authentication failure."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Validate and persist replacement credentials."""
        entry = self._reauth_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            submitted = {
                CONF_DEVICE_ID: entry.data[CONF_DEVICE_ID],
                CONF_API_KEY: user_input[CONF_API_KEY],
                CONF_EMAIL: user_input[CONF_EMAIL],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            try:
                data = await _async_validate_and_rotate(self.hass, submitted)
            except V2CAuthError:
                errors["base"] = "invalid_auth"
            except V2CConnectionError:
                errors["base"] = "cannot_connect"
            except V2CError:
                errors["base"] = "unknown"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(entry, data=data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): _secret_text_selector(),
                    vol.Required(CONF_EMAIL): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
                    ),
                    vol.Required(CONF_PASSWORD): _secret_text_selector(),
                }
            ),
            errors=errors,
            description_placeholders={"device_id": entry.data[CONF_DEVICE_ID]},
        )
