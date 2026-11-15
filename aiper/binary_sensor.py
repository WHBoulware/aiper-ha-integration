"""Binary sensors for Aiper devices."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AiperCoordinator
from .entity import AiperEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AiperCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(AiperOnlineSensor(coordinator, sn) for sn in coordinator.data)


class AiperOnlineSensor(AiperEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "online"

    @property
    def unique_id(self) -> str:
        return f"{self._sn}_online"

    @property
    def is_on(self) -> bool:
        return bool(self.device.get("online"))
