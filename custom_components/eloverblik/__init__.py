"""The Eloverblik (Energinet) integration.

Sets up a DataUpdateCoordinator that pulls metering data from the Eloverblik
customer API, inserts it into Home Assistant statistics, and forwards the
sensor platform which exposes live energy entities for the Energy dashboard.
"""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN as DOMAIN
from .coordinator import EloverblikConfigEntry, EloverblikCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: EloverblikConfigEntry) -> bool:
    """Set up Eloverblik from a config entry."""
    coordinator = EloverblikCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EloverblikConfigEntry) -> bool:
    """Unload an Eloverblik config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await entry.runtime_data.async_ws_close()
    return unload_ok
