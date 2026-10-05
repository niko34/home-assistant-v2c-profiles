"""Async V2C Cloud client used by the V2C Profiles integration."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import time
from typing import Any
from urllib.parse import quote

from aiohttp import BasicAuth, ClientError, ClientResponse, ClientSession
from yarl import URL

from .const import (
    FIREBASE_API_KEY,
    FIREBASE_SIGN_IN_URL,
    OAUTH_CLIENT_PASSWORD,
    OAUTH_CLIENT_USERNAME,
    OAUTH_TOKEN_URL,
    PROFILES_URL,
    SERVICE_BASE_URL,
)

REQUEST_TIMEOUT_SECONDS = 20
TOKEN_EXPIRY_MARGIN_SECONDS = 30


class V2CError(Exception):
    """Base exception for V2C Cloud errors."""


class V2CAuthError(V2CError):
    """Raised when V2C rejects a credential."""


class V2CConnectionError(V2CError):
    """Raised when V2C Cloud cannot be reached."""


@dataclass(frozen=True, slots=True)
class V2CProfile:
    """A V2C Cloud charging profile."""

    name: str
    active: bool


RefreshTokenCallback = Callable[[str], Awaitable[None]]


class V2CProfilesClient:
    """Small client for the V2C profile and OAuth endpoints."""

    def __init__(
        self,
        session: ClientSession,
        *,
        device_id: str,
        api_key: str,
        refresh_token: str,
        email: str | None = None,
        password: str | None = None,
        async_refresh_token_callback: RefreshTokenCallback | None = None,
    ) -> None:
        self._session = session
        self.device_id = device_id.strip().upper()
        self._api_key = api_key.strip()
        self._refresh_token = refresh_token.strip()
        self._email = email.strip() if email else None
        self._password = password
        self._async_refresh_token_callback = async_refresh_token_callback
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._refresh_lock = asyncio.Lock()

    @property
    def refresh_token(self) -> str:
        """Return the most recently issued refresh token."""
        return self._refresh_token

    async def async_login(self, email: str, password: str) -> str:
        """Use V2C's Firebase login once, then obtain native V2C OAuth tokens."""
        self._email = email.strip()
        self._password = password
        return await self._async_login_with_stored_credentials()

    async def _async_login_with_stored_credentials(self) -> str:
        """Rebuild OAuth credentials using the stored V2C login."""
        if not self._email or not self._password:
            raise V2CAuthError("V2C login credentials are unavailable")
        try:
            async with self._session.post(
                FIREBASE_SIGN_IN_URL,
                params={"key": FIREBASE_API_KEY},
                json={
                    "email": self._email,
                    "password": self._password,
                    "returnSecureToken": True,
                },
                headers={"Accept": "application/json"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as response:
                await self._raise_for_status(response)
                firebase_payload = await response.json(content_type=None)
        except V2CError:
            raise
        except (ClientError, asyncio.TimeoutError, ValueError) as err:
            raise V2CConnectionError("Unable to authenticate with V2C") from err

        firebase_token = firebase_payload.get("idToken")
        if not isinstance(firebase_token, str) or not firebase_token:
            raise V2CAuthError("V2C login did not return a Firebase token")

        payload = await self._async_request_oauth_token(
            {
                "grant_type": "firebase",
                "firebase_token_id": firebase_token,
            }
        )
        return await self._async_accept_oauth_payload(payload)

    async def async_get_profiles(self) -> list[V2CProfile]:
        """Fetch the dynamic profile list and active state using the API key."""
        try:
            async with self._session.get(
                PROFILES_URL,
                params={"deviceId": self.device_id},
                headers={"apikey": self._api_key, "Accept": "application/json"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as response:
                await self._raise_for_status(response)
                payload = await response.json(content_type=None)
        except V2CError:
            raise
        except (ClientError, asyncio.TimeoutError, ValueError) as err:
            raise V2CConnectionError("Unable to read V2C profiles") from err

        records = self._profile_records(payload)
        profiles: list[V2CProfile] = []
        seen: set[str] = set()
        for record in records:
            if not isinstance(record, dict):
                continue
            name = record.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            clean_name = name.strip()
            if clean_name in seen:
                continue
            seen.add(clean_name)
            profiles.append(
                V2CProfile(name=clean_name, active=record.get("active") is True)
            )

        if not profiles:
            raise V2CError("V2C returned no usable charging profiles")
        return profiles

    async def async_refresh_access_token(self, *, force: bool = False) -> str:
        """Refresh OAuth credentials, persisting a rotated refresh token first."""
        if (
            not force
            and self._access_token
            and time.monotonic() < self._access_token_expires_at
        ):
            return self._access_token

        async with self._refresh_lock:
            if (
                not force
                and self._access_token
                and time.monotonic() < self._access_token_expires_at
            ):
                return self._access_token

            try:
                payload = await self._async_request_oauth_token(
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": self._refresh_token,
                    }
                )
            except V2CAuthError:
                # A crash between server-side rotation and local persistence can
                # invalidate the saved token. Rebuild the OAuth chain once from
                # the V2C login instead of requiring manual intervention.
                return await self._async_login_with_stored_credentials()
            return await self._async_accept_oauth_payload(payload)

    async def _async_request_oauth_token(self, data: dict[str, str]) -> dict[str, Any]:
        """Exchange Firebase or refresh credentials for V2C OAuth tokens."""
        try:
            async with self._session.post(
                OAUTH_TOKEN_URL,
                auth=BasicAuth(OAUTH_CLIENT_USERNAME, OAUTH_CLIENT_PASSWORD),
                data=data,
                headers={"Accept": "application/json"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as response:
                await self._raise_for_status(response)
                payload = await response.json(content_type=None)
        except V2CError:
            raise
        except (ClientError, asyncio.TimeoutError, ValueError) as err:
            raise V2CConnectionError("Unable to obtain a V2C OAuth token") from err
        if not isinstance(payload, dict):
            raise V2CAuthError("V2C returned an invalid OAuth response")
        return payload

    async def _async_accept_oauth_payload(self, payload: dict[str, Any]) -> str:
        """Apply an OAuth response and persist a newly issued refresh token."""
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise V2CAuthError("V2C did not return an access token")

        expires_in = payload.get("expires_in", 300)
        try:
            expires_in_seconds = max(1, int(expires_in))
        except (TypeError, ValueError):
            expires_in_seconds = 300

        rotated_refresh_token = payload.get("refresh_token")
        if isinstance(rotated_refresh_token, str) and rotated_refresh_token:
            token_changed = rotated_refresh_token != self._refresh_token
            self._refresh_token = rotated_refresh_token
            if token_changed and self._async_refresh_token_callback is not None:
                # Persist the rotated token before it is needed for another call.
                await self._async_refresh_token_callback(rotated_refresh_token)

        if not self._refresh_token:
            raise V2CAuthError("V2C did not return a refresh token")

        self._access_token = access_token
        self._access_token_expires_at = time.monotonic() + max(
            1, expires_in_seconds - TOKEN_EXPIRY_MARGIN_SECONDS
        )
        return access_token

    async def async_select_profile(self, profile_name: str) -> None:
        """Activate a profile. This is the integration's only mutating API call."""
        access_token = await self.async_refresh_access_token()
        response = await self._async_put_profile(profile_name, access_token)
        if response.status in (401, 403):
            response.release()
            access_token = await self.async_refresh_access_token(force=True)
            response = await self._async_put_profile(profile_name, access_token)

        try:
            await self._raise_for_status(response)
            await response.read()
        finally:
            response.release()

    async def _async_put_profile(
        self, profile_name: str, access_token: str
    ) -> ClientResponse:
        encoded_device_id = quote(self.device_id, safe="")
        encoded_profile_name = quote(profile_name, safe="")
        url = URL(
            f"{SERVICE_BASE_URL}/device/{encoded_device_id}/personalicepower/v2/"
            f"{encoded_profile_name}",
            encoded=True,
        ).with_query(updateAt=str(int(time.time() * 1000)))
        try:
            return await self._session.put(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                json={},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except (ClientError, asyncio.TimeoutError) as err:
            raise V2CConnectionError("Unable to select V2C profile") from err

    @staticmethod
    async def _raise_for_status(response: ClientResponse) -> None:
        if response.status < 400:
            return
        # Consume the response without ever surfacing tokens or server payloads.
        await response.read()
        if response.status in (400, 401, 403):
            raise V2CAuthError(f"V2C rejected the request ({response.status})")
        raise V2CError(f"V2C request failed ({response.status})")

    @staticmethod
    def _profile_records(payload: Any) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("profiles", "data", "content", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []
