"""Sensor platform for the Eloverblik integration.

Exposes one energy sensor per relevant metering point. Consumption meters
(E17) feed the Energy dashboard's "Grid consumption"; production meters (E18),
when enabled, feed "Return to grid". Long-term history is delivered via the
statistics inserted by the coordinator.
"""

from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EloverblikConfigEntry, EloverblikCoordinator, MeterData

_PARALLEL_UPDATES = 0


def _meter_device(meter: MeterData) -> DeviceInfo:
    """Build device info for a metering point."""
    return DeviceInfo(
        identifiers={(DOMAIN, meter.metering_point_id)},
        name=meter.name,
        manufacturer="Energinet",
        model="Production meter" if meter.is_production else "Consumption meter",
        serial_number=meter.metering_point_id,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EloverblikConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Eloverblik sensors from a config entry."""
    coordinator = entry.runtime_data
    created: set[str] = set()

    @callback
    def _sync_entities() -> None:
        """Add sensors for any metering points not yet represented."""
        data = coordinator.data
        new_entities: list[EloverblikSensor] = []
        for meter in data.meters.values():
            if meter.metering_point_id in created:
                continue
            created.add(meter.metering_point_id)
            new_entities.append(EloverblikSensor(coordinator, meter))
        if new_entities:
            async_add_entities(new_entities)

    _sync_entities()
    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))


# CoordinatorEntity.available is a @property while Entity.available (inherited
# via SensorEntity) is a propcache cached_property in HA 2026.x, so pyright
# flags the MRO as incompatible. The conflict lives entirely in HA's base
# classes (same pattern as the built-in opower integration), hence the ignore.
class EloverblikSensor(  # type: ignore[reportIncompatibleVariableOverride]
    CoordinatorEntity[EloverblikCoordinator], SensorEntity
):
    """A single energy sensor for an Eloverblik metering point."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_has_entity_name = True
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: EloverblikCoordinator, meter: MeterData) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._meter_id = meter.metering_point_id
        self._attr_unique_id = f"{meter.metering_point_id}_energy"
        self._attr_device_info = _meter_device(meter)
        self.entity_description = SensorEntityDescription(
            key=f"{meter.metering_point_id}_energy",
            translation_key=(
                "energy_production" if meter.is_production else "energy_consumption"
            ),
        )
        self._update_native_value()

    @override
    @callback
    def _handle_coordinator_update(self) -> None:
        """Push the latest coordinator data into the sensor, then write state."""
        self._update_native_value()
        super()._handle_coordinator_update()

    @callback
    def _update_native_value(self) -> None:
        """Compute the latest cumulative energy total from coordinator data."""
        meter = self.coordinator.data.meters.get(self._meter_id)
        self._attr_native_value = meter.latest_sum if meter else None
