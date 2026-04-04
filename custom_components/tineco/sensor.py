"""Sensor platform for Tineco integration."""

import logging
import re
from typing import Dict, Optional
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

_LOGGER = logging.getLogger(__name__)

DOMAIN = "tineco"


def _extract_values(obj, target_keys):
    """Recursively extract values for target keys (lowercased) from nested dicts/lists."""
    result = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            k_lower = k.lower() if isinstance(k, str) else ""
            if k_lower in target_keys:
                result[k_lower] = v
            if isinstance(v, (dict, list, tuple)):
                result.update(_extract_values(v, target_keys))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            result.update(_extract_values(item, target_keys))
    return result


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform from a config entry."""
    
    data = hass.data[DOMAIN].get(config_entry.entry_id, {})
    coordinator = data.get("coordinator")
    
    # Create sensor entities for each device property
    sensors = [
        TinecoFirmwareVersionSensor(config_entry, hass, coordinator),
        TinecoAPISensor(config_entry, hass, coordinator),
        TinecoModelSensor(config_entry, hass, coordinator),
        TinecoBatterySensor(config_entry, hass, coordinator),
        TinecoVacuumStatusSensor(config_entry, hass, coordinator),
        TinecoWaterTankSensor(config_entry, hass, coordinator),
        TinecoFreshWaterTankSensor(config_entry, hass, coordinator),
        TinecoBrushRollerSensor(config_entry, hass, coordinator),
    ]

    async_add_entities(sensors)


class TinecoBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for Tineco sensors."""

    def __init__(self, config_entry: ConfigEntry, sensor_type: str, hass: HomeAssistant, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self.sensor_type = sensor_type
        self.hass = hass
        self._state = "Unknown"
        self._device_info = {}
        
        email = config_entry.data.get("email", "")
        self._attr_unique_id = f"{DOMAIN}_{email}_{sensor_type}"
        # Don't add Tineco prefix for water tank sensors
        if "water_tank" in sensor_type:
            self._attr_name = f"{sensor_type.replace('_', ' ').title()}"
        else:
            self._attr_name = f"Tineco {sensor_type.replace('_', ' ').title()}"

    @property
    def native_value(self):
        """Return the native value."""
        return self._state

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": "Tineco Device",
            "manufacturer": "Jack Whelan",
            "model": self._device_info.get("model", "IoT Device"),
        }

    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._update_state_from_data(self.coordinator.data)
        self.async_write_ha_state()

    def _update_state_from_data(self, info: Dict):
        """Update state from device info - override in subclasses."""
        pass


class TinecoFirmwareVersionSensor(TinecoBaseSensor):
    """Sensor for firmware version."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant, coordinator):
        """Initialize."""
        super().__init__(config_entry, "firmware_version", hass, coordinator)
        self._state = "Unknown"

    def _update_state_from_data(self, info: Dict):
        """Update state from device info."""
        # Try to find firmware version from endpoints
        try:
            # Check gav endpoint first (Get API Version - has firmware info)
            if 'gav' in info and isinstance(info['gav'], dict):
                gav = info['gav']
                # Try vv (voice version) or tv (main version)
                fw = gav.get('vv') or gav.get('tv') or gav.get('pv')
                if fw:
                    # Clean up special characters (vv field has garbage at end)
                    fw_clean = self._clean_version_string(str(fw))
                    if fw_clean:
                        self._state = fw_clean
                        return
            
            # Fallback: check device list
            stored = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {})
            client = stored.get('client')
            if client and hasattr(client, 'devices') and client.devices:
                device = client.devices[0]
                fw = device.get('firmwareVersion') or device.get('fwVersion') or device.get('version')
                if fw:
                    fw_clean = self._clean_version_string(str(fw))
                    if fw_clean:
                        self._state = fw_clean
                        return
                        
            self._state = "Unknown"
        except Exception as err:
            _LOGGER.error(f"Error parsing firmware: {err}", exc_info=True)
            self._state = "Unknown"
    
    def _clean_version_string(self, version_str: str) -> str:
        """Clean version string by removing special characters."""
        if not version_str:
            return ""
        cleaned = re.sub(r'[^a-zA-Z0-9._-]', '', version_str)
        return cleaned if cleaned else ""
    
    @property
    def icon(self):
        """Return the icon."""
        return "mdi:information"


class TinecoAPISensor(TinecoBaseSensor):
    """Sensor for API version."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant, coordinator):
        """Initialize."""
        super().__init__(config_entry, "api_version", hass, coordinator)
        self._state = "Unknown"

    def _update_state_from_data(self, info: Dict):
        """Update state from device info."""
        # Try to find API version in any endpoint
        try:
            # Search through all endpoints
            for endpoint_key in ['gav', 'gci', 'gcf', 'cfp', 'query_mode']:
                if endpoint_key in info and info[endpoint_key]:
                    endpoint_data = info[endpoint_key]
                    if isinstance(endpoint_data, dict):
                        # Try multiple payload structures
                        payloads = [
                            endpoint_data.get('payload'),
                            endpoint_data.get('data'),
                            endpoint_data
                        ]
                        
                        for payload in payloads:
                            if isinstance(payload, dict):
                                # Try various field names
                                api_version = (
                                    payload.get('api_version') or
                                    payload.get('apiVersion') or
                                    payload.get('api') or
                                    payload.get('av')
                                )
                                if api_version and api_version != "Unknown":
                                    self._state = str(api_version)
                                    _LOGGER.debug(f"Found API version: {api_version} in {endpoint_key}")
                                    return
            
            self._state = "Unknown"
        except Exception as err:
            _LOGGER.error(f"Error parsing API version: {err}", exc_info=True)
            self._state = "Unknown"
    
    @property
    def icon(self):
        """Return the icon."""
        return "mdi:api"


class TinecoModelSensor(TinecoBaseSensor):
    """Sensor for device model."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant, coordinator):
        """Initialize."""
        super().__init__(config_entry, "model", hass, coordinator)
        self._state = "Unknown"

    def _update_state_from_data(self, info: Dict):
        """Update state from device info."""
        # Try to find model in device list first (most reliable)
        try:
            stored = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {})
            client = stored.get('client')
            if client and hasattr(client, 'devices') and client.devices:
                device = client.devices[0]
                
                # Priority: nick (user-set display name) > productType > deviceName > name
                # Skip fields starting with '0000' as they are device IDs
                model = (
                    device.get('nick') or  # User-friendly name (e.g., "S7 Flashdry")
                    device.get('productType') or
                    device.get('deviceName') or
                    device.get('model') or
                    device.get('deviceModel')
                )
                # Fallback to name only if it doesn't look like a device ID
                if not model:
                    name = device.get('name')
                    if name and not name.startswith('0000'):
                        model = name
                
                if model and model != "Unknown":
                    self._state = str(model)
                    return
            
            # Search through all endpoints
            for endpoint_key in ['gci', 'gav', 'gcf', 'cfp', 'query_mode']:
                if endpoint_key in info and info[endpoint_key]:
                    endpoint_data = info[endpoint_key]
                    if isinstance(endpoint_data, dict):
                        # Try multiple payload structures
                        payloads = [
                            endpoint_data.get('payload'),
                            endpoint_data.get('data'),
                            endpoint_data
                        ]
                        
                        for payload in payloads:
                            if isinstance(payload, dict):
                                # Try various field names
                                model = (
                                    payload.get('model') or
                                    payload.get('deviceModel') or
                                    payload.get('device_name') or
                                    payload.get('name') or
                                    payload.get('deviceName')
                                )
                                if model and model != "Unknown":
                                    self._state = str(model)
                                    _LOGGER.debug(f"Found model: {model} in {endpoint_key}")
                                    return
                        
            self._state = "Tineco Device"
        except Exception as err:
            _LOGGER.error(f"Error parsing model: {err}", exc_info=True)
            self._state = "Unknown"
    
    @property
    def icon(self):
        """Return the icon."""
        return "mdi:home"


class TinecoVacuumStatusSensor(TinecoBaseSensor):
    """Sensor for vacuum operating status."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant, coordinator):
        """Initialize."""
        super().__init__(config_entry, "vacuum_status", hass, coordinator)
        self._state = "idle"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["idle", "in_operation", "self_cleaning"]
        self._attr_translation_key = "vacuum_status"

    def _update_state_from_data(self, info: Dict):
        """Update state from device info.

        Based on FloorSyscBean from decompiled Tineco app (CL2349 / Floor One Switch S7):
        - wm=3: in operation (actively cleaning)
        - wm=8 + selfclean_process >= 5 (and != 17): self-cleaning
        - all other wm values: idle (standby, charging, drying, OTA, etc.)
        """
        try:
            # Use gci (Get Controller Info) or cfp (Config Point) for current status
            # Note: query_mode.cfg is an array of mode configs, not current status
            payload = None
            
            if isinstance(info, dict):
                # Priority: gci > cfp (both contain current device state)
                if 'gci' in info and isinstance(info['gci'], dict):
                    payload = info['gci']
                elif 'cfp' in info and isinstance(info['cfp'], dict):
                    payload = info['cfp']
            
            if payload:
                _LOGGER.debug("Vacuum status: raw payload = %s", payload)
                status = self._parse_vacuum_status(payload)
                if status:
                    self._state = status
                    return

            # Default to idle if we have data but can't determine status
            self._state = "idle"

        except Exception as err:
            _LOGGER.error(f"Error parsing vacuum status: {err}", exc_info=True)
            self._state = "idle"

    def _parse_vacuum_status(self, payload: Dict) -> Optional[str]:
        """Parse vacuum status from payload.

        Logic mirrors the Tineco app's getDeviceState() for the CL2349 (Floor One Switch S7):
        - wm=1: standby
        - wm=2: charging
        - wm=3: running (in_operation)
        - wm=8: self-cleaning ONLY if selfclean_process >= 5 and != 17
                (selfclean_process 1-4 = pre-clean charging, 17 = post-clean charging)
        - wm=9: OTA update (idle)
        - wm=13: drying (idle)
        - other wm values: standby (idle)
        """
        if not isinstance(payload, dict):
            return None

        fields = _extract_values(payload, ["wm", "selfclean_process"])

        wm = fields.get("wm")
        selfclean_process = fields.get("selfclean_process")

        _LOGGER.debug(
            "Vacuum status raw: wm=%s, selfclean_process=%s, payload_keys=%s",
            wm, selfclean_process, list(payload.keys()) if isinstance(payload, dict) else "N/A"
        )

        if wm is None:
            _LOGGER.debug("Vacuum status: wm not found in payload")
            return None

        try:
            work_mode = int(wm)
        except (ValueError, TypeError):
            return None

        if work_mode == 3:
            return "in_operation"

        if work_mode == 8:
            # wm=8 = self-clean mode.
            # If selfclean_process is present (station-equipped models like CL2349 Switch S7):
            #   process >= 5 (and != 17) = actively self-cleaning
            #   process < 5 or == 17 = pre/post-clean charging → idle
            # If selfclean_process is absent (e.g. S7 Flashdry): wm=8 alone means self-cleaning
            if selfclean_process is None:
                _LOGGER.debug("Vacuum status: wm=8, no selfclean_process → self_cleaning")
                return "self_cleaning"
            try:
                process = int(selfclean_process)
            except (ValueError, TypeError):
                process = 0
            result = "self_cleaning" if (process >= 5 and process != 17) else "idle"
            _LOGGER.debug("Vacuum status: wm=8, selfclean_process=%s → %s", process, result)
            if process >= 5 and process != 17:
                return "self_cleaning"
            return "idle"

        _LOGGER.debug("Vacuum status: wm=%s → idle", work_mode)
        # wm=1 (standby), wm=2 (charging), wm=9 (OTA), wm=13 (drying), others → idle
        return "idle"
    
    @property
    def icon(self):
        """Return the icon based on state."""
        if self._state == "in_operation":
            return "mdi:vacuum"
        elif self._state == "self_cleaning":
            return "mdi:dishwasher"
        else:  # idle or unknown
            return "mdi:home-circle"


class TinecoBatterySensor(TinecoBaseSensor):
    """Sensor for battery percentage."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant, coordinator):
        """Initialize."""
        super().__init__(config_entry, "battery", hass, coordinator)
        self._state = None
        self._attr_device_class = "battery"
        self._attr_native_unit_of_measurement = "%"

    def _update_state_from_data(self, info: Dict):
        """Update state from device info."""
        percent = self._extract_battery_percent(info)
        if percent is not None:
            try:
                self._state = max(0, min(100, int(round(float(percent)))))
            except Exception:
                self._state = None
        else:
            self._state = None

    def _extract_battery_percent(self, info: Dict):
        """Attempt to find battery percentage across known payloads."""
        def pick(d: Dict, keys):
            for k in keys:
                if isinstance(d, dict) and k in d and d.get(k) is not None:
                    return d.get(k)
            return None

        # Check QueryMode first (most common for real-time data)
        qm = info.get("query_mode")
        if isinstance(qm, dict):
            payload = qm.get("payload") or qm.get("data") or qm
            val = pick(payload, [
                "bp", "battery", "battery_percent", "batteryPercent", "batteryLevel",
                "electricQuantity", "elec", "elecQuantity", "powerPercent", "soc"
            ])
            if val is not None:
                return self._normalize_percent(val)

        # Check GCI
        gci = info.get("gci")
        if isinstance(gci, dict):
            payload = gci.get("payload") or gci.get("data") or gci
            val = pick(payload, [
                "bp", "battery", "battery_percent", "batteryLevel", "electricQuantity",
                "elec", "elecQuantity", "powerPercent", "soc"
            ])
            if val is not None:
                return self._normalize_percent(val)

        # Any other top-level payloads
        for key in ("gcf", "cfp"):
            part = info.get(key)
            if isinstance(part, dict):
                payload = part.get("payload") or part.get("data") or part
                val = pick(payload, ["bp", "battery", "batteryLevel", "powerPercent", "soc"])
                if val is not None:
                    return self._normalize_percent(val)
        return None

    def _normalize_percent(self, val):
        try:
            if isinstance(val, str):
                v = val.strip().replace("%", "")
                raw = float(v)
            elif isinstance(val, (int, float)):
                raw = float(val)
            else:
                return None
            
            # Handle Tineco's battery encoding:
            # 240 = fully charged (100%)
            # 0-100 = actual percentage when discharging
            # Values > 100 = charging or fully charged state
            if raw >= 100:
                # Treat any value >= 100 as fully charged
                return 100.0
            else:
                # Values 0-100 are the actual percentage
                return max(0.0, min(100.0, raw))
        except Exception:
            return None

class TinecoWaterTankSensor(TinecoBaseSensor):
    """Sensor for water tank status."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant, coordinator):
        """Initialize."""
        super().__init__(config_entry, "waste_water_tank_status", hass, coordinator)
        self._state = "clean"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["clean", "full"]
        self._attr_translation_key = "waste_water_tank_status"

    def _update_state_from_data(self, info: Dict):
        """Update state from device info."""
        try:
            payload = None
            
            if isinstance(info, dict):
                # Priority: gci > cfp
                if 'gci' in info and isinstance(info['gci'], dict):
                    payload = info['gci']
                elif 'cfp' in info and isinstance(info['cfp'], dict):
                    payload = info['cfp']
            
            if payload:
                status = self._parse_water_tank_status(payload)
                if status:
                    self._state = status
                    return
            
            # Default to clean if we can't determine
            self._state = "clean"
            
        except Exception as err:
            _LOGGER.error(f"Error parsing water tank status: {err}", exc_info=True)
            self._state = "clean"

    def _parse_water_tank_status(self, payload: Dict) -> Optional[str]:
        """Parse waste water tank status from payload."""
        if not isinstance(payload, dict):
            return None

        fields = _extract_values(payload, ["e1", "mdt"])
        
        # Check e1 field if it exists (might indicate waste tank issue)
        e1 = fields.get("e1")
        if e1 is not None:
            try:
                error_code = int(e1)
                if error_code > 0:
                    return "full"
            except (ValueError, TypeError):
                pass
        
        return "clean"
    
    @property
    def icon(self):
        """Return the icon based on state."""
        if self._state == "full":
            return "mdi:water-alert"
        else:
            return "mdi:water"


class TinecoFreshWaterTankSensor(TinecoBaseSensor):
    """Sensor for fresh water tank status."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant, coordinator):
        """Initialize."""
        super().__init__(config_entry, "fresh_water_tank_status", hass, coordinator)
        self._state = "full"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["empty", "full"]
        self._attr_translation_key = "fresh_water_tank_status"

    def _update_state_from_data(self, info: Dict):
        """Update state from device info."""
        try:
            payload = None
            
            if isinstance(info, dict):
                # Priority: gci > cfp
                if 'gci' in info and isinstance(info['gci'], dict):
                    payload = info['gci']
                elif 'cfp' in info and isinstance(info['cfp'], dict):
                    payload = info['cfp']
            
            if payload:
                status = self._parse_fresh_water_status(payload)
                if status:
                    self._state = status
                    return
            
            # Default to full if we can't determine
            self._state = "full"
            
        except Exception as err:
            _LOGGER.error(f"Error parsing fresh water tank status: {err}", exc_info=True)
            self._state = "full"

    def _parse_fresh_water_status(self, payload: Dict) -> Optional[str]:
        """Parse fresh water tank status from payload."""
        if not isinstance(payload, dict):
            return None

        fields = _extract_values(payload, ["e2"])
        
        # Check e2 field: 64 = fresh water tank empty
        e2 = fields.get("e2")
        if e2 is not None:
            try:
                error_code = int(e2)
                if error_code == 64:
                    return "empty"
            except (ValueError, TypeError):
                pass
        
        return "full"
    
    @property
    def icon(self):
        """Return the icon based on state."""
        if self._state == "empty":
            return "mdi:water-off"
        return "mdi:water-check"


class TinecoBrushRollerSensor(TinecoBaseSensor):
    """Sensor for brush roller status."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant, coordinator):
        """Initialize."""
        super().__init__(config_entry, "brush_roller", hass, coordinator)
        self._state = "normal"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["normal", "tangled", "stuck", "needs_cleaning"]
        self._attr_translation_key = "brush_roller"

    def _update_state_from_data(self, info: Dict):
        """Update state from device info."""
        try:
            payload = None

            if isinstance(info, dict):
                # Priority: gci > cfp
                if 'gci' in info and isinstance(info['gci'], dict):
                    payload = info['gci']
                elif 'cfp' in info and isinstance(info['cfp'], dict):
                    payload = info['cfp']

            if payload:
                status = self._parse_brush_roller_status(payload)
                if status:
                    self._state = status
                    return

            # Default to normal if we can't determine
            self._state = "normal"

        except Exception as err:
            _LOGGER.error(f"Error parsing brush roller status: {err}", exc_info=True)
            self._state = "normal"

    def _parse_brush_roller_status(self, payload: Dict) -> Optional[str]:
        """Parse brush roller status from payload."""
        if not isinstance(payload, dict):
            return None

        fields = _extract_values(payload, ["br", "brs", "brush_roller", "roller_status"])

        # Check br field for brush roller status
        br = fields.get("br")
        if br is not None:
            try:
                status_code = int(br)
                # Map status codes to states
                # 0 = normal, 1 = tangled, 2 = stuck, 3 = needs_cleaning
                if status_code == 0:
                    return "normal"
                elif status_code == 1:
                    return "tangled"
                elif status_code == 2:
                    return "stuck"
                elif status_code == 3:
                    return "needs_cleaning"
            except (ValueError, TypeError):
                pass

        return "normal"

    @property
    def icon(self):
        """Return the icon based on state."""
        if self._state == "tangled":
            return "mdi:alert-circle"
        elif self._state == "stuck":
            return "mdi:alert"
        elif self._state == "needs_cleaning":
            return "mdi:broom"
        else:  # normal
            return "mdi:rotate-3d-variant"
