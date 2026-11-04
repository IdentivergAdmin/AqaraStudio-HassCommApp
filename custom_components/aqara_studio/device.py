"""Validated Aqara data model and conservative capability discovery.

Mappings are from Aqara's published data-model specification. Contact and leak
polarity are deliberately user-confirmed: the specification defines a boolean,
but does not say which boolean means open/wet. No default is inferred from a
missing value, a model name, or Matter's separate data model.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote


def strict_bool(value: Any) -> bool | None:
    """Accept only actual boolean representations, never Python truthiness."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.casefold().strip()
        if normalized in ("true", "1"):
            return True
        if normalized in ("false", "0"):
            return False
    return None


def finite_number(value: Any) -> float | None:
    """Decode a finite API number, rejecting booleans and empty values."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError, OverflowError:
        return None
    return number if math.isfinite(number) else None


@dataclass(frozen=True, order=True)
class TraitKey:
    """A stable, endpoint-specific trait address."""

    device_id: str
    endpoint_id: int
    function_code: str
    trait_code: str

    def as_dict(self) -> dict[str, Any]:
        """Return the documented Aqara address, without a value."""
        return {
            "deviceId": self.device_id,
            "endpointId": self.endpoint_id,
            "functionCode": self.function_code,
            "traitCode": self.trait_code,
        }

    def unique_id(self, studio_id: str) -> str:
        """Escape separators so identifiers cannot accidentally collide."""
        return ":".join(
            quote(str(value), safe="")
            for value in (
                studio_id,
                self.device_id,
                self.endpoint_id,
                self.function_code,
                self.trait_code,
            )
        )


@dataclass
class Trait:
    """An advertised trait and its last observed value."""

    key: TraitKey
    parameter: dict[str, Any]
    value: Any = None
    time: int | None = None
    endpoint_name: str = ""
    endpoint_type: str = ""

    @property
    def readable(self) -> bool:
        """Missing access flags never grant access."""
        return self.parameter.get("readable") is True

    @property
    def writable(self) -> bool:
        """Require an explicitly advertised write flag."""
        return self.parameter.get("writable") is True

    @property
    def subscribable(self) -> bool:
        """Require an explicitly advertised subscription flag."""
        return self.parameter.get("subscribable") is True


@dataclass
class StudioDevice:
    """A physical device; display names never participate in identity."""

    device_id: str
    name: str
    gateway_id: str | None = None
    model: str | None = None
    manufacturer: str | None = None
    firmware: str | None = None
    device_types: tuple[str, ...] = ()
    traits: dict[TraitKey, Trait] = field(default_factory=dict)
    present: bool = True
    inventory_online: bool | None = None

    @property
    def reachable(self) -> bool | None:
        """Prefer explicit Reachable evidence over inventory fallback.

        A malformed advertised Reachable is unknown, not silently online.
        Multiple endpoints are conservative: any explicit offline wins.
        """
        evidence = [
            strict_bool(trait.value)
            for key, trait in self.traits.items()
            if (key.function_code, key.trait_code) == ("BasicInformation", "Reachable")
        ]
        if evidence:
            if False in evidence:
                return False
            return True if all(value is True for value in evidence) else None
        return self.inventory_online


def parse_device(
    record: Mapping[str, Any], definition: Mapping[str, Any]
) -> StudioDevice:
    """Parse one inventory record and definition, tolerating partial metadata.

    Invalid nested points are skipped. Duplicate addresses are merged in place;
    absent values do not erase an earlier value from the same response. A
    conflicting duplicate is retained as unknown rather than choosing a safe
    state arbitrarily.
    """
    device_id = definition.get("deviceId") or record.get("deviceId")
    if not isinstance(device_id, str) or not device_id:
        raise ValueError("Device has no stable identifier")
    if record.get("deviceId") not in (None, device_id):
        raise ValueError("Inventory and definition device identifiers differ")
    device_types = definition.get("deviceTypesList", record.get("deviceTypesList", []))
    if not isinstance(device_types, list):
        device_types = []
    name = record.get("deviceName") or definition.get("name")
    gateway = definition.get("gatewayId", record.get("gatewayId"))
    model = record.get("model")
    device = StudioDevice(
        device_id=device_id,
        name=name if isinstance(name, str) and name else "Aqara device",
        gateway_id=gateway if isinstance(gateway, str) and gateway else None,
        model=model if isinstance(model, str) and model else None,
        device_types=tuple(item for item in device_types if isinstance(item, str)),
        inventory_online=strict_bool(record.get("state")),
    )
    endpoints = definition.get("endpoints", [])
    if not isinstance(endpoints, list):
        return device
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        endpoint_id = endpoint.get("endpointId")
        if isinstance(endpoint_id, bool) or not isinstance(endpoint_id, int):
            continue
        functions = endpoint.get("functions", [])
        if not isinstance(functions, list):
            continue
        for function in functions:
            if not isinstance(function, dict):
                continue
            function_code = function.get("functionCode")
            if not isinstance(function_code, str) or not function_code:
                continue
            traits = function.get("traits", [])
            if not isinstance(traits, list):
                continue
            for raw_trait in traits:
                if not isinstance(raw_trait, dict):
                    continue
                trait_code = raw_trait.get("traitCode")
                parameter = raw_trait.get("parameter")
                if (
                    not isinstance(trait_code, str)
                    or not trait_code
                    or not isinstance(parameter, dict)
                ):
                    continue
                key = TraitKey(device_id, endpoint_id, function_code, trait_code)
                stamp = raw_trait.get("time")
                trait = Trait(
                    key=key,
                    parameter=dict(parameter),
                    value=raw_trait.get("value"),
                    time=stamp
                    if isinstance(stamp, int) and not isinstance(stamp, bool)
                    else None,
                    endpoint_name=endpoint.get("endpointName", "")
                    if isinstance(endpoint.get("endpointName"), str)
                    else "",
                    endpoint_type=endpoint.get("deviceType", "")
                    if isinstance(endpoint.get("deviceType"), str)
                    else "",
                )
                if prior := device.traits.get(key):
                    if "value" in raw_trait and prior.value != trait.value:
                        prior.value = None
                    # Never let duplicate definitions escalate access.
                    for flag in ("readable", "writable", "subscribable"):
                        prior.parameter[flag] = (
                            prior.parameter.get(flag) is True
                            and trait.parameter.get(flag) is True
                        )
                    continue
                device.traits[key] = trait
                if function_code == "BasicInformation" and isinstance(trait.value, str):
                    if trait_code in {"FirmwareRevision", "FirmwareRevisionString"}:
                        device.firmware = trait.value
                    elif trait_code == "VendorName":
                        device.manufacturer = trait.value
                    elif trait_code == "ModelValue":
                        device.model = trait.value
    return device


@dataclass(frozen=True)
class Capability:
    """A useful Home Assistant entity supported by one primary trait."""

    key: TraitKey
    platform: str
    name: str
    kind: str
    device_class: str | None = None
    unit: str | None = None
    scale: float = 1.0
    minimum: float | None = None
    maximum: float | None = None
    diagnostic: bool = False
    enabled_default: bool = True
    brightness_key: TraitKey | None = None
    color_temp_key: TraitKey | None = None
    xy_color_key: TraitKey | None = None
    color_mode_key: TraitKey | None = None


# Unit aliases are formats seen in the official data model, not unit guesses
# based on a value's magnitude. Missing units use the specification's units.
_SENSORS: dict[tuple[str, str], tuple[str, str, str, float | None, float | None]] = {
    ("Temperature", "CurrentTemperature"): (
        "Temperature",
        "temperature",
        "°C",
        -273.15,
        None,
    ),
    ("RelativeHumidity", "CurrentHumidity"): ("Humidity", "humidity", "%", 0, 100),
    ("PowerSource", "BatPercentRemaining"): ("Battery", "battery", "%", 0, 100),
    ("PowerSource", "CurrentVoltage"): ("Supply voltage", "voltage", "V", 0, None),
    ("Illuminance", "CurrentIlluminance"): (
        "Illuminance",
        "illuminance",
        "lx",
        0,
        None,
    ),
}


def _sensor_unit(trait: Trait, default: str) -> tuple[str, float] | None:
    unit = trait.parameter.get("unit")
    if unit in (None, ""):
        return default, 1.0
    if not isinstance(unit, str):
        return None
    aliases = {
        "°C": {"°c", "c", "℃", "celsius", "deg c"},
        "°F": {"°f", "f", "℉", "fahrenheit", "deg f"},
        "%": {"%", "percent", "percentage"},
        "V": {"v", "volt", "volts"},
        "lx": {"lx", "lux"},
    }
    normalized = unit.strip().casefold()
    if normalized in aliases.get(default, set()):
        return default, 1.0
    if default == "°C" and normalized in aliases["°F"]:
        return "°F", 1.0
    if default == "V" and normalized in {"mv", "millivolt", "millivolts"}:
        return "V", 0.001
    return None


def numeric_parameter(trait: Trait, key: str, default: float) -> float | None:
    """Use Aqara-spec defaults only for omitted optional numeric metadata.

    A malformed explicit value still rejects the capability. None means that
    Studio omitted the optional field; it is not a device range assertion.
    """
    raw = trait.parameter.get(key)
    return float(default) if raw is None else finite_number(raw)


def brightness_trait(device: StudioDevice, primary: Trait) -> Trait | None:
    """Select percentage brightness only on the same advertised light endpoint."""
    key = TraitKey(
        primary.key.device_id, primary.key.endpoint_id, "LevelControl", "CurrentLevel"
    )
    trait = device.traits.get(key)
    if (
        trait is None
        or not trait.readable
        or not trait.writable
        or trait.parameter.get("type") not in {"Float", "Integer"}
    ):
        return None
    # CurrentLevel is percentage-based. Aqara's min=1, max=100 and step=1
    # metadata are optional; explicit incompatible ranges remain rejected.
    minimum = numeric_parameter(trait, "min", 1)
    maximum = numeric_parameter(trait, "max", 100)
    if minimum not in (0.0, 1.0) or maximum != 100.0:
        return None
    step = numeric_parameter(trait, "step", 1)
    if step is not None and not 0 < step <= 100:
        return None
    if (
        trait.parameter.get("type") == "Integer"
        and step is not None
        and not step.is_integer()
    ):
        return None
    if trait.parameter.get("unit") not in (None, "", "%", "percent", "percentage"):
        return None
    return trait


# Require *positive* light evidence, not a generic writable OnOff capability.
# A standalone OnOff can describe relays, valves, or security equipment.
_LIGHT_TYPES = {
    "Light",
    "DimmableLight",
    "ColorTemperatureLight",
    "ExtendedColorLight",
    "LightStrip",
}
_NEVER_LIGHT_TYPES = {
    "Lock",
    "DoorLock",
    "GarageDoor",
    "Valve",
    "Public",
    "Cover",
    "WindowCovering",
}


def light_output(device: StudioDevice, primary: Trait) -> bool:
    """Recognize a light from its type or same-endpoint lighting functions."""
    if primary.endpoint_type in _NEVER_LIGHT_TYPES | {"Switch", "Outlet"}:
        return False
    if primary.endpoint_type in _LIGHT_TYPES:
        return True
    functions = {
        key.function_code
        for key in device.traits
        if key.endpoint_id == primary.key.endpoint_id
    }
    # Same-endpoint lighting controls are the strongest positive evidence.
    if {"Lighting", "ColorControl"} & functions:
        return True
    # Aqara specifies deviceTypesList ["Light"] as an explicit device type.
    # Allow the device-level type only for an unambiguous single-output light;
    # never treat a multi-endpoint relay, valve or mixed-function device as light.
    outputs = [
        item
        for item in device.traits.values()
        if (item.key.function_code, item.key.trait_code) == ("Output", "OnOff")
    ]
    return (
        set(device.device_types) == {"Light"}
        and len(outputs) == 1
        and outputs[0].key == primary.key
    )


def _integer_trait(device: StudioDevice, primary: Trait, code: str) -> Trait | None:
    key = TraitKey(primary.key.device_id, primary.key.endpoint_id, "ColorControl", code)
    trait = device.traits.get(key)
    if (
        trait is None
        or not trait.readable
        or not trait.writable
        or trait.parameter.get("type") not in {"Integer", "UInt32", "Uint32", "uint32"}
    ):
        return None
    return trait


@dataclass(frozen=True)
class ColorTemperatureProfile:
    """Validated device-level color temperature representation."""

    unit: str
    minimum: int
    maximum: int
    step: int

    @property
    def min_kelvin(self) -> int:
        return (
            math.ceil(1_000_000 / self.maximum)
            if self.unit == "mired"
            else self.minimum
        )

    @property
    def max_kelvin(self) -> int:
        return (
            math.floor(1_000_000 / self.minimum)
            if self.unit == "mired"
            else self.maximum
        )

    def to_kelvin(self, raw: Any) -> int | None:
        value = finite_number(raw)
        if value is None or not self.minimum <= value <= self.maximum:
            return None
        return round(1_000_000 / value) if self.unit == "mired" else round(value)

    def from_kelvin(self, kelvin: int) -> int | None:
        """Encode a HA Kelvin request in the device's advertised raw units."""
        if type(kelvin) is not int or not self.min_kelvin <= kelvin <= self.max_kelvin:
            return None
        raw = 1_000_000 / kelvin if self.unit == "mired" else kelvin
        quantized = self.minimum + round((raw - self.minimum) / self.step) * self.step
        return max(self.minimum, min(self.maximum, quantized))

    def accepts_raw(self, value: Any) -> bool:
        return (
            type(value) is int
            and self.minimum <= value <= self.maximum
            and (value - self.minimum) % self.step == 0
        )


def color_temperature_profile(trait: Trait) -> ColorTemperatureProfile | None:
    """Identify the API's mired or Kelvin representation, never cross-write.

    Aqara specifies mired for its core trait but the M300 LED-strip Studio
    definition reports the Kelvin-derived bounds 2703..6536. The corresponding
    Zigbee hardware bounds are 370..153 mired. Both forms must be supported.
    """
    if trait.parameter.get("type") not in {"Integer", "UInt32", "Uint32", "uint32"}:
        return None
    minimum = numeric_parameter(trait, "min", 153)
    maximum = numeric_parameter(trait, "max", 500)
    step = numeric_parameter(trait, "step", 1)
    if (
        minimum is None
        or maximum is None
        or step is None
        or not minimum.is_integer()
        or not maximum.is_integer()
        or not step.is_integer()
        or not 1 <= step <= maximum - minimum
    ):
        return None

    raw_unit = trait.parameter.get("unit")
    if raw_unit is not None and not isinstance(raw_unit, str):
        return None
    unit = (raw_unit or "").strip().casefold()
    mired_aliases = {"", "mired", "mireds", "mirek"}
    kelvin_aliases = {"", "k", "°k", "kelvin", "kelvins", "deg k", "degrees kelvin"}

    if 100 <= minimum < maximum <= 1000 and unit in mired_aliases:
        return ColorTemperatureProfile("mired", int(minimum), int(maximum), int(step))
    if 1800 <= minimum < maximum <= 10000 and unit in kelvin_aliases:
        return ColorTemperatureProfile("kelvin", int(minimum), int(maximum), int(step))

    # This exact metadata profile was observed on a real M300 LED strip.
    # Studio displays those bounds as Kelvin, but its supplied unit string
    # is redacted by our diagnostics. Restrict fallback to this exact shape,
    # excluding explicitly contradictory mired/Celsius/Fahrenheit units.
    if (
        minimum == 2703
        and maximum == 6536
        and step == 1
        and unit not in {"mired", "mireds", "mirek", "c", "°c", "celsius", "f", "°f"}
    ):
        return ColorTemperatureProfile("kelvin", 2703, 6536, 1)
    return None


def color_temp_trait(device: StudioDevice, primary: Trait) -> Trait | None:
    """Select a writable, unit-validated white-temperature light trait."""
    trait = _integer_trait(device, primary, "ColorTemperature")
    return trait if trait and color_temperature_profile(trait) else None


def xy_color_trait(device: StudioDevice, primary: Trait) -> Trait | None:
    """ColorXY uses documented uint32 packing, not a guessed RGB conversion."""
    trait = _integer_trait(device, primary, "ColorXY")
    if trait is None:
        return None
    if trait.parameter.get("unit") not in (None, ""):
        return None
    minimum = numeric_parameter(trait, "min", 0)
    maximum = numeric_parameter(trait, "max", 4294967295)
    step = numeric_parameter(trait, "step", 1)
    # The M300's metadata incorrectly advertises 2^32+7, while ColorXY
    # itself is a uint32. Accept only that narrow descriptor overshoot;
    # outgoing commands remain strictly limited to 0..0xffffffff.
    if minimum != 0 or not 4294967295 <= maximum <= 4294967303 or step != 1:
        return None
    return trait


def light_control_status(
    device: StudioDevice, trait: Trait, options: Mapping[str, Any] | None = None
) -> str:
    """Give an explicit, safe reason a light may not have native controls."""
    options = options or {}
    if not light_output(device, trait):
        return "not_a_light"
    if trait.parameter.get("type") not in {"Bool", "Boolean", "bool", "boolean"}:
        return "unsupported_onoff_type"
    if not trait.writable:
        return "api_read_only"
    if not options.get("enable_light_controls", True):
        return "disabled_in_options"
    return "ready"


def discover_capabilities(
    device: StudioDevice, options: Mapping[str, Any] | None = None
) -> list[Capability]:
    """Map supported advertised functions without enumerating every diagnostic."""
    options = options or {}
    capabilities: list[Capability] = []
    for key, trait in device.traits.items():
        code = (key.function_code, key.trait_code)
        if code == ("Button", "ButtonEvent"):
            if options.get("enable_button_events", False) and trait.subscribable:
                capabilities.append(Capability(key, "event", "Button", "button"))
            continue
        if not trait.readable:
            continue
        if code == ("Contact", "ContactSensorState"):
            capabilities.append(
                Capability(key, "binary_sensor", "Contact", "contact", "door")
            )
        elif code == ("WaterLeak", "LeakState"):
            capabilities.append(
                Capability(key, "binary_sensor", "Water leak", "leak", "moisture")
            )
        elif code in _SENSORS:
            name, device_class, unit, minimum, maximum = _SENSORS[code]
            resolved = _sensor_unit(trait, unit)
            if resolved is None:
                continue
            unit, scale = resolved
            if unit == "°F":
                minimum = -459.67
            capabilities.append(
                Capability(
                    key,
                    "sensor",
                    name,
                    device_class,
                    device_class,
                    unit,
                    scale,
                    minimum,
                    maximum,
                    diagnostic=code[0] == "PowerSource",
                    enabled_default=code[1] != "CurrentVoltage",
                )
            )
        elif code == ("Output", "OnOff"):
            # Keep a stable read-only state entity when controls are toggled.
            # The optional actuator uses another HA platform with the same
            # underlying trait identity; neither registry entry is deleted.
            is_light = light_output(device, trait)
            # Lighting is a first-class HA device, enabled by default only
            # with explicit API write permission. Other switching stays opt-in.
            controls = (
                trait.writable
                and trait.parameter.get("type")
                in {"Bool", "Boolean", "bool", "boolean"}
                and (
                    (is_light and options.get("enable_light_controls", True))
                    or (
                        not is_light
                        and options.get("enable_controls", False)
                        and trait.endpoint_type in {"Switch", "Outlet"}
                    )
                )
            )
            if is_light:
                capabilities.append(
                    Capability(
                        key,
                        "sensor",
                        "Light control status",
                        "light_readiness",
                        diagnostic=True,
                    )
                )
            capabilities.append(
                Capability(
                    key,
                    "binary_sensor",
                    "Output state",
                    "onoff",
                    diagnostic=bool(controls),
                    enabled_default=not controls,
                )
            )
            platform = None
            brightness_key = None
            color_temp_key = None
            xy_color_key = None
            color_mode_key = None
            if controls:
                if is_light:
                    platform = "light"
                    if brightness := brightness_trait(device, trait):
                        brightness_key = brightness.key
                    if color_temp := color_temp_trait(device, trait):
                        color_temp_key = color_temp.key
                    if xy_color := xy_color_trait(device, trait):
                        xy_color_key = xy_color.key
                    mode = TraitKey(
                        key.device_id, key.endpoint_id, "ColorControl", "ColorMode"
                    )
                    if mode in device.traits and device.traits[mode].readable:
                        color_mode_key = mode
                elif trait.endpoint_type in {"Switch", "Outlet"}:
                    platform = "switch"
            if platform:
                capabilities.append(
                    Capability(
                        key,
                        platform,
                        "Power",
                        "control",
                        brightness_key=brightness_key,
                        color_temp_key=color_temp_key,
                        xy_color_key=xy_color_key,
                        color_mode_key=color_mode_key,
                    )
                )
    return capabilities


def unknown_capabilities(device: StudioDevice) -> list[dict[str, Any]]:
    """Return metadata only, never arbitrary vendor values or household names."""
    supported = {
        cap.key for cap in discover_capabilities(device, {"enable_button_events": True})
    }
    known_metadata = {
        ("BasicInformation", "Reachable"),
        ("BasicInformation", "FirmwareRevision"),
        ("BasicInformation", "FirmwareRevisionString"),
        ("BasicInformation", "VendorName"),
        ("BasicInformation", "ModelValue"),
    }
    return [
        {
            "endpoint": key.endpoint_id,
            "function": key.function_code,
            "trait": key.trait_code,
            "readable": trait.readable,
            "writable": trait.writable,
            "subscribable": trait.subscribable,
        }
        for key, trait in device.traits.items()
        if key not in supported
        and (key.function_code, key.trait_code) not in known_metadata
    ]
