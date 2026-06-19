"""Config flow for the Eloverblik integration."""

from collections.abc import Mapping
import logging
from typing import Any, override

import httpx
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import create_async_httpx_client
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CONF_ENABLE_PRODUCTION, CONF_REFRESH_TOKEN, DOMAIN
from .energinet.client import (
    BASE_URL,
    DEFAULT_TIMEOUT,
    EnerginetAuthError,
    EnerginetClient,
)
from .energinet.models import MeteringPoint

_LOGGER = logging.getLogger(__name__)


def _user_schema(defaults: Mapping[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_REFRESH_TOKEN,
                description={"suggested_value": defaults.get(CONF_REFRESH_TOKEN, "")},
            ): TextSelector(
                TextSelectorConfig(
                    type=TextSelectorType.PASSWORD,
                    autocomplete="off",
                )
            ),
            vol.Required(
                CONF_ENABLE_PRODUCTION,
                default=bool(defaults.get(CONF_ENABLE_PRODUCTION, False)),
            ): bool,
        }
    )


async def _validate_token(
    hass: HomeAssistant, refresh_token: str
) -> list[MeteringPoint]:
    """Validate the refresh token by opening the client and listing meters.

    Raises _InvalidAuth on authentication failure and _CannotConnect on
    network errors; returns the list of metering points otherwise.
    """
    client = EnerginetClient(
        refresh_token,
        client=create_async_httpx_client(
            hass, base_url=BASE_URL, timeout=DEFAULT_TIMEOUT
        ),
    )
    try:
        await client.open()
        points = await client.async_get_metering_points()
    except EnerginetAuthError as err:
        raise _InvalidAuth from err
    except httpx.HTTPError as err:
        raise _CannotConnect from err
    finally:
        await client.close()
    return points


class _InvalidAuth(Exception):
    """The supplied refresh token was rejected."""


class _CannotConnect(Exception):
    """A network/transport error occurred while validating."""


class EloverblikConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Eloverblik."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step asking for the refresh token and production toggle."""
        errors: dict[str, str] = {}

        if user_input is not None:
            refresh_token = user_input[CONF_REFRESH_TOKEN].strip()
            self._data = {
                CONF_REFRESH_TOKEN: refresh_token,
                CONF_ENABLE_PRODUCTION: bool(
                    user_input.get(CONF_ENABLE_PRODUCTION, False)
                ),
            }

            self._async_abort_entries_match(
                {CONF_REFRESH_TOKEN: self._data[CONF_REFRESH_TOKEN]}
            )

            try:
                points = await _validate_token(self.hass, refresh_token)
            except _InvalidAuth:
                errors["base"] = "invalid_auth"
            except _CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating Eloverblik token")
                errors["base"] = "unknown"
            else:
                unique_id = points[0].metering_point_id if points else refresh_token
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Eloverblik",
                    data=self._data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _user_schema(self._data), user_input or {}
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Trigger reauth flow when the token stops working."""
        reauth_entry = self._get_reauth_entry()
        self._data = dict(reauth_entry.data)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new refresh token."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            refresh_token = user_input[CONF_REFRESH_TOKEN].strip()
            try:
                await _validate_token(self.hass, refresh_token)
            except _InvalidAuth:
                errors["base"] = "invalid_auth"
            except _CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating Eloverblik token")
                errors["base"] = "unknown"
            else:
                data = {**reauth_entry.data, CONF_REFRESH_TOKEN: refresh_token}
                return self.async_update_reload_and_abort(reauth_entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_REFRESH_TOKEN): TextSelector(
                            TextSelectorConfig(
                                type=TextSelectorType.PASSWORD,
                                autocomplete="off",
                            )
                        )
                    }
                ),
                {},
            ),
            errors=errors,
            description_placeholders={"name": reauth_entry.title},
        )
