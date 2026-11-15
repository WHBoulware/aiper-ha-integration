"""Data update coordinator for Aiper."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AiperApiClient, AiperAuthError, AiperApiError
from .const import DOMAIN
from .mqtt import AiperMqtt

_LOGGER = logging.getLogger(__name__)


class AiperCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls the Aiper cloud and, when possible, augments with live MQTT state."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: AiperApiClient,
        scan_interval: int,
        use_mqtt: bool,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.entry = entry
        self.client = client
        self._use_mqtt = use_mqtt
        self._mqtt: AiperMqtt | None = None
        # live state pushed by MQTT, merged over the polled snapshot
        self._live: dict[str, dict[str, Any]] = {}
        self.devices: dict[str, dict[str, Any]] = {}

    async def _async_setup(self) -> None:
        """Discover devices once, then optionally bring up MQTT."""
        devices = await self.client.async_get_devices()
        self.devices = {d["sn"]: d for d in devices if d.get("sn")}

        if self._use_mqtt:
            try:
                iot_model = await self.client.async_get_iot_model()
                self._mqtt = AiperMqtt(iot_model)
                if await self._mqtt.async_connect():
                    for sn in self.devices:
                        self._mqtt.subscribe_device(sn, self._on_live_state)
                else:
                    self._mqtt = None
            except (AiperApiError, AiperAuthError) as err:
                _LOGGER.warning("Could not start MQTT (%s); poll-only", err)
                self._mqtt = None

    def _on_live_state(self, topic: str, state: dict[str, Any]) -> None:
        """Merge a pushed MQTT state update and notify entities."""
        # topic ends with the device sn segment; find which device
        for sn in self.devices:
            if sn in topic:
                self._live.setdefault(sn, {}).update(state)
                merged = dict(self.data or {})
                merged.setdefault(sn, {}).update(self._live[sn])
                self.async_set_updated_data(merged)
                break

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            devices = await self.client.async_get_devices()
        except AiperAuthError as err:
            raise UpdateFailed(f"auth failed: {err}") from err
        except AiperApiError as err:
            raise UpdateFailed(str(err)) from err

        self.devices = {d["sn"]: d for d in devices if d.get("sn")}
        snapshot: dict[str, dict[str, Any]] = {}
        for sn, dev in self.devices.items():
            merged = dict(dev)
            # overlay any live MQTT state we have
            merged.update(self._live.get(sn, {}))
            snapshot[sn] = merged
        return snapshot

    async def async_send_command(self, sn: str, command: str, **params: Any) -> bool:
        """Send a control command, MQTT first, REST fallback where it exists."""
        if self._mqtt and self._mqtt.publish_command(sn, command, params):
            await self.async_request_refresh()
            return True
        _LOGGER.warning(
            "Command '%s' for %s could not be sent (command layer not "
            "calibrated or MQTT unavailable).",
            command,
            sn,
        )
        return False

    async def async_shutdown(self) -> None:
        if self._mqtt:
            await self._mqtt.async_disconnect()
        await super().async_shutdown()
