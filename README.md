# Tineco - Home Assistant HACS Integration

Control your Tineco smart devices through Home Assistant using this custom integration.

## What's New in v2.1.0

### China Region Phone Number Support
Chinese Tineco accounts use phone numbers instead of email addresses for login. The integration now supports this:

- The login field is now labelled **"Email or Phone Number"** — Chinese users can enter their phone number directly
- When region **CN** is selected, the integration automatically routes authentication through Tineco's SMS-based verification endpoints (`/user/sendSmsVerifyCode`, `/user/quickLoginByMobile`) instead of the email endpoints
- If a new device verification code (OTP) is triggered, Chinese users will receive an **SMS** to their phone number rather than an email
- All other regions continue to use email-based authentication unchanged

### Bug Fixes
- Fixed missing `translations/` directory — UI field labels were showing raw key names instead of translated strings

---

## What's New in v2.0.1

### New Controls
| Control | Type | Description |
|---------|------|-------------|
| Water Mode: Enabled | Switch | Enable/disable water-only cleaning mode |
| Floor Brush Light | Switch | Toggle floor brush LED light |
| Suction Mode: Power | Select | Adjust suction power (120W, 150W) |
| MAX Mode: Power | Select | Adjust MAX mode power (120W, 150W) |
| MAX Mode: Spray Volume | Select | Set MAX mode spray level (Rinse, Max) |
| Water Mode: Power | Select | Adjust water mode power (90W, 120W, 150W) |
| Water Mode: Spray Volume | Select | Set water mode spray level (Mist, Wet, Medium, Rinse, Max) |

### New Setup
During the integration setup the user can specify the region e.g IE for Ireland or PL for Poland. This is needed to succesfully authenticate

## Features

- **Device Discovery**: Automatically discovers Tineco devices in your account
- **Sensor Entities**: 
  - Firmware version
  - API version
  - Device model
  - Battery level
  - Vacuum status (idle, in_operation, self_cleaning, etc.)
  - Waste water tank status (clean/full)
  - Fresh water tank status (empty/full)
- **Switch Controls**:
  - Sound: Enabled (mute/unmute)
  - Water Mode: Enabled (enable/disable water-only mode)
  - Floor Brush Light on/off
- **Select Controls**:
  - Sound: Volume Level (Low, Medium, High)
  - Suction Mode: Power (120W, 150W)
  - MAX Mode: Power (120W, 150W)
  - MAX Mode: Spray Volume (Rinse, Max)
  - Water Mode: Power (90W, 120W, 150W) - *disabled when Water Mode is off*
  - Water Mode: Spray Volume (Mist, Wet, Medium, Rinse, Max) - *disabled when Water Mode is off*
- **Binary Sensors**:
  - Online status
  - Charging status
- **Smart Controls**:
  - Water Mode controls are automatically disabled (greyed out) when Water Mode is turned off
  - Grouped entity naming for easy organization
- **Configuration UI**: Easy setup through Home Assistant UI
- **Multi-language Support**: English and Spanish

### Improvements
- **Smart Availability**: Water Mode controls automatically grey out when Water Mode is disabled
- **Grouped Entity Naming**: Related controls are now prefixed (e.g., "Tineco Sound:", "Tineco Water Mode:")
- **Instant UI Updates**: Control availability updates immediately when toggling Water Mode
- **Coordinated Mode Commands**: Mode changes now send properly synchronized commands to the device
- **Renamed Integration**: Changed from "Tineco IoT" to "Tineco" for simplicity


## Installation

### Via HACS
Note: Ensure your Tineco device is powered on and connected to the app before adding the integration

1. Go to **HACS** → **Integrations**
2. Click the three dots menu → **Custom repositories**
3. Add: `https://github.com/wheeller123/Tineco-HACS-Integration`
4. Category: `Integration`
5. Search for "Tineco"
6. Click **Install**
7. Restart Home Assistant
8. Go to **Settings** → **Devices & Services** → **Add Integration**
9. Search for "Tineco" and configure

### Manual Installation

1. Copy the `custom_components/tineco` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Go to **Settings** → **Devices & Services** → **Add Integration**
4. Search for "Tineco" and configure

## Configuration

### Via UI (Recommended)

1. In Home Assistant, go to **Settings** → **Devices & Services**
2. Click **Create Integration** (+ button)
3. Search for "Tineco"
4. Enter your Tineco account email (or phone number for CN region) and password
5. Click **Submit**

## Usage

Once configured, the integration will create the following entities:

### Sensors
- `sensor.tineco_firmware_version` - Firmware version
- `sensor.tineco_api_version` - API version  
- `sensor.tineco_model` - Device model (e.g., S7 Flashdry)
- `sensor.tineco_battery` - Battery level percentage
- `sensor.tineco_vacuum_status` - Current vacuum status (idle, in_operation, self_cleaning, docked_standby)
- `sensor.tineco_waste_water_tank_status` - Waste water tank status (clean/full)
- `sensor.tineco_fresh_water_tank_status` - Fresh water tank status (empty/full)

### Switches
- `switch.tineco_sound_enabled` - Sound on/off (mute/unmute control)
- `switch.tineco_water_mode_enabled` - Water-only mode on/off
- `switch.tineco_floor_brush_light` - Floor brush light on/off

### Selects
- `select.tineco_sound_volume_level` - Volume level selection (Low, Medium, High)
- `select.tineco_suction_mode_power` - Suction mode power (120W, 150W)
- `select.tineco_max_mode_power` - MAX mode power (120W, 150W)
- `select.tineco_max_mode_spray_volume` - MAX mode spray volume (Rinse, Max)
- `select.tineco_water_mode_power` - Water mode power (90W, 120W, 150W) - *unavailable when water mode is off*
- `select.tineco_water_mode_spray_volume` - Water mode spray volume (Mist, Wet, Medium, Rinse, Max) - *unavailable when water mode is off*

### Binary Sensors
- `binary_sensor.tineco_online` - Device online status
- `binary_sensor.tineco_charging` - Charging status

### Entity Grouping

Entities are named with prefixes for easy grouping in the UI:
- **Sound**: `Tineco Sound: Enabled`, `Tineco Sound: Volume Level`
- **Suction Mode**: `Tineco Suction Mode: Power`
- **MAX Mode**: `Tineco MAX Mode: Power`, `Tineco MAX Mode: Spray Volume`
- **Water Mode**: `Tineco Water Mode: Enabled`, `Tineco Water Mode: Power`, `Tineco Water Mode: Spray Volume`

### Automation Examples

#### Remind to empty tank after self-cleaning

```yaml
- alias: "Remind to empty tank after self-cleaning"
  trigger:
    - platform: state
      entity_id: sensor.tineco_vacuum_status
      from: "self_cleaning"
      to: "idle"
  action:
    - service: notify.mobile_app_your_phone
      data:
        title: "Tineco Cleaning Complete"
        message: "Self-cleaning cycle finished. Remember to empty the waste water tank!"
```

#### Notify when fresh water tank is empty

```yaml
- alias: "Notify when fresh water tank is empty"
  trigger:
    - platform: state
      entity_id: sensor.fresh_water_tank_status
      to: "empty"
  action:
    - service: notify.notify
      data:
        message: "Tineco fresh water tank needs refilling"
```

#### Notify when waste water tank is full

```yaml
- alias: "Notify when waste water tank is full"
  trigger:
    - platform: state
      entity_id: sensor.waste_water_tank_status
      to: "full"
  action:
    - service: notify.notify
      data:
        message: "Tineco waste water tank needs emptying"
```

#### Notify when Tineco goes offline

```yaml
- alias: "Notify when Tineco goes offline"
  trigger:
    - platform: state
      entity_id: binary_sensor.tineco_online
      to: "off"
  action:
    - service: notify.notify
      data:
        message: "Your Tineco device is offline"
```

## Troubleshooting

### Invalid Authentication Error

- Double-check your credentials (email or phone number) and password
- Chinese users: ensure you are entering your phone number and have selected **CN** as the region
- Ensure your Tineco account is active
- Try resetting your Tineco password on the official app

## API Queries Used

This integration uses the following device queries:

- **GCI** (Get Controller Info) - Battery level, vacuum status, water tank status, error codes
- **GAV** (Get API Version) - Firmware version information
- **GCF** (Get Config File) - Device configuration
- **CFP** (Get Config Point) - Configuration points including status data
- **QueryMode** - Query current device mode configuration
- **UpdateMode** - Update mode settings (suction power, MAX mode, water mode)
- **DeleteMode** - Delete/disable a mode (e.g., disable water-only mode)

### Mode Commands

The integration sends coordinated mode commands when changing mode settings:

1. **UpdateMode** - Suction mode (md=4) with power setting
2. **UpdateMode** - MAX mode (md=3) with power and spray settings
3. **UpdateMode/DeleteMode** - Water mode (md=6) - UpdateMode when enabled, DeleteMode when disabled
4. **QueryMode** - Verify current configuration

### Key API Fields

- `bp` - Battery percentage (0-100)
- `wm` - Working mode (0=Idle, 2=Charging, 3/4=In Operation, 8=Docked/Standby, 10=Self-cleaning)
- `e1` - Error code 1 (waste water tank issues)
- `e2` - Error code 2 (64 = fresh water tank empty)
- `e3` - Error code 3 (other errors)
- `vs` - Device online status
- `wp` - Water pressure/percentage
- `vl` - Volume level (1=Low, 2=Medium, 3=High)
- `ms` - Mute status (0=unmuted, 1=muted)

## Support

- GitHub Issues: https://github.com/wheeller123/Tineco-HACS-Integration/issues
- Home Assistant Community: https://community.home-assistant.io/

## Credits

Created by Jack Whelan

## Disclaimer

This integration is not affiliated with Tineco. It uses reverse-engineered APIs. Use at your own risk. I developed this specifically for my S7 Flashdry, it may not work with other models but I am happy to try and add others with community support

## License

MIT License - See LICENSE file for details
