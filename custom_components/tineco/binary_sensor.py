"""Binary sensor platform for Tineco integration."""

import logging
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

_LOGGER = logging.getLogger(__name__)

DOMAIN = "tineco"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor platform from a config entry."""

    data = hass.data[DOMAIN].get(config_entry.entry_id, {})
    coordinator = data.get("coordinator")

    sensors = [
        TinecoDeviceOnlineSensor(config_entry, hass, coordinator),
        TinecoChargingSensor(config_entry, hass, coordinator),
    ]

    async_add_entities(sensors)


def _walk(obj):
    """Yield (key, value) pairs from nested dicts/lists/tuples."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            if isinstance(v, (dict, list, tuple)):
                yield from _walk(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            if isinstance(v, (dict, list, tuple)):
                yield from _walk(v)


def _extract_payloads(info):
    """Collect possible payload blobs from coordinator device info."""
    payloads = []
    if isinstance(info, dict):
        for key in ("query_mode", "gci", "gcf", "cfp"):
            part = info.get(key)
            if isinstance(part, dict):
                payloads.append(part.get("payload") or part.get("data") or part)
        # Fallback: use the whole info blob if nothing else
        if not payloads:
            payloads.append(info)
    return payloads


class TinecoBaseBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Base class for Tineco binary sensors.

    These entities derive their state from the shared DataUpdateCoordinator
    rather than issuing their own IoT queries. This keeps the upstream API load
    to a single request per refresh cycle and means a single flaky endpoint can
    no longer cause one entity to take >10s and report a wrong state.
    """

    def __init__(self, config_entry: ConfigEntry, sensor_type: str, hass: HomeAssistant, coordinator):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self.sensor_type = sensor_type
        self.hass = hass
        self._state = False

        email = config_entry.data.get("email", "")
        self._attr_unique_id = f"{DOMAIN}_{email}_{sensor_type}"
        self._attr_name = f"Tineco {sensor_type.replace('_', ' ').title()}"

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        return self._state

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": "Tineco Device",
            "manufacturer": "Jack Whelan",
            "model": "IoT Device",
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_state_from_coordinator()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Set initial state when the entity is added."""
        await super().async_added_to_hass()
        self._update_state_from_coordinator()

    def _update_state_from_coordinator(self) -> None:
        """Update state from coordinator data - override in subclasses."""


class TinecoDeviceOnlineSensor(TinecoBaseBinarySensor):
    """Binary sensor for device online status.

    Online state mirrors whether the coordinator's last refresh succeeded: if
    the integration can reach the device through the IoT API, it is online.
    """

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant, coordinator):
        """Initialize the online sensor."""
        super().__init__(config_entry, "online", hass, coordinator)

    def _update_state_from_coordinator(self) -> None:
        """Online if the coordinator successfully fetched device data."""
        self._state = bool(self.coordinator.last_update_success and self.coordinator.data)

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:wifi" if self._state else "mdi:wifi-off"


class TinecoChargingSensor(TinecoBaseBinarySensor):
    """Binary sensor for charging state."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant, coordinator):
        """Initialize the charging sensor."""
        super().__init__(config_entry, "charging", hass, coordinator)
        self._unknown_log_count = 0

    def _update_state_from_coordinator(self) -> None:
        """Update charging state from coordinator data."""
        payloads = _extract_payloads(self.coordinator.data) if self.coordinator.data else []
        self._state = any(self._is_charging_from_payload(p) for p in payloads)

        if not self._state and payloads and self._unknown_log_count < 3:
            sample = payloads[0] if isinstance(payloads[0], dict) else None
            keys = list(sample.keys()) if isinstance(sample, dict) else "non-dict"
            _LOGGER.debug("Charging not detected; payload keys=%s", keys)
            self._unknown_log_count += 1

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:battery-charging" if self._state else "mdi:battery"

    def _is_charging_from_payload(self, payload) -> bool:
        """Infer charging state from known and heuristic fields.

        Based on reverse-engineered Tineco Android app (MQTT CFT topic payload):
        - wm (work mode) = 2 indicates charging state
        - bp (battery percentage) > 100 indicates charging (e.g., 238, 239, 240)

        See: CHARGING_INDICATOR_ANALYSIS.md from decompiled APK
        """
        if not isinstance(payload, (dict, list, tuple)):
            return False

        # Define explicit charging-related keys
        explicit_keys = {
            "charging",
            "ischarging",
            "chargestate",
            "charge_status",
            "charge_status_code",
            "charging_state",
            "is_charging",
            "is_charger",
            "dock",
            "docked",
            "isdocked",
            "plug",
            "plugged",
            "pluggedin",
            "plug_status",
        }

        charge_strings = {"charge", "charging", "recharge", "plug", "dock"}
        charge_values = {"charge", "charging", "recharging", "plugged", "plug", "plug-in", "dock", "docked", "on", "true", "yes", "1"}

        for key, val in _walk(payload):
            key_lower = key.lower() if isinstance(key, str) else ""

            # PRIORITY 1: Check Tineco-specific wm (work mode) field
            # wm=2 definitively indicates charging state (from decompiled app)
            if key_lower == "wm":
                try:
                    work_mode = int(val)
                    if work_mode == 2:
                        return True
                except (ValueError, TypeError):
                    pass

            # PRIORITY 2: Battery raw value heuristic
            # Tineco reports >100 (e.g., 238, 239, 240) while docked/charging
            if key_lower in ("bp", "battery", "batterypercent", "battery_percent", "powerpercent", "elec", "electricquantity", "battery_level", "soc"):
                try:
                    numeric_val = float(str(val).replace("%", ""))
                    if numeric_val > 100:
                        return True
                except Exception:
                    pass

            # PRIORITY 3: Explicit keys or keys containing charge/dock/plug
            if key_lower in explicit_keys or any(term in key_lower for term in charge_strings):
                if isinstance(val, bool):
                    if val:
                        return True
                elif isinstance(val, str):
                    lower = val.lower()
                    if "discharge" in lower:
                        continue
                    if lower in charge_values or any(term in lower for term in charge_strings):
                        return True
                elif isinstance(val, (int, float)):
                    if val > 0:
                        return True

            # PRIORITY 4: Status-style fields where a specific value indicates charging
            if key_lower in ("status", "state", "workstatus", "work_status", "mode"):
                if isinstance(val, str):
                    lower = val.lower()
                    if "charge" in lower and "discharge" not in lower:
                        return True
                    if any(term in lower for term in ("dock", "plug")):
                        return True
                elif isinstance(val, (int, float)) and val in (2, 3, 4, 5, 6, 100):
                    return True

        return False
