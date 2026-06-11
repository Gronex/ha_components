DOMAIN = "eloverblik"


async def async_setup(hass, config):
    hass.states.async_set("hello_state.world", "Paulus")

    return True
