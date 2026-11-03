"""Configure a local Aqara Studio instance through Home Assistant's UI."""

from typing import Any

import probatio as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    AqaraAuthError,
    AqaraConnectionError,
    AqaraError,
    AqaraResponseError,
    AqaraStudioClient,
    normalize_host,
)
from .const import (
    CONF_CONTACT_POLARITY,
    CONF_ENABLE_BUTTON_EVENTS,
    CONF_ENABLE_CONTROLS,
    CONF_ENABLE_WEBSOCKET,
    CONF_EXCLUDED_DEVICES,
    CONF_GATEWAY_ID,
    CONF_GATEWAY_IDS,
    CONF_INVENTORY_INTERVAL,
    CONF_LEAK_POLARITY,
    CONF_POLL_INTERVAL,
    CONF_RECONCILE_INTERVAL,
    CONF_TOKEN,
    CONTACT_POLARITIES,
    DEFAULT_OPTIONS,
    DOMAIN,
    LEAK_POLARITIES,
)


def _password_selector() -> selector.TextSelector:
    return selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
    )


def _polarity_fields(options: dict[str, Any]) -> dict:
    return {
        vol.Required(
            CONF_CONTACT_POLARITY, default=options[CONF_CONTACT_POLARITY]
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=CONTACT_POLARITIES, translation_key=CONF_CONTACT_POLARITY
            )
        ),
        vol.Required(
            CONF_LEAK_POLARITY, default=options[CONF_LEAK_POLARITY]
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=LEAK_POLARITIES, translation_key=CONF_LEAK_POLARITY
            )
        ),
    }


async def async_validate_connection(
    hass: HomeAssistant, host: str, token: str
) -> dict[str, Any]:
    """Authenticate and identify Studio using an immutable gateway anchor.

    The published API has no Studio UUID. Retaining one gateway deviceId is
    deliberate; names, addresses, and the order of the gateway list are not IDs.
    """
    host = normalize_host(host)
    token = token.strip()
    if not token:
        raise AqaraAuthError("An API token is required")
    client = AqaraStudioClient(async_get_clientsession(hass), host, token)
    gateways = await client.async_get_gateways()
    gateway_ids = sorted(
        {
            gateway["deviceId"]
            for gateway in gateways
            if isinstance(gateway.get("deviceId"), str) and gateway["deviceId"]
        }
    )
    if not gateway_ids:
        raise AqaraResponseError("Studio did not provide a stable gateway identifier")
    # Validate inventory access as well as authentication; an empty inventory is
    # valid and will be discovered later by the coordinator.
    await client.async_get_devices()
    return {
        CONF_HOST: host,
        CONF_TOKEN: token,
        CONF_GATEWAY_ID: gateway_ids[0],
        CONF_GATEWAY_IDS: gateway_ids,
    }


class AqaraStudioConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle initial configuration, credential renewal, and host changes."""

    VERSION = 1

    def __init__(self) -> None:
        self._validated: dict[str, Any] = {}

    @callback
    def _finish_update(
        self, entry: ConfigEntry, updates: dict[str, Any]
    ) -> ConfigFlowResult:
        """Let the entry listener reload once; also recover an unloaded entry."""
        schedule_reload = not entry.update_listeners or all(
            entry.data.get(key) == value for key, value in updates.items()
        )
        result = self.async_update_and_abort(entry, data_updates=updates)
        if schedule_reload:
            self.hass.config_entries.async_schedule_reload(entry.entry_id)
        return result

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AqaraStudioOptionsFlow()

    async def _validate(self, host: str, token: str) -> tuple[dict | None, dict]:
        try:
            return await async_validate_connection(self.hass, host, token), {}
        except ValueError:
            return None, {"host": "invalid_host"}
        except AqaraAuthError:
            return None, {"base": "invalid_auth"}
        except AqaraConnectionError:
            return None, {"base": "cannot_connect"}
        except AqaraResponseError:
            return None, {"base": "unsupported_response"}
        except AqaraError:
            return None, {"base": "cannot_connect"}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            validated, errors = await self._validate(
                user_input[CONF_HOST], user_input[CONF_TOKEN]
            )
            if validated is not None:
                await self.async_set_unique_id(validated[CONF_GATEWAY_ID])
                self._abort_if_unique_id_configured()
                # Also reject hostname aliases and choosing a different anchor
                # from the same multi-gateway Studio inventory.
                discovered = set(validated[CONF_GATEWAY_IDS])
                for entry in self._async_current_entries():
                    known = set(entry.data.get(CONF_GATEWAY_IDS, []))
                    if entry.unique_id in discovered or known & discovered:
                        return self.async_abort(reason="already_configured")
                self._validated = validated
                return await self.async_step_mapping()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_HOST): str,
                        vol.Required(CONF_TOKEN): _password_selector(),
                    }
                ),
                {CONF_HOST: user_input[CONF_HOST]} if user_input else None,
            ),
            errors=errors,
        )

    async def async_step_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Require explicit polarity evidence instead of guessing closed/dry."""
        if user_input is not None:
            return self.async_create_entry(
                title="Aqara Studio", data=self._validated, options=user_input
            )
        return self.async_show_form(
            step_id="mapping", data_schema=vol.Schema(_polarity_fields(DEFAULT_OPTIONS))
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            validated, errors = await self._validate(
                entry.data[CONF_HOST], user_input[CONF_TOKEN]
            )
            if validated is not None:
                if entry.unique_id not in validated[CONF_GATEWAY_IDS]:
                    return self.async_abort(reason="wrong_instance")
                return self._finish_update(
                    entry,
                    {
                        CONF_TOKEN: validated[CONF_TOKEN],
                        CONF_GATEWAY_IDS: validated[CONF_GATEWAY_IDS],
                    },
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): _password_selector()}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            validated, errors = await self._validate(
                user_input[CONF_HOST],
                user_input.get(CONF_TOKEN) or entry.data[CONF_TOKEN],
            )
            if validated is not None:
                if entry.unique_id not in validated[CONF_GATEWAY_IDS]:
                    return self.async_abort(reason="wrong_instance")
                validated[CONF_GATEWAY_ID] = entry.unique_id
                return self._finish_update(entry, validated)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_HOST): str,
                        vol.Optional(CONF_TOKEN): _password_selector(),
                    }
                ),
                {CONF_HOST: entry.data[CONF_HOST]},
            ),
            errors=errors,
        )


class AqaraStudioOptionsFlow(OptionsFlow):
    """Tune transports, explicitly enable controls, or exclude devices."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        options = {**DEFAULT_OPTIONS, **self.config_entry.options}
        errors = {}
        if user_input is not None:
            if user_input[CONF_RECONCILE_INTERVAL] < user_input[CONF_POLL_INTERVAL]:
                errors["base"] = "invalid_intervals"
            else:
                return self.async_create_entry(title="", data=user_input)
        devices = {}
        if coordinator := getattr(self.config_entry, "runtime_data", None):
            devices = {key: device.name for key, device in coordinator.data.items()}
        for device_id in options[CONF_EXCLUDED_DEVICES]:
            devices.setdefault(device_id, device_id)
        fields = _polarity_fields(options)
        for key, minimum, maximum in (
            (CONF_POLL_INTERVAL, 5, 300),
            (CONF_RECONCILE_INTERVAL, 60, 3600),
            (CONF_INVENTORY_INTERVAL, 60, 3600),
        ):
            fields[vol.Required(key, default=options[key])] = vol.All(
                vol.Coerce(int), vol.Range(min=minimum, max=maximum)
            )
        for key in (
            CONF_ENABLE_WEBSOCKET,
            CONF_ENABLE_BUTTON_EVENTS,
            CONF_ENABLE_CONTROLS,
        ):
            fields[vol.Required(key, default=options[key])] = bool
        fields[
            vol.Optional(CONF_EXCLUDED_DEVICES, default=options[CONF_EXCLUDED_DEVICES])
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": key, "label": label}
                    for key, label in sorted(devices.items())
                ],
                multiple=True,
            )
        )
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(fields), errors=errors
        )
