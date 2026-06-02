# Tineco - Home Assistant HACS Integration

Control your Tineco smart devices through Home Assistant using this custom integration.

Current version: **2.4.1** — supports global (`IE`, `US`, etc.) and China (`CN`) regions. Developed against the S7 Flashdry; other models (incl. Floor One S5 / S5 Pro) work with community feedback.

### Community Lovelace Card

A custom Lovelace card for Tineco devices is available: [lovelace-tineco-card](https://github.com/MattiaSaiko/lovelace-tineco-card)


## What's New

### 2.4.1

- **Water tank statuses now work.** Both the *waste/dirty* and *fresh/clean*
  tank sensors now track correctly on the S7 Flashdry, verified against captured
  full↔empty transitions. The `e2` field is a bitmask: bit `256` = waste tank
  full, bit `64` = fresh tank empty (the fresh tank also corroborates via the
  `wp` level flipping 238→239). Previously the waste tank was stuck on *Clean*
  and the fresh tank didn't track properly. Great for "empty the tank" /
  "refill water" reminder automations. (#29)
- **Online sensor no longer flips to *off* by mistake.** The online and charging
  binary sensors used to run their own slow API calls — which timed out, logged
  *"taking over 10 seconds"* warnings, and reported the wrong state. They now
  follow the integration's shared update cycle: online simply reflects whether the
  last poll reached the device.
- **Quieter, faster polling.** The occasionally-unresponsive `gcf` request is now
  best-effort with a short timeout, and its repeated `Read timed out` messages are
  no longer logged as errors every cycle. Device state comes from the other
  endpoints, so a `gcf` hiccup no longer slows down or fails a refresh. (#29)

See [CHANGELOG.md](CHANGELOG.md) for the full history.


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
  - Water Mode: Power (90W, 120W, 150W) — *disabled when Water Mode is off*
  - Water Mode: Spray Volume (Mist, Wet, Medium, Rinse, Max) — *disabled when Water Mode is off*
- **Binary Sensors**:
  - Online status
  - Charging status
- **Smart Controls**:
  - Water Mode controls automatically grey out when Water Mode is disabled
  - Grouped entity naming for easy organization
- **Configuration UI**: Setup through the Home Assistant UI
- **Multi-region**: Global (`IE`, `US`, …) and China (`CN`) — the integration picks the correct host, org, and country at runtime
- **Multi-language**: English and Spanish


## Installation

### Via HACS

> Make sure the device is powered on and paired in the Tineco app before adding the integration.

1. Open **HACS** → **Integrations**
2. Three-dots menu → **Custom repositories**
3. Add `https://github.com/wheeller123/Tineco-HACS-Integration` with category **Integration**
4. Search for **Tineco** and install
5. Restart Home Assistant
6. **Settings** → **Devices & Services** → **Add Integration** → search for **Tineco**

### Manual installation

1. Copy `custom_components/tineco/` into your Home Assistant `custom_components/` directory
2. Restart Home Assistant
3. **Settings** → **Devices & Services** → **Add Integration** → search for **Tineco**


## Configuration

1. **Settings** → **Devices & Services** → **+ Add Integration**
2. Search for **Tineco**
3. Enter your Tineco account email (or phone number for the CN region) and password
4. Pick the correct region (`CN` for mainland China accounts, otherwise your global region code)
5. **Submit**


## Entities

### Sensors
- `sensor.tineco_firmware_version` — firmware version
- `sensor.tineco_api_version` — API version
- `sensor.tineco_model` — device model (e.g. *S7 Flashdry*)
- `sensor.tineco_battery` — battery level percentage
- `sensor.tineco_vacuum_status` — `idle`, `in_operation`, `self_cleaning`, `docked_standby`, …
- `sensor.tineco_waste_water_tank_status` — `clean` / `full`
- `sensor.tineco_fresh_water_tank_status` — `empty` / `full`

### Switches
- `switch.tineco_sound_enabled`
- `switch.tineco_water_mode_enabled`
- `switch.tineco_floor_brush_light`

### Selects
- `select.tineco_sound_volume_level` — Low / Medium / High
- `select.tineco_suction_mode_power` — 120W / 150W
- `select.tineco_max_mode_power` — 120W / 150W
- `select.tineco_max_mode_spray_volume` — Rinse / Max
- `select.tineco_water_mode_power` — 90W / 120W / 150W *(unavailable when water mode is off)*
- `select.tineco_water_mode_spray_volume` — Mist / Wet / Medium / Rinse / Max *(unavailable when water mode is off)*

### Binary sensors
- `binary_sensor.tineco_online`
- `binary_sensor.tineco_charging`

### Entity grouping

Related controls share a prefix so they group naturally in the UI:

- **Sound**: `Tineco Sound: Enabled`, `Tineco Sound: Volume Level`
- **Suction Mode**: `Tineco Suction Mode: Power`
- **MAX Mode**: `Tineco MAX Mode: Power`, `Tineco MAX Mode: Spray Volume`
- **Water Mode**: `Tineco Water Mode: Enabled`, `Tineco Water Mode: Power`, `Tineco Water Mode: Spray Volume`


## Automation examples

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
      entity_id: sensor.tineco_fresh_water_tank_status
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
      entity_id: sensor.tineco_waste_water_tank_status
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


## API reference

Device queries used by the integration:

- **GCI** (Get Controller Info) — battery, vacuum status, tank state, error codes
- **GAV** (Get API Version) — firmware version
- **GCF** (Get Config File) — device configuration
- **CFP** (Get Config Point) — configuration points, status data
- **QueryMode / UpdateMode / DeleteMode** — read & change suction / MAX / water modes

### Key fields

- `bp` — battery percentage (0–100). Sentinel values 238/239/240 mean "no data / error".
- `e2` — tank-condition **bitmask** (primary signal on the S7 Flashdry, verified
  from captured transitions):
  - bit `64` (`e2 & 64`) — **fresh / clean water tank empty**
  - bit `256` (`e2 & 256`) — **waste / dirty water tank full**
  - the two bits are independent and can be set together
- `wp` — clean (fresh) water tank level indicator. On the S7 Flashdry it
  reports `238` when water is present and flips to `239` when empty (a
  corroborating signal alongside `e2 & 64`). `wp=238` is **not** an empty
  sentinel.
- `wm` — working mode (1=Standby, 2=Charging, 3=In Operation, 8=Self-clean, 9=OTA, 13=Drying)
- `e3` — alternate warning bitmask used by some firmware. Each set bit `n` maps
  to warning code `n + 32` (decoded from the Tineco app). Notably:
  - bit 12 (`e3 & 4096`, code 44) — waste / dirty water tank full
  - bit 13 (`e3 & 8192`, code 45) — fresh / clean water tank empty
- `e1` — legacy single-value waste-tank fallback (`e1 > 0`) on older firmware
- `vs` — online flag
- `vl` — volume level (1=Low, 2=Medium, 3=High)
- `ms` — mute status (0=unmuted, 1=muted)


## Troubleshooting

### Invalid authentication

- Re-check credentials (email **or** phone number for CN) and password
- CN users: phone number + region set to **CN**
- Try resetting the password in the official Tineco app first


## Support

If something isn't working, please open an issue with logs attached so the cause is visible.

**How to grab logs:**

1. In Home Assistant, edit `configuration.yaml` and add:

   ```yaml
   logger:
     default: info
     logs:
       custom_components.tineco: debug
   ```

   Restart Home Assistant so the `logger` block is active.

2. Open the Tineco integration: **Settings** → **Devices & Services** → **Tineco** → **Enable debug logging**.

3. Reproduce the problem (e.g. add the integration, toggle a switch, wait for the failing poll).

4. Back on the integration page, click **Disable debug logging**. Home Assistant will prompt you to save the log file — download it.

**Open the issue here:** https://github.com/wheeller123/Tineco-HACS-Integration/issues — attach the log file and include the integration version, region (`IE` / `US` / `CN` / …), device model, and a short description of what you did. Scrub anything that looks like a token, account ID, or phone number before posting.


## Credits

Created by Jack Whelan. Community contributions and bug reports welcome.


## Disclaimer

This integration is not affiliated with Tineco. It uses reverse-engineered APIs and may break when Tineco changes their servers. Developed primarily against the S7 Flashdry — other models may work with community help.


## License

MIT — see [`LICENSE`](LICENSE).
