"""Switch platform for Tineco integration."""

import logging
from datetime import datetime, timedelta
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

DOMAIN = "tineco"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch platform from a config entry."""

    # Add all switches
    switches = [
        TinecoAudioSwitch(config_entry, hass),
        TinecoFloorBrushLightSwitch(config_entry, hass),
        TinecoWaterOnlyModeSwitch(config_entry, hass),
    ]

    async_add_entities(switches)


class TinecoBaseSwitch(SwitchEntity):
    """Base class for Tineco switches."""

    def __init__(self, config_entry: ConfigEntry, switch_type: str, hass: HomeAssistant):
        """Initialize the switch."""
        self.config_entry = config_entry
        self.switch_type = switch_type
        self.hass = hass
        self._attr_should_poll = True
        self._state = False
        self._last_command_time = None
        
        email = config_entry.data.get("email", "")
        self._attr_unique_id = f"{DOMAIN}_{email}_{switch_type}"
        self._attr_name = f"Tineco {switch_type.replace('_', ' ').title()}"

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": "Tineco Device",
            "manufacturer": "Jack Whelan",
            "model": "IoT Device",
        }

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        return self._state

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        _LOGGER.info(f"Turning on {self.switch_type}")
        # Send control command to device
        await self._send_command(on=True)
        self._state = True
        self._last_command_time = datetime.now()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        _LOGGER.info(f"Turning off {self.switch_type}")
        # Send control command to device
        await self._send_command(on=False)
        self._state = False
        self._last_command_time = datetime.now()
        self.async_write_ha_state()

    async def _send_command(self, on: bool):
        """Send command to device - override in subclasses."""
        pass

    async def async_update(self):
        """Update switch state."""
        try:
            from .client import async_get_or_create_client
            client = await async_get_or_create_client(self.hass, self.config_entry)
            if client is None:
                _LOGGER.debug("Failed to login during update")
                return

            stored = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {})
            device_ctx = stored.get("device")
            if not device_ctx:
                devices = await client.async_get_devices()
                if not devices or not client.devices:
                    return
                first = client.devices[0]
                device_ctx = {
                    "id": first.get("did") or first.get("deviceId"),
                    "class": first.get("className", ""),
                    "resource": first.get("resource", ""),
                }
                self.hass.data[DOMAIN][self.config_entry.entry_id]["device"] = device_ctx

            device_id = device_ctx.get("id")
            device_class = device_ctx.get("class", "")
            device_resource = device_ctx.get("resource", "")
            
            # Get device status to determine if on/off
            status = await client.async_query_device_mode(device_id, device_class, device_resource)
            if status:
                # Try to determine power state from device response
                self._state = True  # Default to on if we got data
            
        except Exception as err:
            _LOGGER.debug(f"Error updating switch: {err}")


class TinecoDevicePowerSwitch(TinecoBaseSwitch):
    """Switch for device power control."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant):
        """Initialize the power switch."""
        super().__init__(config_entry, "power", hass)
        self._state = True  # Assume device is on by default

    async def _send_command(self, on: bool):
        """Send power command to device."""
        try:
            from .client import async_get_or_create_client
            client = await async_get_or_create_client(self.hass, self.config_entry)
            if client is None:
                _LOGGER.error("Failed to login for power command")
                return

            stored = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {})
            device_ctx = stored.get("device")
            if not device_ctx:
                devices = await client.async_get_devices()
                if not devices or not client.devices:
                    _LOGGER.error("No devices found for power command")
                    return
                first = client.devices[0]
                device_ctx = {
                    "id": first.get("did") or first.get("deviceId"),
                    "class": first.get("className", ""),
                    "resource": first.get("resource", ""),
                }
                self.hass.data[DOMAIN][self.config_entry.entry_id]["device"] = device_ctx

            device_id = device_ctx.get("id")
            
            # Send power command
            command = {"power": 1 if on else 0}
            result = await client.async_control_device(device_id, command)
            
            if result:
                _LOGGER.info(f"Power command sent: {on}")
            else:
                _LOGGER.error("Failed to send power command")
                
        except Exception as err:
            _LOGGER.error(f"Error sending power command: {err}")

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:power" if self._state else "mdi:power-off"


class TinecoAudioSwitch(TinecoBaseSwitch):
    """Switch for sound control."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant):
        """Initialize the sound switch."""
        super().__init__(config_entry, "sound", hass)
        self._state = True  # Assume sound is on by default
        # Override name with group prefix
        self._attr_name = "Tineco Sound: Enabled"

    async def _send_command(self, on: bool):
        """Send volume command to device."""
        try:
            from .client import async_get_or_create_client
            client = await async_get_or_create_client(self.hass, self.config_entry)
            if client is None:
                _LOGGER.error("Failed to login for sound command")
                return

            stored = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {})
            device_ctx = stored.get("device")
            if not device_ctx:
                devices = await client.async_get_devices()
                if not devices or not client.devices:
                    _LOGGER.error("No devices found for sound command")
                    return
                first = client.devices[0]
                device_ctx = {
                    "id": first.get("did") or first.get("deviceId"),
                    "class": first.get("className", ""),
                    "resource": first.get("resource", ""),
                }
                self.hass.data[DOMAIN][self.config_entry.entry_id]["device"] = device_ctx

            device_id = device_ctx.get("id")
            device_sn = device_ctx.get("resource", "")
            device_class = device_ctx.get("class", "")
            
            # Send sound command: ms = 1 to mute (off), ms = 0 to unmute (on)
            command = {"ms": 1 if not on else 0}
            _LOGGER.info(f"Sending sound command to device {device_id} (class: {device_class}, sn: {device_sn}): {command} (turning {'on' if on else 'off'})")
            result = await client.async_control_device(device_id, command, device_sn, device_class)
            
            if result:
                _LOGGER.info(f"Sound command sent successfully: {on}, result: {result}")
            else:
                _LOGGER.error("Failed to send sound command - no result returned")
                
        except Exception as err:
            _LOGGER.error(f"Error sending volume command: {err}")

    async def async_update(self):
        """Update sound switch state."""
        try:
            # Skip update if a command was sent recently (within 5 seconds)
            # This prevents stale data from overwriting the optimistic state
            if self._last_command_time:
                time_since_command = datetime.now() - self._last_command_time
                if time_since_command < timedelta(seconds=5):
                    _LOGGER.debug(f"Skipping update - recent command sent {time_since_command.total_seconds():.1f}s ago")
                    return
            
            stored = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {})
            coordinator = stored.get("coordinator")
            
            if coordinator and coordinator.data:
                # Get current sound state from coordinator data
                info = coordinator.data
                
                # Check gci or cfp for vl (voice level) field
                payload = None
                if isinstance(info, dict):
                    if 'gci' in info and isinstance(info['gci'], dict):
                        payload = info['gci']
                    elif 'cfp' in info and isinstance(info['cfp'], dict):
                        payload = info['cfp']
                
                if payload and 'vl' in payload:
                    # vl = 1 means sound on, vl = 0 means sound off/muted
                    self._state = payload['vl'] >= 1
                    
        except Exception as err:
            _LOGGER.debug(f"Error updating sound switch: {err}")

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:volume-high" if self._state else "mdi:volume-off"


class TinecoFloorBrushLightSwitch(TinecoBaseSwitch):
    """Switch for floor brush light control."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant):
        """Initialize the floor brush light switch."""
        super().__init__(config_entry, "floor_brush_light", hass)
        self._state = False  # Assume light is off by default

    async def _send_command(self, on: bool):
        """Send floor brush light command to device."""
        _LOGGER.info(f"🔧 Floor Brush Light: Attempting to turn {'ON' if on else 'OFF'}")
        try:
            from .client import async_get_or_create_client
            stored = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {})
            if stored.get("client") is None:
                _LOGGER.warning("Floor Brush Light: Client not found, creating new client")
            client = await async_get_or_create_client(self.hass, self.config_entry)
            if client is None:
                _LOGGER.error("Floor Brush Light: Failed to login")
                return

            stored = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {})
            device_ctx = stored.get("device")
            if not device_ctx:
                _LOGGER.warning("Floor Brush Light: Device context not found, fetching devices")
                devices = await client.async_get_devices()
                if not devices or not client.devices:
                    _LOGGER.error("Floor Brush Light: No devices found")
                    return
                first = client.devices[0]
                device_ctx = {
                    "id": first.get("did") or first.get("deviceId"),
                    "class": first.get("className", ""),
                    "resource": first.get("resource", ""),
                }
                self.hass.data[DOMAIN][self.config_entry.entry_id]["device"] = device_ctx

            device_id = device_ctx.get("id")
            device_sn = device_ctx.get("resource", "")
            device_class = device_ctx.get("class", "")

            _LOGGER.info(f"Floor Brush Light: Device context - ID: {device_id}, SN: {device_sn}, Class: {device_class}")

            # Send floor brush light command: led = 0 for on, led = 1 for off (inverted)
            command = {"led": 0 if on else 1}
            _LOGGER.info(f"Floor Brush Light: Sending command {command} to device {device_id}")

            result = await client.async_control_device(device_id, command, device_sn, device_class)

            if result:
                _LOGGER.info(f"✅ Floor Brush Light: Command sent successfully! State: {'ON' if on else 'OFF'}")
                _LOGGER.debug(f"Floor Brush Light: Full response: {result}")
                self._state = on
                self._last_command_time = datetime.now()
                self.async_write_ha_state()
            else:
                _LOGGER.error("❌ Floor Brush Light: Command failed - no result returned")
                _LOGGER.info("Floor Brush Light: Checking coordinator data for current 'led' field...")

                # Try to read current state to verify field exists
                coordinator = stored.get("coordinator")
                if coordinator and coordinator.data:
                    info = coordinator.data
                    _LOGGER.debug(f"Floor Brush Light: Available endpoints in coordinator data: {list(info.keys())}")

                    for endpoint in ['gci', 'cfp']:
                        if endpoint in info and isinstance(info[endpoint], dict):
                            if 'led' in info[endpoint]:
                                _LOGGER.info(f"Floor Brush Light: Found 'led' field in {endpoint}: {info[endpoint]['led']}")
                            else:
                                _LOGGER.warning(f"Floor Brush Light: 'led' field NOT found in {endpoint}")
                                _LOGGER.debug(f"Floor Brush Light: Available fields in {endpoint}: {list(info[endpoint].keys())}")

        except Exception as err:
            _LOGGER.error(f"❌ Floor Brush Light: Exception occurred - {err}", exc_info=True)

    async def async_update(self):
        """Update floor brush light switch state."""
        try:
            # Skip update if a command was sent recently (within 5 seconds)
            if self._last_command_time:
                time_since_command = datetime.now() - self._last_command_time
                if time_since_command < timedelta(seconds=5):
                    _LOGGER.debug(f"Floor Brush Light: Skipping update - recent command sent {time_since_command.total_seconds():.1f}s ago")
                    return

            stored = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {})
            coordinator = stored.get("coordinator")

            if coordinator and coordinator.data:
                # Get current floor brush light state from coordinator data
                info = coordinator.data
                _LOGGER.debug("Floor Brush Light: Updating state from coordinator data")

                # Check gci or cfp for led (floor brush light) field
                payload = None
                payload_source = None
                if isinstance(info, dict):
                    if 'gci' in info and isinstance(info['gci'], dict):
                        payload = info['gci']
                        payload_source = "gci"
                    elif 'cfp' in info and isinstance(info['cfp'], dict):
                        payload = info['cfp']
                        payload_source = "cfp"

                if payload:
                    if 'led' in payload:
                        # led = 0 means light on, led = 1 means light off (inverted)
                        old_state = self._state
                        self._state = payload['led'] == 0
                        _LOGGER.debug(f"Floor Brush Light: State from {payload_source}.led: {payload['led']} → {'ON' if self._state else 'OFF'}")
                        if old_state != self._state:
                            _LOGGER.info(f"Floor Brush Light: State changed from {'ON' if old_state else 'OFF'} to {'ON' if self._state else 'OFF'}")
                    else:
                        _LOGGER.debug(f"Floor Brush Light: 'led' field not found in {payload_source}")
                        _LOGGER.debug(f"Floor Brush Light: Available fields in {payload_source}: {list(payload.keys())[:20]}")
                else:
                    _LOGGER.debug("Floor Brush Light: No valid payload found in coordinator data")
            else:
                _LOGGER.debug("Floor Brush Light: No coordinator data available")

        except Exception as err:
            _LOGGER.error(f"Floor Brush Light: Error updating switch: {err}", exc_info=True)

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:lightbulb-on" if self._state else "mdi:lightbulb-off"


class TinecoWaterOnlyModeSwitch(TinecoBaseSwitch):
    """Switch for water only mode control."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant):
        """Initialize the water only mode switch."""
        super().__init__(config_entry, "water_only_mode", hass)
        self._state = False  # Assume water only mode is off by default
        # Override name with group prefix
        self._attr_name = "Tineco Water Mode: Enabled"

    async def _send_command(self, on: bool):
        """Send water only mode command using coordinated mode commands."""
        _LOGGER.info(f"Setting water only mode to {'ON' if on else 'OFF'}")
        try:
            # Import get_mode_state and send_mode_commands from select module
            from .select import get_mode_state, send_mode_commands

            # Update shared mode state
            mode_state = get_mode_state(self.hass, self.config_entry)
            mode_state["water_only_mode"] = on

            # Send all mode commands in sequence
            result = await send_mode_commands(self.hass, self.config_entry)

            if result:
                _LOGGER.info(f"Water only mode command sent successfully: {'ON' if on else 'OFF'}")
                self._state = on
                self._last_command_time = datetime.now()
                self.async_write_ha_state()
                
                # Immediately notify water mode entities to update their availability
                await self._update_water_mode_entities()
            else:
                _LOGGER.error("Failed to send water only mode command")

        except Exception as err:
            _LOGGER.error(f"Error sending water only mode command: {err}")

    async def _update_water_mode_entities(self):
        """Trigger immediate update of water mode dependent entities."""
        try:
            # Fire an event to trigger entity updates
            self.hass.bus.async_fire(
                f"{DOMAIN}_water_mode_changed",
                {"entry_id": self.config_entry.entry_id}
            )
            _LOGGER.debug("Fired water mode changed event")
        except Exception as err:
            _LOGGER.debug(f"Error firing water mode event: {err}")

    async def async_update(self):
        """Update water only mode switch state."""
        try:
            # Skip update if a command was sent recently (within 5 seconds)
            if self._last_command_time:
                time_since_command = datetime.now() - self._last_command_time
                if time_since_command < timedelta(seconds=5):
                    _LOGGER.debug(f"Skipping update - recent command sent {time_since_command.total_seconds():.1f}s ago")
                    return

            # Import functions from select module
            from .select import get_mode_state, update_mode_state_from_coordinator

            # Sync shared mode state with device state
            update_mode_state_from_coordinator(self.hass, self.config_entry)

            # Update from shared mode state which is synchronized with device
            mode_state = get_mode_state(self.hass, self.config_entry)
            self._state = mode_state.get("water_only_mode", False)

        except Exception as err:
            _LOGGER.debug(f"Error updating water only mode switch: {err}")

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:water" if self._state else "mdi:water-off"
