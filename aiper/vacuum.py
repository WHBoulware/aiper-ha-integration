"""Vacuum entity for Aiper pool cleaners."""

from __future__ import annotations

from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    WORK_STATUS_CHARGING,
    WORK_STATUS_CLEANING,
    WORK_STATUS_ERROR,
    WORK_STATUS_IDLE,
    WORK_STATUS_PAUSED,
    WORK_STATUS_RETURNING,
)
from .coordinator import AiperCoordinator
from .entity import AiperEntity

# Mapping of recovered workStatus ints -> HA vacuum activity.
_ACTIVITY = {
    WORK_STATUS_IDLE: VacuumActivity.IDLE,
    WORK_STATUS_CLEANING: VacuumActivity.CLEANING,
    WORK_STATUS_CHARGING: VacuumActivity.DOCKED,
    WORK_STATUS_PAUSED: VacuumActivity.PAUSED,
    WORK_STATUS_RETURNING: VacuumActivity.RETURNING,
    WORK_STATUS_ERROR: VacuumActivity.ERROR,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AiperCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(AiperVacuum(coordinator, sn) for sn in coordinator.data)


class AiperVacuum(AiperEntity, StateVacuumEntity):
    """Represents an Aiper robot as a vacuum.

    Control features are advertised but each command only takes effect once
    the MQTT command layer is calibrated (see mqtt.build_command). Until
    then, state reporting works and commands log a clear warning.
    """

    _attr_name = None  # use the device name
    _attr_supported_features = (
        VacuumEntityFeature.START
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.STATE
        | VacuumEntityFeature.BATTERY
    )

    @property
    def unique_id(self) -> str:
        return f"{self._sn}_vacuum"

    @property
    def activity(self) -> VacuumActivity | None:
        status = _coerce_int(self.device.get("workStatus"))
        if status is None:
            return None
        return _ACTIVITY.get(status, VacuumActivity.IDLE)

    @property
    def battery_level(self) -> int | None:
        return _coerce_int(self.device.get("battery") or self.device.get("batteryLevel"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.device
        return {
            "serial_number": self._sn,
            "model": d.get("model"),
            "online": d.get("online"),
            "clean_mode": d.get("cleanMode"),
            "error_code": d.get("errorCode"),
            "firmware": d.get("firmware"),
        }

    async def async_start(self) -> None:
        await self.coordinator.async_send_command(self._sn, "start")

    async def async_stop(self, **kwargs: Any) -> None:
        await self.coordinator.async_send_command(self._sn, "stop")

    async def async_pause(self) -> None:
        await self.coordinator.async_send_command(self._sn, "pause")

    async def async_return_to_base(self, **kwargs: Any) -> None:
        await self.coordinator.async_send_command(self._sn, "recall")


def _coerce_int(val: Any) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
