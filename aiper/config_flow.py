"""Config flow for Aiper Pool Cleaner."""

from __future__ import annotations

import uuid
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AiperApiClient, AiperApiError, AiperAuthError
from .const import (
    API_HOSTS,
    CONF_ACCESS_TOKEN,
    CONF_APP_VERSION,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_USE_MQTT,
    DEFAULT_APP_VERSION,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)


class AiperConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Aiper."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            device_id = str(uuid.uuid4()).upper()
            session = async_get_clientsession(self.hass)
            client = AiperApiClient(
                session,
                user_input[CONF_REGION],
                device_id=device_id,
                app_version=user_input.get(CONF_APP_VERSION, DEFAULT_APP_VERSION),
            )
            try:
                await client.login(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            except AiperAuthError:
                errors["base"] = "invalid_auth"
            except AiperApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME],
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_REGION: user_input[CONF_REGION],
                        CONF_APP_VERSION: user_input.get(
                            CONF_APP_VERSION, DEFAULT_APP_VERSION
                        ),
                        CONF_DEVICE_ID: device_id,
                        CONF_ACCESS_TOKEN: client.access_token,
                        CONF_REFRESH_TOKEN: client.refresh_token,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_REGION, default=DEFAULT_REGION): vol.In(
                    list(API_HOSTS)
                ),
                vol.Optional(CONF_APP_VERSION, default=DEFAULT_APP_VERSION): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return AiperOptionsFlow(entry)


class AiperOptionsFlow(OptionsFlow):
    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self.entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(int, vol.Range(min=15, max=3600)),
                vol.Optional(
                    CONF_USE_MQTT,
                    default=self.entry.options.get(CONF_USE_MQTT, True),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
