"""Select platform for Tineco integration."""

import logging
from datetime import datetime, timedelta
from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

DOMAIN = "tineco"

# Volume level mapping
VOLUME_LEVELS = {
    "Low": 1,
    "Medium": 2,
    "High": 3,
}

# Running speed mapping
RUNNING_SPEED_LEVELS = {
    "Soft": 0,
    "Medium": 1,
    "Max": 2,
}

# Cleaning method mapping
CLEANING_METHOD_LEVELS = {
    "Clean water": 0,
    "Detergent": 1,
}

# Suction power mapping (120W or 150W)
SUCTION_POWER_LEVELS = {
    "120W": 1,
    "150W": 2,
}

# MAX power mapping (120W or 150W)
MAX_POWER_LEVELS = {
    "120W": 1,
    "150W": 2,
}

# MAX mode spray volume mapping (only Rinse or Max)
MAX_SPRAY_VOLUME_LEVELS = {
    "Rinse": 3,
    "Max": 4,
}

# Water mode spray volume mapping (Mist, Wet, Medium, Rinse, Max)
WATER_MODE_SPRAY_VOLUME_LEVELS = {
    "Mist": 0,
    "Wet": 1,
    "Medium": 2,
    "Rinse": 3,
    "Max": 4,
}

# Water mode power mapping (90W, 120W, 150W)
WATER_MODE_POWER_LEVELS = {
    "90W": 0,
    "120W": 1,
    "150W": 2,
}


def get_mode_state(hass: HomeAssistant, config_entry: ConfigEntry) -> dict:
    """Get or initialize the shared mode state for interdependent controls."""
    stored = hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {})

    if "mode_state" not in stored:
        # Initialize with default values
        stored["mode_state"] = {
            "suction_power": 2,              # Default to 150W
            "max_power": 2,                  # Default to 150W
            "max_spray_volume": 3,           # Default to Rinse
            "water_only_mode": False,        # Default to OFF
            "water_mode_power": 1,           # Default to 120W
            "water_mode_spray_volume": 3,    # Default to Rinse
        }
        hass.data[DOMAIN][config_entry.entry_id] = stored

    return stored["mode_state"]


def update_mode_state_from_coordinator(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Update shared mode state from coordinator data (device state)."""
    try:
        stored = hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {})
        coordinator = stored.get("coordinator")

        if not coordinator or not coordinator.data:
            return

        mode_state = get_mode_state(hass, config_entry)
        info = coordinator.data

        # Get payload from gci or cfp
        payload = None
        if isinstance(info, dict):
            if 'gci' in info and isinstance(info['gci'], dict):
                payload = info['gci']
            elif 'cfp' in info and isinstance(info['cfp'], dict):
                payload = info['cfp']

        if not payload:
            return

        # Update mode state from device payload
        # Note: The device may not expose all mode parameters directly
        # We'll update what we can find

        # Check for water mode spray volume (wp field)
        if 'wp' in payload:
            water_spray = payload['wp']
            mode_state["water_mode_spray_volume"] = water_spray
            # Also update MAX spray if it's Rinse or Max
            if water_spray >= 3:
                mode_state["max_spray_volume"] = water_spray

        # Check for water only mode (wom field)
        if 'wom' in payload:
            mode_state["water_only_mode"] = payload['wom'] == 1

        _LOGGER.debug(f"Updated mode state from coordinator: {mode_state}")

    except Exception as err:
        _LOGGER.debug(f"Error updating mode state from coordinator: {err}")


async def send_mode_commands(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Send all 4 mode commands in sequence when any interdependent control changes."""
    try:
        mode_state = get_mode_state(hass, config_entry)

        from .client import async_get_or_create_client
        client = await async_get_or_create_client(hass, config_entry)
        if client is None:
            _LOGGER.error("Failed to login for mode commands")
            return False

        stored = hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {})
        device_ctx = stored.get("device")
        if not device_ctx:
            devices = await client.async_get_devices()
            if not devices or not client.devices:
                _LOGGER.error("No devices found for mode commands")
                return False
            first = client.devices[0]
            device_ctx = {
                "id": first.get("did") or first.get("deviceId"),
                "class": first.get("className", ""),
                "resource": first.get("resource", ""),
            }
            hass.data[DOMAIN][config_entry.entry_id]["device"] = device_ctx

        device_id = device_ctx.get("id")
        device_sn = device_ctx.get("resource", "")
        device_class = device_ctx.get("class", "")

        # Build the 4 mode commands with their corresponding actions
        # Command 1 & 2: UpdateMode, Command 3: DeleteMode/UpdateMode, Command 4: QueryMode
        commands = []

        # Command 1: Suction mode (md=4) - UpdateMode
        cmd1 = ({"md": 4, "vm": mode_state["suction_power"]}, "UpdateMode")
        commands.append(cmd1)

        # Command 2: MAX mode (md=3) - UpdateMode
        cmd2 = ({"md": 3, "vm": mode_state["max_power"], "wm": mode_state["max_spray_volume"]}, "UpdateMode")
        commands.append(cmd2)

        # Command 3: Water mode (md=6)
        if mode_state["water_only_mode"]:
            # Water mode ON - use UpdateMode with power and spray volume
            cmd3 = ({
                "md": 6,
                "vm": mode_state["water_mode_power"],
                "wm": mode_state["water_mode_spray_volume"]
            }, "UpdateMode")
        else:
            # Water mode OFF - use DeleteMode
            cmd3 = ({"md": 6}, "DeleteMode")
        commands.append(cmd3)

        # Command 4: Query current mode configuration - QueryMode
        cmd4 = ({}, "QueryMode")
        commands.append(cmd4)

        # Send all commands in sequence
        _LOGGER.info(f"Sending {len(commands)} mode commands in sequence...")
        for i, (command, action) in enumerate(commands, 1):
            _LOGGER.info(f"  Command {i}/{len(commands)} (action={action}): {command}")
            result = await client.async_control_device(device_id, command, device_sn, device_class, action=action)

            if not result:
                _LOGGER.error(f"  Failed to send command {i}: {command} - No response received")
                return False

            # Validate response - {"ret": "ok"} for UpdateMode/DeleteMode, {"cfg": [...]} for QueryMode
            if isinstance(result, dict) and (result.get("ret") == "ok" or "cfg" in result):
                _LOGGER.info(f"  ✓ Command {i} successful: {result}")
            else:
                _LOGGER.warning(f"  Command {i} sent but unexpected response: {result}")

            _LOGGER.debug(f"  Command {i} full result: {result}")

        _LOGGER.info("All mode commands sent successfully")
        return True

    except Exception as err:
        _LOGGER.error(f"Error sending mode commands: {err}")
        return False


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select platform from a config entry."""

    # Initialize mode state
    get_mode_state(hass, config_entry)

    # Add all select controls
    selects = [
        TinecoVolumeSelect(config_entry, hass),
        TinecoRunningSpeedSelect(config_entry, hass),
        TinecoCleaningMethodSelect(config_entry, hass),
        TinecoSuctionPowerSelect(config_entry, hass),
        TinecoMaxPowerSelect(config_entry, hass),
        TinecoMaxSprayVolumeSelect(config_entry, hass),
        TinecoWaterModePowerSelect(config_entry, hass),
        TinecoWaterModeSprayVolumeSelect(config_entry, hass),
    ]

    async_add_entities(selects)


class TinecoVolumeSelect(SelectEntity):
    """Select entity for Tineco volume level control."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant):
        """Initialize the volume select."""
        self.config_entry = config_entry
        self.hass = hass
        self._attr_should_poll = True
        self._attr_options = list(VOLUME_LEVELS.keys())
        self._attr_current_option = "Low"
        self._last_command_time = None
        
        email = config_entry.data.get("email", "")
        self._attr_unique_id = f"{DOMAIN}_{email}_volume_level"
        self._attr_name = "Tineco Sound: Volume Level"
        self._attr_icon = "mdi:volume-high"

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
    def current_option(self) -> str:
        """Return the current selected option."""
        return self._attr_current_option

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in VOLUME_LEVELS:
            _LOGGER.error(f"Invalid volume level: {option}")
            return
        
        volume_value = VOLUME_LEVELS[option]
        _LOGGER.info(f"Setting volume level to {option} (vl={volume_value})")
        
        try:
            from .client import async_get_or_create_client
            client = await async_get_or_create_client(self.hass, self.config_entry)
            if client is None:
                _LOGGER.error("Failed to login for volume level command")
                return

            stored = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {})
            device_ctx = stored.get("device")
            if not device_ctx:
                devices = await client.async_get_devices()
                if not devices or not client.devices:
                    _LOGGER.error("No devices found for volume level command")
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
            
            # Send volume level command
            command = {"vl": volume_value}
            _LOGGER.info(f"Sending volume level command to device {device_id}: {command}")
            result = await client.async_control_device(device_id, command, device_sn, device_class)
            
            if result:
                _LOGGER.info(f"Volume level command sent successfully: {option}, result: {result}")
                self._attr_current_option = option
                self._last_command_time = datetime.now()
                self.async_write_ha_state()
            else:
                _LOGGER.error("Failed to send volume level command - no result returned")
                
        except Exception as err:
            _LOGGER.error(f"Error sending volume level command: {err}")

    async def async_update(self):
        """Update volume level state."""
        try:
            # Skip update if a command was sent recently (within 5 seconds)
            if self._last_command_time:
                time_since_command = datetime.now() - self._last_command_time
                if time_since_command < timedelta(seconds=5):
                    _LOGGER.debug(f"Skipping update - recent command sent {time_since_command.total_seconds():.1f}s ago")
                    return
            
            stored = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {})
            coordinator = stored.get("coordinator")
            
            if coordinator and coordinator.data:
                # Get current volume level from coordinator data
                info = coordinator.data
                
                # Check gci or cfp for vl (volume level) field
                payload = None
                if isinstance(info, dict):
                    if 'gci' in info and isinstance(info['gci'], dict):
                        payload = info['gci']
                    elif 'cfp' in info and isinstance(info['cfp'], dict):
                        payload = info['cfp']
                
                if payload and 'vl' in payload:
                    vl_value = payload['vl']
                    # Map vl value to option name
                    for level_name, level_value in VOLUME_LEVELS.items():
                        if level_value == vl_value:
                            self._attr_current_option = level_name
                            break
                    
        except Exception as err:
            _LOGGER.debug(f"Error updating volume level select: {err}")


class TinecoBaseSelect(SelectEntity):
    """Base class for Tineco select entities."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant, select_type: str,
                 options_dict: dict, command_key: str, icon: str):
        """Initialize the select."""
        self.config_entry = config_entry
        self.hass = hass
        self.select_type = select_type
        self.options_dict = options_dict
        self.command_key = command_key
        self._attr_should_poll = True
        self._attr_options = list(options_dict.keys())
        self._attr_current_option = list(options_dict.keys())[0]
        self._last_command_time = None
        self._attr_icon = icon

        email = config_entry.data.get("email", "")
        self._attr_unique_id = f"{DOMAIN}_{email}_{select_type}"
        self._attr_name = f"Tineco {select_type.replace('_', ' ').title()}"

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
    def current_option(self) -> str:
        """Return the current selected option."""
        return self._attr_current_option

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in self.options_dict:
            _LOGGER.error(f"Invalid {self.select_type}: {option}")
            return

        value = self.options_dict[option]
        _LOGGER.info(f"Setting {self.select_type} to {option} ({self.command_key}={value})")

        try:
            from .client import async_get_or_create_client
            client = await async_get_or_create_client(self.hass, self.config_entry)
            if client is None:
                _LOGGER.error(f"Failed to login for {self.select_type} command")
                return

            stored = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {})
            device_ctx = stored.get("device")
            if not device_ctx:
                devices = await client.async_get_devices()
                if not devices or not client.devices:
                    _LOGGER.error(f"No devices found for {self.select_type} command")
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

            # Send command
            command = {self.command_key: value}
            _LOGGER.info(f"Sending {self.select_type} command to device {device_id}: {command}")
            result = await client.async_control_device(device_id, command, device_sn, device_class)

            if result:
                _LOGGER.info(f"{self.select_type} command sent successfully: {option}, result: {result}")
                self._attr_current_option = option
                self._last_command_time = datetime.now()
                self.async_write_ha_state()
            else:
                _LOGGER.error(f"Failed to send {self.select_type} command - no result returned")

        except Exception as err:
            _LOGGER.error(f"Error sending {self.select_type} command: {err}")

    async def async_update(self):
        """Update select state."""
        try:
            # Skip update if a command was sent recently (within 5 seconds)
            if self._last_command_time:
                time_since_command = datetime.now() - self._last_command_time
                if time_since_command < timedelta(seconds=5):
                    _LOGGER.debug(f"Skipping update - recent command sent {time_since_command.total_seconds():.1f}s ago")
                    return

            stored = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {})
            coordinator = stored.get("coordinator")

            if coordinator and coordinator.data:
                # Get current value from coordinator data
                info = coordinator.data

                # Check gci or cfp for the command key field
                payload = None
                if isinstance(info, dict):
                    if 'gci' in info and isinstance(info['gci'], dict):
                        payload = info['gci']
                    elif 'cfp' in info and isinstance(info['cfp'], dict):
                        payload = info['cfp']

                if payload and self.command_key in payload:
                    current_value = payload[self.command_key]
                    # Map value to option name
                    for option_name, option_value in self.options_dict.items():
                        if option_value == current_value:
                            self._attr_current_option = option_name
                            break

        except Exception as err:
            _LOGGER.debug(f"Error updating {self.select_type} select: {err}")


class TinecoRunningSpeedSelect(TinecoBaseSelect):
    """Select entity for Tineco running speed control."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant):
        """Initialize the running speed select."""
        super().__init__(
            config_entry,
            hass,
            "running_speed",
            RUNNING_SPEED_LEVELS,
            "wheel",  # Running Speed command key
            "mdi:speedometer"
        )


class TinecoCleaningMethodSelect(TinecoBaseSelect):
    """Select entity for Tineco cleaning method control."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant):
        """Initialize the cleaning method select."""
        super().__init__(
            config_entry,
            hass,
            "cleaning_method",
            CLEANING_METHOD_LEVELS,
            "cleanway",  # Cleaning Method command key
            "mdi:spray-bottle"
        )


class TinecoSuctionPowerSelect(TinecoBaseSelect):
    """Select entity for Tineco suction power control."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant):
        """Initialize the suction power select."""
        super().__init__(
            config_entry,
            hass,
            "suction_power",
            SUCTION_POWER_LEVELS,
            "sp",  # Suction Power command key
            "mdi:vacuum"
        )
        # Override name with group prefix
        self._attr_name = "Tineco Suction Mode: Power"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option using coordinated mode commands."""
        if option not in self.options_dict:
            _LOGGER.error(f"Invalid {self.select_type}: {option}")
            return

        value = self.options_dict[option]
        _LOGGER.info(f"Setting {self.select_type} to {option} (value={value})")

        try:
            # Update shared mode state
            mode_state = get_mode_state(self.hass, self.config_entry)
            mode_state["suction_power"] = value

            # Send all mode commands in sequence
            result = await send_mode_commands(self.hass, self.config_entry)

            if result:
                _LOGGER.info(f"{self.select_type} command sent successfully: {option}")
                self._attr_current_option = option
                self._last_command_time = datetime.now()
                self.async_write_ha_state()
            else:
                _LOGGER.error(f"Failed to send {self.select_type} command")

        except Exception as err:
            _LOGGER.error(f"Error sending {self.select_type} command: {err}")

    async def async_update(self):
        """Update select state from device."""
        try:
            # Skip update if a command was sent recently (within 5 seconds)
            if self._last_command_time:
                time_since_command = datetime.now() - self._last_command_time
                if time_since_command < timedelta(seconds=5):
                    _LOGGER.debug(f"Skipping update - recent command sent {time_since_command.total_seconds():.1f}s ago")
                    return

            # Sync shared mode state with device state
            update_mode_state_from_coordinator(self.hass, self.config_entry)

            # Update from shared mode state which is synchronized with device
            mode_state = get_mode_state(self.hass, self.config_entry)
            current_value = mode_state.get("suction_power", 2)

            # Map value to option name
            for option_name, option_value in self.options_dict.items():
                if option_value == current_value:
                    self._attr_current_option = option_name
                    break

        except Exception as err:
            _LOGGER.debug(f"Error updating {self.select_type} select: {err}")


class TinecoMaxPowerSelect(TinecoBaseSelect):
    """Select entity for Tineco MAX power control."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant):
        """Initialize the MAX power select."""
        super().__init__(
            config_entry,
            hass,
            "max_power",
            MAX_POWER_LEVELS,
            "mp",  # MAX Power command key
            "mdi:flash"
        )
        # Override name with group prefix
        self._attr_name = "Tineco MAX Mode: Power"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option using coordinated mode commands."""
        if option not in self.options_dict:
            _LOGGER.error(f"Invalid {self.select_type}: {option}")
            return

        value = self.options_dict[option]
        _LOGGER.info(f"Setting {self.select_type} to {option} (value={value})")

        try:
            # Update shared mode state
            mode_state = get_mode_state(self.hass, self.config_entry)
            mode_state["max_power"] = value

            # Send all mode commands in sequence
            result = await send_mode_commands(self.hass, self.config_entry)

            if result:
                _LOGGER.info(f"{self.select_type} command sent successfully: {option}")
                self._attr_current_option = option
                self._last_command_time = datetime.now()
                self.async_write_ha_state()
            else:
                _LOGGER.error(f"Failed to send {self.select_type} command")

        except Exception as err:
            _LOGGER.error(f"Error sending {self.select_type} command: {err}")

    async def async_update(self):
        """Update select state from device."""
        try:
            # Skip update if a command was sent recently (within 5 seconds)
            if self._last_command_time:
                time_since_command = datetime.now() - self._last_command_time
                if time_since_command < timedelta(seconds=5):
                    _LOGGER.debug(f"Skipping update - recent command sent {time_since_command.total_seconds():.1f}s ago")
                    return

            # Sync shared mode state with device state
            update_mode_state_from_coordinator(self.hass, self.config_entry)

            # Update from shared mode state which is synchronized with device
            mode_state = get_mode_state(self.hass, self.config_entry)
            current_value = mode_state.get("max_power", 2)

            # Map value to option name
            for option_name, option_value in self.options_dict.items():
                if option_value == current_value:
                    self._attr_current_option = option_name
                    break

        except Exception as err:
            _LOGGER.debug(f"Error updating {self.select_type} select: {err}")


class TinecoMaxSprayVolumeSelect(TinecoBaseSelect):
    """Select entity for Tineco MAX mode spray volume control."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant):
        """Initialize the MAX spray volume select."""
        super().__init__(
            config_entry,
            hass,
            "max_spray_volume",
            MAX_SPRAY_VOLUME_LEVELS,
            "wm",  # MAX spray command key
            "mdi:spray"
        )
        # Override name with group prefix
        self._attr_name = "Tineco MAX Mode: Spray Volume"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option using coordinated mode commands."""
        if option not in self.options_dict:
            _LOGGER.error(f"Invalid {self.select_type}: {option}")
            return

        value = self.options_dict[option]
        _LOGGER.info(f"Setting {self.select_type} to {option} (value={value})")

        try:
            # Update shared mode state
            mode_state = get_mode_state(self.hass, self.config_entry)
            mode_state["max_spray_volume"] = value

            # Send all mode commands in sequence
            result = await send_mode_commands(self.hass, self.config_entry)

            if result:
                _LOGGER.info(f"{self.select_type} command sent successfully: {option}")
                self._attr_current_option = option
                self._last_command_time = datetime.now()
                self.async_write_ha_state()
            else:
                _LOGGER.error(f"Failed to send {self.select_type} command")

        except Exception as err:
            _LOGGER.error(f"Error sending {self.select_type} command: {err}")

    async def async_update(self):
        """Update select state from device."""
        try:
            # Skip update if a command was sent recently (within 5 seconds)
            if self._last_command_time:
                time_since_command = datetime.now() - self._last_command_time
                if time_since_command < timedelta(seconds=5):
                    _LOGGER.debug(f"Skipping update - recent command sent {time_since_command.total_seconds():.1f}s ago")
                    return

            # Sync shared mode state with device state
            update_mode_state_from_coordinator(self.hass, self.config_entry)

            # Update from shared mode state which is synchronized with device
            mode_state = get_mode_state(self.hass, self.config_entry)
            current_value = mode_state.get("max_spray_volume", 3)

            # Map value to option name
            for option_name, option_value in self.options_dict.items():
                if option_value == current_value:
                    self._attr_current_option = option_name
                    break

        except Exception as err:
            _LOGGER.debug(f"Error updating {self.select_type} select: {err}")


class TinecoWaterModePowerSelect(TinecoBaseSelect):
    """Select entity for Tineco water mode power control."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant):
        """Initialize the water mode power select."""
        super().__init__(
            config_entry,
            hass,
            "water_mode_power",
            WATER_MODE_POWER_LEVELS,
            "vm",  # Water mode power command key
            "mdi:lightning-bolt"
        )
        # Override name with group prefix
        self._attr_name = "Tineco Water Mode: Power"
        self._remove_listener = None

    async def async_added_to_hass(self):
        """Register event listener when entity is added."""
        await super().async_added_to_hass()
        
        async def handle_water_mode_changed(event):
            """Handle water mode changed event."""
            if event.data.get("entry_id") == self.config_entry.entry_id:
                self.async_write_ha_state()
        
        self._remove_listener = self.hass.bus.async_listen(
            f"{DOMAIN}_water_mode_changed",
            handle_water_mode_changed
        )

    async def async_will_remove_from_hass(self):
        """Remove event listener when entity is removed."""
        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None

    @property
    def available(self) -> bool:
        """Return True if entity is available (water mode is enabled)."""
        try:
            mode_state = get_mode_state(self.hass, self.config_entry)
            return mode_state.get("water_only_mode", False)
        except Exception:
            return False

    async def async_select_option(self, option: str) -> None:
        """Change the selected option using coordinated mode commands."""
        if option not in self.options_dict:
            _LOGGER.error(f"Invalid {self.select_type}: {option}")
            return

        value = self.options_dict[option]
        _LOGGER.info(f"Setting {self.select_type} to {option} (value={value})")

        try:
            # Update shared mode state
            mode_state = get_mode_state(self.hass, self.config_entry)
            mode_state["water_mode_power"] = value

            # Send all mode commands in sequence
            result = await send_mode_commands(self.hass, self.config_entry)

            if result:
                _LOGGER.info(f"{self.select_type} command sent successfully: {option}")
                self._attr_current_option = option
                self._last_command_time = datetime.now()
                self.async_write_ha_state()
            else:
                _LOGGER.error(f"Failed to send {self.select_type} command")

        except Exception as err:
            _LOGGER.error(f"Error sending {self.select_type} command: {err}")

    async def async_update(self):
        """Update select state from device."""
        try:
            # Skip update if a command was sent recently (within 5 seconds)
            if self._last_command_time:
                time_since_command = datetime.now() - self._last_command_time
                if time_since_command < timedelta(seconds=5):
                    _LOGGER.debug(f"Skipping update - recent command sent {time_since_command.total_seconds():.1f}s ago")
                    return

            # Sync shared mode state with device state
            update_mode_state_from_coordinator(self.hass, self.config_entry)

            # Update from shared mode state which is synchronized with device
            mode_state = get_mode_state(self.hass, self.config_entry)
            current_value = mode_state.get("water_mode_power", 1)

            # Map value to option name
            for option_name, option_value in self.options_dict.items():
                if option_value == current_value:
                    self._attr_current_option = option_name
                    break

        except Exception as err:
            _LOGGER.debug(f"Error updating {self.select_type} select: {err}")


class TinecoWaterModeSprayVolumeSelect(TinecoBaseSelect):
    """Select entity for Tineco water mode spray volume control."""

    def __init__(self, config_entry: ConfigEntry, hass: HomeAssistant):
        """Initialize the water mode spray volume select."""
        super().__init__(
            config_entry,
            hass,
            "water_mode_spray_volume",
            WATER_MODE_SPRAY_VOLUME_LEVELS,
            "wm",  # Water mode spray command key
            "mdi:water-percent"
        )
        # Override name with group prefix
        self._attr_name = "Tineco Water Mode: Spray Volume"
        self._remove_listener = None

    async def async_added_to_hass(self):
        """Register event listener when entity is added."""
        await super().async_added_to_hass()
        
        async def handle_water_mode_changed(event):
            """Handle water mode changed event."""
            if event.data.get("entry_id") == self.config_entry.entry_id:
                self.async_write_ha_state()
        
        self._remove_listener = self.hass.bus.async_listen(
            f"{DOMAIN}_water_mode_changed",
            handle_water_mode_changed
        )

    async def async_will_remove_from_hass(self):
        """Remove event listener when entity is removed."""
        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None

    @property
    def available(self) -> bool:
        """Return True if entity is available (water mode is enabled)."""
        try:
            mode_state = get_mode_state(self.hass, self.config_entry)
            return mode_state.get("water_only_mode", False)
        except Exception:
            return False

    async def async_select_option(self, option: str) -> None:
        """Change the selected option using coordinated mode commands."""
        if option not in self.options_dict:
            _LOGGER.error(f"Invalid {self.select_type}: {option}")
            return

        value = self.options_dict[option]
        _LOGGER.info(f"Setting {self.select_type} to {option} (value={value})")

        try:
            # Update shared mode state
            mode_state = get_mode_state(self.hass, self.config_entry)
            mode_state["water_mode_spray_volume"] = value

            # Send all mode commands in sequence
            result = await send_mode_commands(self.hass, self.config_entry)

            if result:
                _LOGGER.info(f"{self.select_type} command sent successfully: {option}")
                self._attr_current_option = option
                self._last_command_time = datetime.now()
                self.async_write_ha_state()
            else:
                _LOGGER.error(f"Failed to send {self.select_type} command")

        except Exception as err:
            _LOGGER.error(f"Error sending {self.select_type} command: {err}")

    async def async_update(self):
        """Update select state from device."""
        try:
            # Skip update if a command was sent recently (within 5 seconds)
            if self._last_command_time:
                time_since_command = datetime.now() - self._last_command_time
                if time_since_command < timedelta(seconds=5):
                    _LOGGER.debug(f"Skipping update - recent command sent {time_since_command.total_seconds():.1f}s ago")
                    return

            # Sync shared mode state with device state
            update_mode_state_from_coordinator(self.hass, self.config_entry)

            # Update from shared mode state which is synchronized with device
            mode_state = get_mode_state(self.hass, self.config_entry)
            current_value = mode_state.get("water_mode_spray_volume", 3)

            # Map value to option name
            for option_name, option_value in self.options_dict.items():
                if option_value == current_value:
                    self._attr_current_option = option_name
                    break

        except Exception as err:
            _LOGGER.debug(f"Error updating {self.select_type} select: {err}")


