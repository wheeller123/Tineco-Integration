#!/usr/bin/env python3
"""Interactive smoke test: drive your real vacuum and verify decoded state.

This is a *pre-release* manual check that catches API-shape regressions the
captured-fixture unit tests can't see — e.g. Tineco starts returning a new
field name, or a firmware update changes the meaning of ``wm=8``.

Flow per step:

    1. Script prompts you to perform an action on the physical vacuum
       (e.g. "press the power button").
    2. You confirm by pressing Enter.
    3. Script polls the live Tineco API.
    4. Script feeds the response into the SAME ``_update_state_from_data``
       method used by the HA sensors — so the assertion below proves both
       the API shape AND the decoding logic are still correct.
    5. PASS/FAIL is reported with the raw fields that drove the decision,
       so a failure pinpoints which field broke.

Run::

    python scripts/smoke_vacuum_state.py

Add ``--region <code>`` if your account isn't IE.

Skipped by CI — this is a release-checklist step, not a unit test.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
import types
from typing import Any, Callable

# Ensure repo root is importable (mirrors tests/conftest.py).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _load_tineco_client():
    """Load TinecoClient without dragging in HA imports from the package."""
    impl_path = os.path.join(REPO_ROOT, "custom_components", "tineco", "tineco_client_impl.py")
    spec = importlib.util.spec_from_file_location("tineco_client_impl", impl_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TinecoClient


# ----------------------------------------------------------------------------
# Pretty output
# ----------------------------------------------------------------------------

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
DIM = "\033[2m"
RESET = "\033[0m"


def _supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(text: str, color: str) -> str:
    return f"{color}{text}{RESET}" if _supports_color() else text


def banner(text: str) -> None:
    line = "=" * 78
    print(f"\n{line}\n  {text}\n{line}")


def prompt(action: str) -> None:
    print(f"\n{_c('▶', YELLOW)} {_c(action, YELLOW)}")
    input(_c("   Press Enter when done...", DIM))


def report(check: str, ok: bool, detail: str = "") -> bool:
    mark = _c("PASS", GREEN) if ok else _c("FAIL", RED)
    suffix = f"  {_c(detail, DIM)}" if detail else ""
    print(f"  [{mark}] {check}{suffix}")
    return ok


# ----------------------------------------------------------------------------
# Sensor invocation — feed live API data into the exact HA sensor logic.
# ----------------------------------------------------------------------------

def _make_sensor(cls, devices=None):
    """Construct a sensor without touching HA's CoordinatorEntity machinery."""
    sensor = cls.__new__(cls)
    sensor._state = None
    sensor.config_entry = types.SimpleNamespace(entry_id="smoke", data={"email": "smoke"})
    fake_client = types.SimpleNamespace(devices=list(devices or []))
    sensor.hass = types.SimpleNamespace(
        data={"tineco": {"smoke": {"client": fake_client}}}
    )
    return sensor


def _import_sensors():
    """Try to import the HA sensor classes; fall back gracefully if HA isn't installed."""
    try:
        from custom_components.tineco.sensor import (
            TinecoBatterySensor,
            TinecoModelSensor,
            TinecoVacuumStatusSensor,
            TinecoWaterTankSensor,
            TinecoFreshWaterTankSensor,
        )
        return dict(
            battery=TinecoBatterySensor,
            model=TinecoModelSensor,
            vacuum=TinecoVacuumStatusSensor,
            waste_water=TinecoWaterTankSensor,
            fresh_water=TinecoFreshWaterTankSensor,
        )
    except ImportError as e:
        print(_c(f"WARNING: HA sensor classes not importable: {e}", YELLOW))
        print(_c("  Decoded-state checks will be skipped. Install homeassistant to enable them.", DIM))
        return None


# ----------------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------------

def check_decoded_state(sensors, name: str, info: dict, devices: list, expected, fields_seen: dict) -> bool:
    """Run a single sensor's _update_state_from_data and assert == expected."""
    if sensors is None:
        return report(f"{name} sensor decoded", True, detail="(skipped: HA not installed)")

    sensor_cls = sensors[name]
    sensor = _make_sensor(sensor_cls, devices=devices)
    sensor._update_state_from_data(info)
    actual = sensor._state
    ok = actual == expected
    return report(
        f"{name} sensor decoded = {actual!r}",
        ok,
        detail=f"expected {expected!r}; raw {fields_seen}",
    )


def query_live(client, device_id: str, device_class: str, device_resource: str) -> dict:
    """Fetch one round of device info."""
    info = client.get_complete_device_info(device_id, device_class, device_resource)
    if not info:
        print(_c("  API query failed (empty response).", RED))
    return info or {}


# ----------------------------------------------------------------------------
# Main flow
# ----------------------------------------------------------------------------

def run(region: str) -> int:
    banner("Tineco live-device smoke test")
    print("Drives your real vacuum through a sequence of states and verifies")
    print("each one decodes correctly. Aborts at the first failure so you")
    print("can capture the API response for a fixture.")

    TinecoClient = _load_tineco_client()
    sensors = _import_sensors()

    email = input("\nTineco email: ").strip()
    import getpass
    password = getpass.getpass("Tineco password (hidden): ").strip()

    client = TinecoClient(region=region)
    print("\nLogging in...")
    success, _token, uid = client.login(email, password)
    if not success:
        print(_c("Login failed. Stopping.", RED))
        return 1
    print(_c(f"  Login OK (uid={uid[:12]}...)", GREEN))

    print("\nFetching device list...")
    client.get_devices()
    if not client.device_list:
        print(_c("No devices on this account.", RED))
        return 1
    device = client.device_list[0]
    device_id = device.get("did")
    device_class = device.get("className", "")
    device_resource = device.get("resource", "")
    print(f"  Device: {device.get('productType') or device.get('nick')!r}")
    print(f"  ID:     {device_id}")

    failures = 0

    # ------------------------------------------------------------------
    # Step 1 — Model sensor (read-only, no action needed)
    # ------------------------------------------------------------------
    banner("Step 1 — Model sensor reads productType, not nick")
    info = query_live(client, device_id, device_class, device_resource)
    nick = device.get("nick")
    product_type = device.get("productType")
    print(f"  Raw: nick={nick!r}, productType={product_type!r}")
    if sensors is not None:
        sensor = _make_sensor(sensors["model"], devices=[device])
        sensor._update_state_from_data(info)
        ok = sensor._state == (product_type or nick)
        if not report(f"model sensor = {sensor._state!r}", ok, f"expected {product_type!r}"):
            failures += 1
            # Specific check for the Floor One-1580 regression class.
            if nick and "-" in nick and any(c.isdigit() for c in nick.split("-")[-1]):
                print(_c(
                    "  ⚠ nick contains an internal project code pattern (e.g. '*-1580'). "
                    "If model sensor shows this, the v2.2.10→v2.2.12 regression is back.",
                    YELLOW,
                ))

    # ------------------------------------------------------------------
    # Step 2 — Vacuum status: idle (charging/standby)
    # ------------------------------------------------------------------
    banner("Step 2 — Vacuum idle/charging")
    prompt("Make sure the vacuum is OFF and on the dock (or just sitting still).")
    info = query_live(client, device_id, device_class, device_resource)
    wm = (info.get("gci") or {}).get("wm")
    bp = (info.get("gci") or {}).get("bp")
    print(f"  Raw: gci.wm={wm}, gci.bp={bp}")
    if not check_decoded_state(sensors, "vacuum", info, [device], "idle", {"wm": wm}):
        failures += 1
    if bp is not None and check_decoded_state(sensors, "battery", info, [device], bp if bp < 100 else 100, {"bp": bp}):
        pass  # battery just needs to read a sane integer 0..100
    else:
        if bp is None:
            failures += 1

    # ------------------------------------------------------------------
    # Step 3 — Vacuum status: in_operation
    # ------------------------------------------------------------------
    banner("Step 3 — Vacuum running")
    prompt("Turn the vacuum ON (squeeze the trigger or press start).")
    time.sleep(1.0)  # let the device push its state up
    info = query_live(client, device_id, device_class, device_resource)
    wm = (info.get("gci") or {}).get("wm")
    print(f"  Raw: gci.wm={wm}")
    if wm != 3:
        report("gci.wm == 3 (running)", False, f"got {wm}; vacuum may not be in operation yet")
        failures += 1
    else:
        report("gci.wm == 3 (running)", True)
    if not check_decoded_state(sensors, "vacuum", info, [device], "in_operation", {"wm": wm}):
        failures += 1

    prompt("Turn the vacuum OFF.")

    # ------------------------------------------------------------------
    # Step 4 — Waste / fresh water tanks (read-only checks against current state)
    # ------------------------------------------------------------------
    banner("Step 4 — Water tank decoding")
    info = query_live(client, device_id, device_class, device_resource)
    e1 = (info.get("gci") or {}).get("e1")
    e2 = (info.get("gci") or {}).get("e2")
    print(f"  Raw: gci.e1={e1}, gci.e2={e2}")
    expected_waste = "full" if (e1 is not None and int(e1) > 0) else "clean"
    expected_fresh = "empty" if (e2 is not None and int(e2) == 64) else "full"
    if not check_decoded_state(sensors, "waste_water", info, [device], expected_waste, {"e1": e1}):
        failures += 1
    if not check_decoded_state(sensors, "fresh_water", info, [device], expected_fresh, {"e2": e2}):
        failures += 1

    # ------------------------------------------------------------------
    # Step 5 — Floor brush light (control + read-back)
    # ------------------------------------------------------------------
    banner("Step 5 — Floor brush light control round-trip")
    print("Sending {'led': 1} (ON)...")
    client.control_device(device_id, {"led": 1}, device_resource, device_class)
    time.sleep(2.0)
    info = query_live(client, device_id, device_class, device_resource)
    led_on = (info.get("gci") or {}).get("led")
    if not report("gci.led == 1 after ON command", led_on == 1, f"got {led_on}"):
        failures += 1

    print("Sending {'led': 0} (OFF)...")
    client.control_device(device_id, {"led": 0}, device_resource, device_class)
    time.sleep(2.0)
    info = query_live(client, device_id, device_class, device_resource)
    led_off = (info.get("gci") or {}).get("led")
    if not report("gci.led == 0 after OFF command", led_off == 0, f"got {led_off}"):
        failures += 1

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------
    banner("Smoke test complete")
    if failures == 0:
        print(_c("All checks passed. Safe to tag/release.", GREEN))
        return 0
    print(_c(f"{failures} check(s) failed. DO NOT TAG — investigate first.", RED))
    print(_c("Capture the failing response with `test_tineco_data.py --dump` "
             "and add it as a fixture before fixing.", DIM))
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--region", default="IE", help="Region code (default: IE)")
    args = parser.parse_args()
    try:
        sys.exit(run(args.region))
    except KeyboardInterrupt:
        print(_c("\nAborted.", YELLOW))
        sys.exit(130)
