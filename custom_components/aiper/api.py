"""Aiper cloud REST client.

Implements the authentication, device discovery and status flow recovered
from the iOS app. This is the "cloud polling" path, which is enough to
expose devices, battery, online state and work status in Home Assistant.

Realtime control (start/stop/recall) goes through AWS IoT MQTT and is
handled in ``mqtt.py``; the command *payloads* need one live capture to
confirm (see tools/capture_guide.md).
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import aiohttp

from .const import (
    API_HOSTS,
    CLIENT_SOURCE,
    DEFAULT_APP_VERSION,
    EP_GET_EQUIPMENT,
    EP_GET_FAMILY_ALL,
    EP_GET_OPENID_TOKEN,
    EP_LOGIN,
    EP_TOKEN_REFRESH,
    ENV_CONTENT,
    HEADER_APP_VERSION,
    HEADER_DEVICE_ID,
    HEADER_LANGUAGE,
    HEADER_TIMESTAMP,
    HEADER_ZONE_ID,
)
from .crypto import decrypt_content, encrypt_payload

_LOGGER = logging.getLogger(__name__)


class AiperAuthError(Exception):
    """Raised when login/refresh fails."""


class AiperApiError(Exception):
    """Raised on a non-success API response."""


class AiperApiClient:
    """Minimal async client for the Aiper regional cloud API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        region: str,
        *,
        device_id: str | None = None,
        app_version: str = DEFAULT_APP_VERSION,
        access_token: str | None = None,
        refresh_token: str | None = None,
        language: str = "en",
    ) -> None:
        self._session = session
        self._host = API_HOSTS[region]
        self._device_id = device_id or str(uuid.uuid4()).upper()
        self._app_version = app_version
        self._language = language
        self.access_token = access_token
        self.refresh_token = refresh_token

    # -- public properties --------------------------------------------------
    @property
    def device_id(self) -> str:
        return self._device_id

    # -- low level ----------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            HEADER_DEVICE_ID: self._device_id,
            HEADER_LANGUAGE: self._language,
            "Accept-Language": self._language,
            HEADER_APP_VERSION: self._app_version,
            HEADER_TIMESTAMP: str(int(time.time() * 1000)),
            HEADER_ZONE_ID: "0",
            "source": CLIENT_SOURCE,
        }
        if self.access_token:
            # The app carries the bearer token in a `token` header; some
            # builds also accept Authorization. We send both to be safe.
            headers["token"] = self.access_token
            headers["Authorization"] = self.access_token
        return headers

    async def _post(
        self, endpoint: str, body: dict[str, Any], *, encrypt: bool = True
    ) -> dict[str, Any]:
        url = self._host + endpoint
        if encrypt:
            envelope, aes_key = encrypt_payload(body)
            payload: dict[str, Any] = envelope
        else:
            payload, aes_key = body, None

        async with self._session.post(
            url, json=payload, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            text = await resp.text()
            _LOGGER.debug("Aiper %s -> HTTP %s: %s", endpoint, resp.status, text[:500])
            if resp.status != 200:
                _LOGGER.warning(
                    "Aiper %s failed: HTTP %s from %s: %s",
                    endpoint, resp.status, url, text[:500],
                )
                raise AiperApiError(f"{endpoint} -> HTTP {resp.status}: {text[:200]}")
            data = _loads(text)

        # The response may itself be enveloped (encrypted `content`).
        if aes_key is not None and isinstance(data, dict) and ENV_CONTENT in data \
                and "code" not in data:
            data = decrypt_content(aes_key, data[ENV_CONTENT])

        # Standard envelope: {"code": ..., "success": bool, "data": {...}, "message": str}
        code = data.get("code")
        success = data.get("success", code in (0, 200, "0", "200", None))
        if not success:
            msg = data.get("message") or data.get("msg") or "unknown error"
            _LOGGER.warning(
                "Aiper %s rejected: code=%s message=%s full=%s",
                endpoint, code, msg, str(data)[:500],
            )
            if code in (401, 403, 1001, 1002):
                raise AiperAuthError(f"{endpoint}: {msg} (code {code})")
            raise AiperApiError(f"{endpoint}: {msg} (code {code})")
        return data.get("data", data)

    # -- auth ---------------------------------------------------------------
    async def login(self, account: str, password: str) -> dict[str, Any]:
        """Log in with email/username + password.

        Field names (`account`, `password`) and the endpoint come from the
        app's login module. If your capture shows a hashed password or extra
        fields, adjust here.
        """
        body = {
            "account": account,
            "password": password,
            "source": CLIENT_SOURCE,
            "deviceId": self._device_id,
        }
        data = await self._post(EP_LOGIN, body)
        self._store_tokens(data)
        if not self.access_token:
            raise AiperAuthError("login succeeded but no token in response")
        return data

    async def refresh(self) -> None:
        if not self.refresh_token:
            raise AiperAuthError("no refresh token")
        data = await self._post(
            EP_TOKEN_REFRESH, {"refreshToken": self.refresh_token}
        )
        self._store_tokens(data)

    def _store_tokens(self, data: dict[str, Any]) -> None:
        # Token field names vary by build; accept the common spellings.
        for key in ("token", "accessToken", "access_token"):
            if data.get(key):
                self.access_token = data[key]
                break
        for key in ("refreshToken", "refresh_token"):
            if data.get(key):
                self.refresh_token = data[key]
                break

    async def _post_auth(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST, transparently refreshing the token once on auth failure."""
        try:
            return await self._post(endpoint, body)
        except AiperAuthError:
            await self.refresh()
            return await self._post(endpoint, body)

    # -- discovery / status -------------------------------------------------
    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Return a flat list of the user's equipment.

        Tries the family tree first (newer app flow) and falls back to the
        flat equipment list. Each item is normalised to a common shape.
        """
        devices: list[dict[str, Any]] = []
        try:
            fam = await self._post_auth(EP_GET_FAMILY_ALL, {})
            devices = _flatten_family(fam)
        except AiperApiError as err:
            _LOGGER.debug("family tree unavailable (%s), using equipment list", err)

        if not devices:
            data = await self._post_auth(EP_GET_EQUIPMENT, {})
            raw = data if isinstance(data, list) else data.get("list", [])
            devices = [_normalise_device(d) for d in raw]

        return devices

    async def async_get_iot_model(self) -> dict[str, Any]:
        """Fetch the AWS IoT connection model (endpoint + Cognito identity).

        Returned to mqtt.py so it can open a Cognito-signed WebSocket.
        """
        return await self._post_auth(EP_GET_OPENID_TOKEN, {})


def _loads(text: str) -> dict[str, Any]:
    import json

    try:
        return json.loads(text) if text else {}
    except ValueError:
        return {"raw": text}


def _normalise_device(d: dict[str, Any]) -> dict[str, Any]:
    sn = d.get("deviceSn") or d.get("sn") or d.get("deviceId")
    return {
        "sn": sn,
        "name": d.get("deviceName") or d.get("nickName") or sn,
        "model": d.get("deviceModel") or d.get("productModel") or d.get("model"),
        "ble_name": d.get("bleName"),
        "firmware": d.get("firmwareVersion") or d.get("mainVersion"),
        "online": _as_bool(d.get("onlineStatus")),
        "place_id": d.get("placeId"),
        "raw": d,
    }


def _flatten_family(fam: Any) -> list[dict[str, Any]]:
    """Walk family -> place -> equipment and return normalised devices."""
    out: list[dict[str, Any]] = []
    families = fam if isinstance(fam, list) else fam.get("list", []) or fam.get("familyList", [])
    for family in families or []:
        for place in family.get("placeList", []) or family.get("places", []) or []:
            for dev in place.get("equipmentList", []) or place.get("deviceList", []) or []:
                out.append(_normalise_device(dev))
    return out


def _as_bool(val: Any) -> bool:
    return str(val) in ("1", "true", "True", "online", "ONLINE")
