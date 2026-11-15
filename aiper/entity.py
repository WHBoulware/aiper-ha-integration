"""Base entity for Aiper devices."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AiperCoordinator


class AiperEntity(CoordinatorEntity[AiperCoordinator]):
    """Common base: ties an entity to one device serial number."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AiperCoordinator, sn: str) -> None:
        super().__init__(coordinator)
        self._sn = sn

    @property
    def device(self) -> dict[str, Any]:
        return self.coordinator.data.get(self._sn, {})

    @property
    def available(self) -> bool:
        return super().available and bool(self.device)

    @property
    def device_info(self) -> DeviceInfo:
        dev = self.device
        return DeviceInfo(
            identifiers={(DOMAIN, self._sn)},
            name=dev.get("name") or self._sn,
            manufacturer="Aiper",
            model=dev.get("model"),
            sw_version=dev.get("firmware"),
            serial_number=self._sn,
        )
