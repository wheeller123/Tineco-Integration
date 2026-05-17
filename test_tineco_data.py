#!/usr/bin/env python3
"""Test script to examine Tineco API data without deploying to Home Assistant.

Two modes:

* No args (default) — interactive: prompts for credentials and runs the full
  diagnostic + sequenced mode-command test against the live device.

* ``--dump <path>``  — read-only: logs in, fetches device list + complete
  device info, scrubs PII, writes JSON suitable for use as a fixture under
  ``tests/fixtures/``. Skips the mode/light/volume mutation tests entirely.

Example::

    python test_tineco_data.py --dump tests/fixtures/s7_flashdry_user.json
"""

import argparse
import copy
import json
import os
import importlib.util
import sys

# Import TinecoClient by loading the module directly to avoid path conflicts
def load_tineco_client():
    """Load TinecoClient module without adding to sys.path."""
    tineco_path = os.path.join(os.path.dirname(__file__), 'custom_components', 'tineco', 'tineco_client_impl.py')
    spec = importlib.util.spec_from_file_location("tineco_client_impl", tineco_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TinecoClient

TinecoClient = load_tineco_client()


# Keys whose values may identify a real account/device. Replace with placeholders
# before writing fixtures. Matched case-insensitively at any depth.
PII_KEYS = {
    "did", "didios",
    "mid", "tuyaid",
    "account", "email", "mobile", "phone", "phonenumber",
    "token", "accesstoken", "authcode", "iottoken", "refreshtoken",
    "uid", "ucuid", "userid",
    "iconurl", "avatar",
}


def _scrub_pii(obj, placeholder="<scrubbed>"):
    """Walk dicts/lists and replace any PII_KEYS values with a placeholder.

    Returns a deep-copied structure; the input is left intact.
    """
    obj = copy.deepcopy(obj)

    def _walk(node):
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if isinstance(key, str) and key.lower() in PII_KEYS:
                    node[key] = placeholder
                elif isinstance(value, (dict, list)):
                    _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(obj)
    return obj


def dump_fixture(output_path: str) -> int:
    """Login, fetch device list + complete device info, scrub PII, write JSON.

    Read-only — never sends control commands. Intended for generating
    ``tests/fixtures/<device>.json`` payloads.
    """
    email = input("Enter Tineco email: ").strip()
    password = input("Enter Tineco password: ").strip()
    region = input("Region code (default IE): ").strip() or "IE"

    client = TinecoClient(region=region)
    print("\n[1/3] Logging in...")
    success, _token, _uid = client.login(email, password)
    if not success:
        print("Login failed.")
        return 1

    print("[2/3] Getting device list...")
    client.get_devices()
    if not client.device_list:
        print("No devices found.")
        return 1

    first_device = client.device_list[0]
    device_id = first_device.get("did") or first_device.get("deviceId")
    device_class = first_device.get("className", "")
    device_resource = first_device.get("resource", "")

    print(f"[3/3] Fetching complete device info for {device_id}...")
    info = client.get_complete_device_info(device_id, device_class, device_resource)
    if not info:
        print("Failed to get device info.")
        return 1

    fixture = {
        "_source": f"Captured via test_tineco_data.py --dump (region={region}). "
                   "PII fields scrubbed; review before committing.",
        "devices": _scrub_pii(client.device_list),
        "info": _scrub_pii(info),
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(fixture, fh, indent=2, sort_keys=True, default=str)

    print(f"\nWrote fixture to {output_path}")
    print(f"Devices: {len(fixture['devices'])}, info endpoints: {len(fixture['info'])}")
    print("REVIEW the file and scrub anything PII_KEYS missed (e.g. project names, locations)")
    print("before committing it to the repo.")
    return 0


def test_tineco_data():
    """Test Tineco API and display all relevant data."""
    
    # Get credentials
    email = input("Enter Tineco email: ").strip()
    password = input("Enter Tineco password: ").strip()
    
    print("\n" + "="*80)
    print("TINECO API DATA TEST")
    print("="*80)
    
    # Create client
    client = TinecoClient()
    
    # Login
    print("\n[1/4] Logging in...")
    success, token, uid = client.login(email, password)
    if not success:
        print("❌ Login failed!")
        return
    print("✅ Login successful")
    
    # Get device list
    print("\n[2/4] Getting device list...")
    client.get_devices()
    if not client.device_list:
        print("❌ No devices found!")
        return
    
    print(f"✅ Found {len(client.device_list)} device(s)")
    
    # Display device list info
    print("\n" + "-"*80)
    print("DEVICE LIST DATA (for model/firmware)")
    print("-"*80)
    for i, device in enumerate(client.device_list):
        print(f"\nDevice {i+1}:")
        print(json.dumps(device, indent=2, default=str))
    
    # Get first device
    first_device = client.device_list[0]
    device_id = first_device.get("did") or first_device.get("deviceId")
    device_class = first_device.get("className", "")
    device_resource = first_device.get("resource", "")
    
    print(f"\n[3/4] Getting complete device info for device: {device_id}")
    
    # Get complete device info
    info = client.get_complete_device_info(device_id, device_class, device_resource)
    
    if not info:
        print("❌ Failed to get device info!")
        return
    
    print("✅ Got device info")
    
    # Display all endpoint data
    print("\n" + "-"*80)
    print("COMPLETE DEVICE INFO (all endpoints)")
    print("-"*80)
    print(json.dumps(info, indent=2, default=str))
    
    # Analyze specific fields for our sensors
    print("\n" + "="*80)
    print("SENSOR FIELD ANALYSIS")
    print("="*80)
    
    # Model analysis
    print("\n📱 MODEL SENSOR:")
    print("  Available fields in device list:")
    for key in ['deviceName', 'name', 'nick', 'model', 'deviceModel']:
        value = first_device.get(key)
        if value:
            starts_with_zero = str(value).startswith('0000')
            print(f"    {key}: '{value}' {'⚠️ STARTS WITH 0000' if starts_with_zero else '✓'}")
    
    # Firmware analysis
    print("\n💾 FIRMWARE SENSOR:")
    print("  Device list fields:")
    for key in ['firmwareVersion', 'fwVersion', 'version']:
        value = first_device.get(key)
        if value:
            # Check if printable
            printable = all(c.isprintable() and ord(c) < 128 for c in str(value))
            print(f"    {key}: '{value}' {'✓ PRINTABLE' if printable else '⚠️ HAS SPECIAL CHARS'}")
    
    print("\n  Endpoint fields:")
    for endpoint_key in ['gci', 'gav', 'gcf', 'cfp', 'query_mode']:
        if endpoint_key in info and info[endpoint_key]:
            endpoint_data = info[endpoint_key]
            if isinstance(endpoint_data, dict):
                for payload_key in ['payload', 'data']:
                    payload = endpoint_data.get(payload_key)
                    if isinstance(payload, dict):
                        for fw_key in ['firmware_version', 'fwVersion', 'firmwareVersion', 'fw', 'version', 'vv']:
                            if fw_key in payload:
                                print(f"    {endpoint_key}.{payload_key}.{fw_key}: '{payload[fw_key]}'")
    
    # Vacuum status analysis
    print("\n🧹 VACUUM STATUS SENSOR:")
    print("  Looking for wm, selfclean_process, station, sta, cleanway, selectmode fields...")
    
    def find_fields(obj, path=""):
        """Recursively find relevant fields."""
        results = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                if key.lower() in ['wm', 'selfclean_process', 'selfclean_progress', 'station', 'sta', 'cleanway', 'selectmode', 'wheel', 'msr']:
                    results.append((current_path, value))
                if isinstance(value, (dict, list)):
                    results.extend(find_fields(value, current_path))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                results.extend(find_fields(item, f"{path}[{i}]"))
        return results
    
    fields_found = find_fields(info)
    if fields_found:
        for path, value in fields_found:
            # Interpret wm value
            if 'wm' in path.lower():
                status_map = {0: "Idle", 1: "Idle", 2: "Charging", 3: "In Operation", 4: "In Operation", 8: "Docked/Standby", 10: "Unknown Mode 10"}
                status = status_map.get(value, f"Unknown Mode {value}")
                print(f"    {path}: {value} → {status}")
            else:
                print(f"    {path}: {value}")
    else:
        print("    ⚠️ No status fields found!")
    
    # Water tank analysis
    print("\n💧 WATER TANK SENSORS:")
    print("  Looking for wdt, mdt, wp, dv, vs, error codes...")
    
    def find_water_fields(obj, path=""):
        """Recursively find water tank fields."""
        results = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                if key.lower() in ['wdt', 'mdt', 'wp', 'dv', 'vs', 'vl', 'e1', 'e2', 'e3', 'water_level', 'water_status']:
                    results.append((current_path, key.lower(), value))
                if isinstance(value, (dict, list)):
                    results.extend(find_water_fields(value, current_path))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                results.extend(find_water_fields(item, f"{path}[{i}]"))
        return results
    
    water_fields = find_water_fields(info)
    if water_fields:
        for path, field, value in water_fields:
            if field == 'wdt':
                status = "Needs Refill" if value == 0 else "OK"
                print(f"    {path}: {value} → Clean Water Tank: {status}")
            elif field == 'mdt':
                status = "Needs Emptying" if value == 1 else "OK"
                print(f"    {path}: {value} → Dirty Water Tank: {status}")
            elif field == 'wp':
                print(f"    {path}: {value} → Water Pressure/Percentage")
            elif field == 'dv':
                print(f"    {path}: {value} → DV (device value?)")
            elif field == 'vs':
                print(f"    {path}: {value} → VS (vacuum/water status?)")
            elif field == 'vl':
                print(f"    {path}: {value} → VL (voice/volume level?)")
            elif field in ['e1', 'e2', 'e3']:
                error_meanings = {
                    'e1': 'Error 1',
                    'e2': 'Error 2 (Dirty Tank=64)',
                    'e3': 'Error 3'
                }
                if value != 0:
                    print(f"    {path}: {value} → {error_meanings[field]} ACTIVE")
                else:
                    print(f"    {path}: {value} → {error_meanings[field]} (None)")
    else:
        print("    ⚠️ No water tank fields found!")
    
    # Light control analysis
    print("\n💡 FLOOR BRUSH LIGHT SENSOR:")
    print("  Looking for led, light, lamp, brush light fields...")

    def find_light_fields(obj, path=""):
        """Recursively find light-related fields."""
        results = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                if key.lower() in ['led', 'light', 'lamp', 'fbl', 'fl', 'bl', 'brush_light']:
                    results.append((current_path, key.lower(), value))
                if isinstance(value, (dict, list)):
                    results.extend(find_light_fields(value, current_path))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                results.extend(find_light_fields(item, f"{path}[{i}]"))
        return results

    light_fields = find_light_fields(info)
    if light_fields:
        for path, field, value in light_fields:
            status = "ON" if value == 1 else "OFF" if value == 0 else f"Unknown ({value})"
            print(f"    {path}: {value} → {status}")
    else:
        print("    ⚠️ No light fields found!")

    # Floor Brush Light control test
    print("\n" + "="*80)
    print("FLOOR BRUSH LIGHT CONTROL TEST")
    print("="*80)

    print("\n[4/5] Testing floor brush light control command...")

    # Check current light state
    print("\n💡 Current floor brush light state:")
    for endpoint_key in ['gci', 'cfp']:
        if endpoint_key in info and isinstance(info[endpoint_key], dict):
            if 'led' in info[endpoint_key]:
                led_value = info[endpoint_key]['led']
                state = "ON" if led_value == 1 else "OFF"
                print(f"    {endpoint_key}.led: {led_value} → {state}")

    # Test floor brush light control - try turning it ON
    print("\n🔧 Testing floor brush light with {'led': 1} (turn ON)...")
    command = {"led": 1}

    print(f"   Device ID: {device_id}")
    print(f"   Device Class: {device_class}")
    print(f"   Device Resource: {device_resource}")

    result = client.control_device(device_id, command, device_resource, device_class)

    if result:
        print("\n✅ Command sent successfully!")
        print(f"   Response: {json.dumps(result, indent=2)}")

        # Wait and check new state
        import time
        print("\n⏳ Waiting 3 seconds for device to update...")
        time.sleep(3)

        print("\n🔄 Fetching updated device info...")
        updated_info = client.get_complete_device_info(device_id, device_class, device_resource)

        if updated_info:
            print("\n💡 Updated floor brush light state:")
            for endpoint_key in ['gci', 'cfp']:
                if endpoint_key in updated_info and isinstance(updated_info[endpoint_key], dict):
                    if 'led' in updated_info[endpoint_key]:
                        led_value = updated_info[endpoint_key]['led']
                        state = "ON" if led_value == 1 else "OFF"
                        print(f"    {endpoint_key}.led: {led_value} → {state}")

            # Now try turning it OFF
            print("\n🔧 Testing floor brush light with {'led': 0} (turn OFF)...")
            command = {"led": 0}
            result = client.control_device(device_id, command, device_resource, device_class)

            if result:
                print("\n✅ OFF command sent successfully!")
                print(f"   Response: {json.dumps(result, indent=2)}")

                print("\n⏳ Waiting 3 seconds for device to update...")
                time.sleep(3)

                print("\n🔄 Fetching final device info...")
                final_info = client.get_complete_device_info(device_id, device_class, device_resource)

                if final_info:
                    print("\n💡 Final floor brush light state:")
                    for endpoint_key in ['gci', 'cfp']:
                        if endpoint_key in final_info and isinstance(final_info[endpoint_key], dict):
                            if 'led' in final_info[endpoint_key]:
                                led_value = final_info[endpoint_key]['led']
                                state = "ON" if led_value == 1 else "OFF"
                                print(f"    {endpoint_key}.led: {led_value} → {state}")
            else:
                print("\n❌ OFF command failed - no response received")
    else:
        print("\n❌ Command failed - no response received")
        print("\n🔍 Trying alternative command keys...")

        # Try alternative keys
        for alt_key in ['light', 'fbl', 'fl', 'lamp']:
            print(f"\n   Testing with {{'{alt_key}': 1}}...")
            alt_result = client.control_device(device_id, {alt_key: 1}, device_resource, device_class)
            if alt_result:
                print(f"   ✅ {alt_key} command worked!")
                print(f"   Response: {json.dumps(alt_result, indent=2)}")
                break
            else:
                print(f"   ❌ {alt_key} command failed")

    # Volume control test
    print("\n" + "="*80)
    print("VOLUME CONTROL TEST")
    print("="*80)

    print("\n[5/5] Testing volume control command...")
    
    # Check current volume state
    print("\n📢 Current volume/mute state:")
    for endpoint_key in ['gci', 'cfp']:
        if endpoint_key in info and isinstance(info[endpoint_key], dict):
            if 'vl' in info[endpoint_key]:
                vl_value = info[endpoint_key]['vl']
                state = "ON (Unmuted)" if vl_value == 1 else "OFF (Muted)"
                print(f"    {endpoint_key}.vl: {vl_value} → {state}")
    
    # Test volume control - automatically send ms=0
    print("\n🔧 Testing volume control with {'ms': 0}...")
    command = {"ms": 0}
    
    print(f"   Device ID: {device_id}")
    print(f"   Device Class: {device_class}")
    print(f"   Device Resource: {device_resource}")
    
    result = client.control_device(device_id, command, device_resource, device_class)
    
    if result:
        print("\n✅ Command sent successfully!")
        print(f"   Response: {json.dumps(result, indent=2)}")
        
        # Wait and check new state
        import time
        print("\n⏳ Waiting 2 seconds for device to update...")
        time.sleep(2)
        
        print("\n🔄 Fetching updated device info...")
        updated_info = client.get_complete_device_info(device_id, device_class, device_resource)
        
        if updated_info:
            print("\n📢 Updated volume/mute state:")
            for endpoint_key in ['gci', 'cfp']:
                if endpoint_key in updated_info and isinstance(updated_info[endpoint_key], dict):
                    if 'vl' in updated_info[endpoint_key]:
                        vl_value = updated_info[endpoint_key]['vl']
                        state = "ON (Unmuted)" if vl_value == 1 else "OFF (Muted)"
                        print(f"    {endpoint_key}.vl: {vl_value} → {state}")
    else:
        print("\n❌ Command failed - no response received")

    # Mode commands test
    print("\n" + "="*80)
    print("MODE COMMANDS TEST (4 SEQUENTIAL COMMANDS)")
    print("="*80)

    print("\n[6/6] Testing coordinated mode commands...")
    print("\nThis test simulates the Home Assistant integration's coordinated mode system.")
    print("It will send 4 commands in sequence to configure all modes.\n")

    # Define test mode settings
    mode_state = {
        "suction_power": 2,              # 150W
        "max_power": 2,                  # 150W
        "max_spray_volume": 3,           # Rinse
        "water_only_mode": False,        # OFF
        "water_mode_power": 1,           # 120W
        "water_mode_spray_volume": 3,    # Rinse
    }

    print("📋 Test configuration:")
    print(f"   Suction Power: {mode_state['suction_power']} (150W)")
    print(f"   MAX Power: {mode_state['max_power']} (150W)")
    print(f"   MAX Spray Volume: {mode_state['max_spray_volume']} (Rinse)")
    print(f"   Water Only Mode: {'ON' if mode_state['water_only_mode'] else 'OFF'}")
    print(f"   Water Mode Power: {mode_state['water_mode_power']} (120W)")
    print(f"   Water Mode Spray Volume: {mode_state['water_mode_spray_volume']} (Rinse)")

    # Build the 4 mode commands (same logic as select.py)
    commands = []

    # Command 1: Suction mode (md=4)
    cmd1 = {"md": 4, "vm": mode_state["suction_power"]}
    commands.append(cmd1)

    # Command 2: MAX mode (md=3)
    cmd2 = {"md": 3, "vm": mode_state["max_power"], "wm": mode_state["max_spray_volume"]}
    commands.append(cmd2)

    # Command 3: Water mode (md=6)
    if mode_state["water_only_mode"]:
        cmd3 = {
            "md": 6,
            "vm": mode_state["water_mode_power"],
            "wm": mode_state["water_mode_spray_volume"]
        }
    else:
        cmd3 = {"md": 6}
    commands.append(cmd3)

    # Command 4: Empty command
    cmd4 = {}
    commands.append(cmd4)

    print(f"\n📤 Sending {len(commands)} commands in sequence...")
    import time

    all_successful = True
    for i, command in enumerate(commands, 1):
        print(f"\n🔧 Command {i}/{len(commands)}: {command}")
        result = client.control_device(device_id, command, device_resource, device_class)

        if result:
            # Check if response is {"ret": "ok"}
            if isinstance(result, dict) and result.get("ret") == "ok":
                print(f"   ✅ SUCCESS - Response: {json.dumps(result, indent=6)}")
            else:
                print(f"   ⚠️  Unexpected response: {json.dumps(result, indent=6)}")
                all_successful = False
        else:
            print(f"   ❌ FAILED - No response received")
            all_successful = False

        # Small delay between commands
        if i < len(commands):
            time.sleep(0.5)

    if all_successful:
        print("\n✅ All 4 mode commands sent successfully!")

        print("\n⏳ Waiting 3 seconds for device to update...")
        time.sleep(3)

        print("\n🔄 Fetching updated device info...")
        updated_info = client.get_complete_device_info(device_id, device_class, device_resource)

        if updated_info:
            print("\n📊 Device state after mode commands:")
            for endpoint_key in ['gci', 'cfp']:
                if endpoint_key in updated_info and isinstance(updated_info[endpoint_key], dict):
                    payload = updated_info[endpoint_key]
                    print(f"\n   {endpoint_key}:")

                    # Check for mode-related fields
                    mode_fields = ['md', 'vm', 'wm', 'wp', 'wom', 'sp', 'mp']
                    for field in mode_fields:
                        if field in payload:
                            print(f"      {field}: {payload[field]}")
    else:
        print("\n❌ Some mode commands failed!")

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dump",
        metavar="PATH",
        help="Read-only mode: write a fixture JSON to PATH instead of running "
             "the interactive control tests.",
    )
    args = parser.parse_args()

    try:
        if args.dump:
            sys.exit(dump_fixture(args.dump))
        else:
            test_tineco_data()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
