"""Constants for V2C Profiles."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "v2c_profiles"

CONF_API_KEY: Final = "api_key"
CONF_DEVICE_ID: Final = "device_id"
CONF_EMAIL: Final = "email"
CONF_PASSWORD: Final = "password"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_CACHED_PROFILES: Final = "cached_profiles"
CONF_CACHED_ACTIVE_PROFILE: Final = "cached_active_profile"

DEFAULT_DEVICE_ID: Final = "QQAE61"
DEFAULT_SCAN_INTERVAL_SECONDS: Final = 300
MAX_RATE_LIMIT_BACKOFF_SECONDS: Final = 3600

OAUTH_TOKEN_URL: Final = "https://v2c.cloud/v2cauth/oauth/token"
FIREBASE_SIGN_IN_URL: Final = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
)
FIREBASE_API_KEY: Final = "AIzaSyAeg7cQsdn0DN68NZq0_478fq7OQVouGKU"
PROFILES_URL: Final = (
    "https://v2c.cloud/kong/v2c_service/device/personalicepower/all"
)
SERVICE_BASE_URL: Final = "https://v2c.cloud/v2cservice/api/v1"

OAUTH_CLIENT_USERNAME: Final = "cloud@v2c.com"
OAUTH_CLIENT_PASSWORD: Final = "1234"

ATTR_PROFILE_COUNT: Final = "profile_count"
ATTR_DEVICE_ID: Final = "device_id"
