"""Sensors for Aiper devices."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AiperCoordinator
from .entity import AiperEntity


@dataclass(frozen=True, kw_only=True)
class AiperSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[AiperSensorDescription, ...] = (
    AiperSensorDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("battery") or d.get("batteryLevel"),
    ),
    AiperSensorDescription(
        key="work_status",
        translation_key="work_status",
        value_fn=lambda d: d.get("workStatus"),
    ),
    AiperSensorDescription(
        key="error_code",
        translation_key="error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("errorCode"),
    ),
    AiperSensorDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("firmware"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AiperCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        AiperSensor(coordinator, sn, desc)
        for sn in coordinator.data
        for desc in SENSORS
    ]
    async_add_entities(entities)


class AiperSensor(AiperEntity, SensorEntity):
    entity_description: AiperSensorDescription

    def __init__(
        self, coordinator: AiperCoordinator, sn: str, desc: AiperSensorDescription
    ) -> None:
        super().__init__(coordinator, sn)
        self.entity_description = desc
        self._attr_unique_id = f"{sn}_{desc.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.device)
