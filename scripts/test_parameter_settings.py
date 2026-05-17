#!/usr/bin/env python3
"""Test script for Tineco mode parameter settings (4 POST commands)."""

import json
import os
import importlib.util
import time

# Import TinecoClient by loading the module directly to avoid path conflicts
def load_tineco_client():
    """Load TinecoClient module without adding to sys.path."""
    # Script lives in scripts/; custom_components/ is one level up at repo root.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tineco_path = os.path.join(repo_root, 'custom_components', 'tineco', 'tineco_client_impl.py')
    spec = importlib.util.spec_from_file_location("tineco_client_impl", tineco_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TinecoClient

TinecoClient = load_tineco_client()


def test_mode_commands():
    """Test the 4 sequential mode commands."""

    print("="*80)
    print("TINECO MODE PARAMETER SETTINGS TEST")
    print("="*80)
    print()

    # Get credentials
    email = input("Enter Tineco email: ").strip()
    password = input("Enter Tineco password: ").strip()

    # Initialize client
    print("\n[1/4] Logging in...")
    client = TinecoClient()

    if not client.login(email, password):
        print("❌ Login failed!")
        return

    print("✅ Login successful")

    # Get devices
    print("\n[2/4] Getting devices...")
    result = client.get_devices()

    if not result or not client.device_list:
        print("❌ No devices found!")
        return

    device = client.device_list[0]
    device_id = device.get("did") or device.get("deviceId")
    device_class = device.get("className", "")
    device_resource = device.get("resource", "")

    print(f"✅ Found device: {device.get('name', 'Unknown')}")
    print(f"   Device ID: {device_id}")
    print(f"   Class: {device_class}")
    print(f"   Resource: {device_resource}")

    # Define test mode settings
    print("\n[3/4] Preparing mode commands...")
    print("\n📋 Test configuration:")

    mode_state = {
        "suction_power": 2,              # 150W
        "max_power": 2,                  # 150W
        "max_spray_volume": 3,           # Rinse
        "water_only_mode": True,        # ON
        "water_mode_power": 1,           # 120W
        "water_mode_spray_volume": 3,    # Rinse
    }

    print(f"   Suction Power: {mode_state['suction_power']} (150W)")
    print(f"   MAX Power: {mode_state['max_power']} (150W)")
    print(f"   MAX Spray Volume: {mode_state['max_spray_volume']} (Rinse)")
    print(f"   Water Only Mode: {'ON' if mode_state['water_only_mode'] else 'OFF'}")
    print(f"   Water Mode Power: {mode_state['water_mode_power']} (120W)")
    print(f"   Water Mode Spray Volume: {mode_state['water_mode_spray_volume']} (Rinse)")

    # Build the 4 mode commands with their corresponding actions
    # Command 1 & 2: UpdateMode, Command 3: DeleteMode, Command 4: QueryMode
    commands = []

    # Command 1: Suction mode (md=4) - UpdateMode
    cmd1 = ({"md": 4, "vm": mode_state["suction_power"]}, "UpdateMode")
    commands.append(cmd1)

    # Command 2: MAX mode (md=3) - UpdateMode
    cmd2 = ({"md": 3, "vm": mode_state["max_power"], "wm": mode_state["max_spray_volume"]}, "UpdateMode")
    commands.append(cmd2)

    # Command 3: Water mode (md=6) - DeleteMode (to disable water-only mode)
    if mode_state["water_only_mode"]:
        cmd3 = ({
            "md": 6,
            "vm": mode_state["water_mode_power"],
            "wm": mode_state["water_mode_spray_volume"]
        }, "UpdateMode")  # Use UpdateMode when enabling water mode
    else:
        cmd3 = ({"md": 6}, "DeleteMode")  # Use DeleteMode when disabling water mode
    commands.append(cmd3)

    # Command 4: Empty command - QueryMode
    cmd4 = ({}, "QueryMode")
    commands.append(cmd4)

    # Send all 4 commands
    print(f"\n[4/4] Sending {len(commands)} mode commands...")
    print("="*80)

    all_successful = True
    for i, (command, action) in enumerate(commands, 1):
        print(f"\n🔧 Command {i}/{len(commands)} (action={action})")
        print(f"   Payload: {json.dumps(command)}")

        result = client.control_device(device_id, command, device_resource, device_class, action=action)

        if result:
            # Success conditions:
            # 1. {"ret": "ok"} - standard success response
            # 2. {"cfg": [...]} - QueryMode returns mode configuration
            # 3. Device state fields (wheel, bp, wm, etc.)
            if isinstance(result, dict) and result.get("ret") == "ok":
                print(f"   ✅ SUCCESS")
                print(f"   Response: {json.dumps(result)}")
            elif isinstance(result, dict) and "cfg" in result:
                print(f"   ✅ SUCCESS")
                print(f"   Response: {json.dumps(result)}")
            elif isinstance(result, dict) and ("wheel" in result or "bp" in result or "wm" in result):
                print(f"   ✅ SUCCESS")
                print(f"   Response: {json.dumps(result)}")
            else:
                print(f"   ⚠️  UNEXPECTED RESPONSE")
                print(f"   Response: {json.dumps(result, indent=3)}")
                all_successful = False
        else:
            print(f"   ❌ FAILED - No response received")
            all_successful = False

        # Small delay between commands
        if i < len(commands):
            time.sleep(0.5)

    print("\n" + "="*80)

    if all_successful:
        print("✅ All 4 mode commands sent successfully!")

        print("\n⏳ Waiting 3 seconds for device to update...")
        time.sleep(3)

        print("\n🔄 Fetching device state...")
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
        print("❌ Some mode commands failed!")

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)


if __name__ == "__main__":
    try:
        test_mode_commands()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
