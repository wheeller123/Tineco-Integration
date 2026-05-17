#!/usr/bin/env python3
"""
Debug script to show all available fields from your Tineco device.
This helps identify the correct command keys for controls.
"""

import sys
import json
from pathlib import Path

# Script lives in scripts/; custom_components/ is one level up at repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components" / "tineco"))

from tineco_client_impl import TinecoClient


def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80)


def explore_dict(data, prefix="", max_depth=3, current_depth=0):
    """Recursively explore dictionary and print all keys."""
    if current_depth >= max_depth or not isinstance(data, dict):
        return

    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key

        if isinstance(value, dict):
            print(f"  {full_key}: <dict with {len(value)} keys>")
            explore_dict(value, full_key, max_depth, current_depth + 1)
        elif isinstance(value, list):
            print(f"  {full_key}: <list with {len(value)} items>")
            if value and isinstance(value[0], dict):
                explore_dict(value[0], f"{full_key}[0]", max_depth, current_depth + 1)
        else:
            # Show the value for simple types
            print(f"  {full_key}: {value}")


def main():
    """Main debug function."""
    print_section("Tineco Device Field Explorer")

    # Get credentials
    print("\nThis script will query your device and show all available fields.")
    print("This helps identify the correct command keys for controls.\n")

    email = input("Enter your Tineco account email: ").strip()
    password = input("Enter your password: ").strip()
    region = input("Enter your region (default: IE): ").strip() or "IE"

    # Initialize client
    print("\n[INFO] Connecting to Tineco API...")
    client = TinecoClient(region=region)

    # Login
    success, token, user_id = client.login(email, password, request_code=False)
    if not success:
        print("[ERROR] Login failed!")
        return 1

    print(f"[OK] Logged in successfully! User ID: {user_id}")

    # Get devices
    print("\n[INFO] Getting device list...")
    devices_response = client.get_devices()
    if not devices_response or not client.device_list:
        print("[ERROR] No devices found!")
        return 1

    # Select device
    if len(client.device_list) == 1:
        device = client.device_list[0]
        print(f"[OK] Using device: {device.get('nick') or device.get('deviceName')}")
    else:
        print("\nAvailable devices:")
        for i, dev in enumerate(client.device_list, 1):
            print(f"  {i}. {dev.get('nick') or dev.get('deviceName')}")
        idx = int(input("Select device number: ")) - 1
        device = client.device_list[idx]

    device_id = device.get('did') or device.get('deviceId')
    device_class = device.get('className', '')
    device_resource = device.get('resource', '')

    # Query all device endpoints
    print_section("Device Information")

    # GCI - Get Controller Info (current device state)
    print("\n[1/5] GCI (Get Controller Info) - Current device state:")
    gci = client.get_controller_info(device_id, device_class, device_resource)
    if gci:
        explore_dict(gci)
        print("\nFull GCI JSON:")
        print(json.dumps(gci, indent=2))

    # CFP - Config File Point (configuration)
    print("\n[2/5] CFP (Config File Point) - Configuration:")
    cfp = client.get_device_config_point(device_id, device_class, device_resource)
    if cfp:
        explore_dict(cfp)

    # GAV - Get API Version
    print("\n[3/5] GAV (Get API Version):")
    gav = client.get_api_version(device_id, device_class, device_resource)
    if gav:
        explore_dict(gav)

    # GCF - Get Config File
    print("\n[4/5] GCF (Get Config File):")
    gcf = client.get_config_file(device_id, device_class, device_resource)
    if gcf:
        explore_dict(gcf)

    # QueryMode - Device modes
    print("\n[5/5] QueryMode - Device operating modes:")
    query_mode = client.query_device_mode(device_id, device_class, device_resource)
    if query_mode:
        explore_dict(query_mode)

    print_section("Field Analysis Complete")
    print("\nLook for fields like:")
    print("  - Light/lamp related: 'light', 'lamp', 'led', 'fl', 'bl'")
    print("  - Floor brush: 'brush', 'roller', 'floor'")
    print("  - Water mode: 'water', 'detergent', 'solution'")
    print("  - Power/speed: 'power', 'speed', 'suction'")
    print("\nUse these field names as command keys in your integration!")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[!] Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
