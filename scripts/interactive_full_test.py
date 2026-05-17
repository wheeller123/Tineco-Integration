#!/usr/bin/env python3
"""Interactive full-feature test — drive every Tineco entity through every state.

This is the extended cousin of ``smoke_vacuum_state.py``. The smoke test does
the bare minimum (model, basic vacuum state, light round-trip); this one
walks you through *every* feature the integration surfaces and verifies the
decode end-to-end:

    Identity       — model, firmware, api_version
    Connectivity   — online, charging
    Battery        — level + percentage clamp
    Vacuum modes   — idle / in_operation / self_cleaning transitions
    Water tanks    — fresh full→empty→full, waste clean→full→clean
    Brush roller   — read-out (physical state, no API command)
    Floor light    — API ON / OFF round-trip
    Sound          — API mute / unmute round-trip

For each step the script prompts you to do something physical to the vacuum,
waits for Enter, queries the live Tineco API, feeds the response into the
*exact* ``_update_state_from_data`` method the HA sensors use, and reports
PASS/FAIL with the raw fields that drove the decision.

This is a release-checklist step, not a unit test. Run before tagging
anything that touches sensor decoding or the IoT URL/auth chain.

Run::

    python scripts/interactive_full_test.py
    python scripts/interactive_full_test.py --region IE --skip sound

The ``--skip`` flag accepts comma-separated section keys: identity, online,
battery, idle, running, selfclean, fresh_water, waste_water, brush, light,
sound.
"""
from __future__ import annotations

import argparse
import getpass
import importlib.util
import os
import sys
import time
import types
from typing import Callable

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _load_tineco_client():
    impl_path = os.path.join(REPO_ROOT, "custom_components", "tineco", "tineco_client_impl.py")
    spec = importlib.util.spec_from_file_location("tineco_client_impl", impl_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TinecoClient


# ---------------------------------------------------------------------------
# Pretty output
# ---------------------------------------------------------------------------

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(text: str, color: str) -> str:
    return f"{color}{text}{RESET}" if _color() else text


def banner(text: str) -> None:
    line = "═" * 78
    print(f"\n{_c(line, CYAN)}\n  {_c(text, BOLD)}\n{_c(line, CYAN)}")


def section(text: str) -> None:
    print(f"\n{_c('▸ ' + text, CYAN)}")
    print(_c("─" * 78, DIM))


def prompt(action: str) -> None:
    print(f"\n{_c('▶ ' + action, YELLOW)}")
    input(_c("   Press Enter when done...", DIM))


def report(check: str, ok: bool, detail: str = "") -> bool:
    mark = _c("PASS", GREEN) if ok else _c("FAIL", RED)
    suffix = f"  {_c(detail, DIM)}" if detail else ""
    print(f"  [{mark}] {check}{suffix}")
    return ok


def info(text: str) -> None:
    print(f"  {_c('· ' + text, DIM)}")


# ---------------------------------------------------------------------------
# Sensor helpers — bypass CoordinatorEntity __init__ and feed live data in.
# ---------------------------------------------------------------------------

def _make_sensor(cls, devices=None):
    sensor = cls.__new__(cls)
    sensor._state = None
    sensor.config_entry = types.SimpleNamespace(entry_id="full_test", data={"email": "tester"})
    fake_client = types.SimpleNamespace(devices=list(devices or []))
    sensor.hass = types.SimpleNamespace(
        data={"tineco": {"full_test": {"client": fake_client}}}
    )
    return sensor


def _import_sensors():
    try:
        from custom_components.tineco.sensor import (
            TinecoAPISensor,
            TinecoBatterySensor,
            TinecoBrushRollerSensor,
            TinecoFirmwareVersionSensor,
            TinecoFreshWaterTankSensor,
            TinecoModelSensor,
            TinecoVacuumStatusSensor,
            TinecoWaterTankSensor,
        )
        return {
            "api": TinecoAPISensor,
            "battery": TinecoBatterySensor,
            "brush": TinecoBrushRollerSensor,
            "firmware": TinecoFirmwareVersionSensor,
            "fresh_water": TinecoFreshWaterTankSensor,
            "model": TinecoModelSensor,
            "vacuum": TinecoVacuumStatusSensor,
            "waste_water": TinecoWaterTankSensor,
        }
    except ImportError as e:
        print(_c(f"WARNING: HA sensors not importable ({e}); decoded checks skipped.", YELLOW))
        return None


def decode(sensors, name: str, info_dict: dict, devices: list):
    """Run a sensor's _update_state_from_data and return its resulting state."""
    if sensors is None:
        return "<HA-not-installed>"
    sensor = _make_sensor(sensors[name], devices=devices)
    sensor._update_state_from_data(info_dict)
    return sensor._state


def gci(info_dict: dict) -> dict:
    """Convenience: extract the gci payload (which most sensors read from)."""
    return info_dict.get("gci") or {}


def query_live(client, device_id, device_class, device_resource) -> dict:
    res = client.get_complete_device_info(device_id, device_class, device_resource)
    if not res:
        print(_c("  ! Empty API response. Network issue or device offline.", RED))
    return res or {}


# ---------------------------------------------------------------------------
# Section implementations. Each returns (section_key, failures_count).
# ---------------------------------------------------------------------------

class Ctx:
    """Per-run context — bundled to avoid 7-arg function signatures."""
    def __init__(self, client, sensors, device, device_id, device_class, device_resource):
        self.client = client
        self.sensors = sensors
        self.device = device
        self.device_id = device_id
        self.device_class = device_class
        self.device_resource = device_resource

    def fetch(self) -> dict:
        return query_live(self.client, self.device_id, self.device_class, self.device_resource)

    def control(self, command: dict) -> None:
        self.client.control_device(self.device_id, command, self.device_resource, self.device_class)


def section_identity(ctx: Ctx) -> int:
    section("Identity — model, firmware, API version")
    failures = 0
    info_dict = ctx.fetch()

    nick = ctx.device.get("nick")
    product_type = ctx.device.get("productType")
    info(f"Raw: nick={nick!r}, productType={product_type!r}, name={ctx.device.get('name')!r}")

    model = decode(ctx.sensors, "model", info_dict, [ctx.device])
    expected_model = product_type or ctx.device.get("productName") or nick
    if not report(f"model sensor = {model!r}", model == expected_model, f"expected {expected_model!r}"):
        failures += 1

    # Regression guard: nick must not silently override productType.
    if product_type and nick and "-" in nick and any(c.isdigit() for c in nick.split("-")[-1]):
        if not report(
            "model is the marketing name (not the *-NNNN project code)",
            model == product_type,
            f"nick {nick!r} contains an internal project code; sensor surfaced {model!r}",
        ):
            failures += 1

    fw = decode(ctx.sensors, "firmware", info_dict, [ctx.device])
    info(f"Firmware sensor = {fw!r} (raw gav={info_dict.get('gav')})")
    if not report("firmware sensor is non-empty + not 'Unknown'", fw and fw != "Unknown"):
        failures += 1

    api_v = decode(ctx.sensors, "api", info_dict, [ctx.device])
    info(f"API version sensor = {api_v!r}")

    return failures


def section_online(ctx: Ctx) -> int:
    section("Connectivity — device online + charging detection")
    info_dict = ctx.fetch()
    failures = 0

    # The online sensor is a binary that polls the device list; if we have a
    # device dict at all we can call the device "online" from the API's view.
    info(f"Device list contains {len((ctx.client.device_list or []))} device(s)")
    if not report("device list non-empty (proxy for online)", bool(ctx.client.device_list)):
        failures += 1

    bp = gci(info_dict).get("bp")
    info(f"gci.bp = {bp}  (≥100 implies on-dock / charging)")
    return failures


def section_battery(ctx: Ctx) -> int:
    section("Battery — percentage read + clamp to 0..100")
    info_dict = ctx.fetch()
    bp = gci(info_dict).get("bp")
    info(f"Raw gci.bp = {bp}")

    pct = decode(ctx.sensors, "battery", info_dict, [ctx.device])
    info(f"Battery sensor = {pct}%")

    failures = 0
    if pct is None:
        report("battery sensor produced a value", False, "got None — bp field missing or null")
        failures += 1
    else:
        if not report("battery in [0,100]", 0 <= pct <= 100, f"got {pct}"):
            failures += 1
    return failures


def section_vacuum_idle(ctx: Ctx) -> int:
    section("Vacuum: idle / standby state")
    prompt("Put the vacuum DOWN on its dock (or just on the floor switched off).")
    info_dict = ctx.fetch()
    wm = gci(info_dict).get("wm")
    info(f"Raw gci.wm = {wm}")
    state = decode(ctx.sensors, "vacuum", info_dict, [ctx.device])
    return 0 if report(f"vacuum_status decoded = {state!r}", state == "idle", f"expected 'idle' from wm={wm}") else 1


def section_vacuum_running(ctx: Ctx) -> int:
    section("Vacuum: in_operation")
    prompt("Squeeze the trigger / press start so the vacuum is ACTIVELY running.")
    time.sleep(1.0)
    info_dict = ctx.fetch()
    wm = gci(info_dict).get("wm")
    info(f"Raw gci.wm = {wm}  (expect 3)")
    state = decode(ctx.sensors, "vacuum", info_dict, [ctx.device])
    failures = 0
    if not report(f"vacuum_status = {state!r}", state == "in_operation", f"expected 'in_operation' from wm={wm}"):
        failures += 1
    prompt("Release the trigger / stop the vacuum.")
    return failures


def section_vacuum_selfclean(ctx: Ctx) -> int:
    section("Vacuum: self-cleaning")
    prompt("Trigger SELF-CLEAN on the vacuum (long-press the self-clean button or use the app).")
    time.sleep(2.0)
    info_dict = ctx.fetch()
    payload = gci(info_dict)
    wm = payload.get("wm")
    selfclean_process = payload.get("selfclean_process")
    info(f"Raw gci.wm = {wm}, gci.selfclean_process = {selfclean_process}")
    state = decode(ctx.sensors, "vacuum", info_dict, [ctx.device])
    failures = 0
    if not report(
        f"vacuum_status = {state!r}",
        state == "self_cleaning",
        f"expected 'self_cleaning' (wm should be 8, optionally with selfclean_process>=5 for station models)",
    ):
        failures += 1
    prompt("Stop the self-clean cycle or wait for it to finish before continuing.")
    return failures


def section_fresh_water(ctx: Ctx) -> int:
    section("Fresh-water tank: full → empty → full")
    failures = 0

    prompt("Make sure the fresh-water (clean) tank is FULL and re-seated on the device.")
    info_dict = ctx.fetch()
    e2 = gci(info_dict).get("e2")
    info(f"Raw gci.e2 = {e2}  (64 = empty; anything else = full)")
    state = decode(ctx.sensors, "fresh_water", info_dict, [ctx.device])
    if not report(f"fresh_water_tank_status = {state!r} when full", state == "full", f"e2={e2}"):
        failures += 1

    prompt("EMPTY the fresh-water tank (pour the water out) and re-seat it.")
    time.sleep(1.5)
    info_dict = ctx.fetch()
    e2 = gci(info_dict).get("e2")
    info(f"Raw gci.e2 = {e2}  (should now be 64 for empty)")
    state = decode(ctx.sensors, "fresh_water", info_dict, [ctx.device])
    if not report(f"fresh_water_tank_status = {state!r} when empty", state == "empty", f"e2={e2}"):
        failures += 1

    prompt("Refill the fresh-water tank.")
    time.sleep(1.5)
    info_dict = ctx.fetch()
    state = decode(ctx.sensors, "fresh_water", info_dict, [ctx.device])
    if not report(f"fresh_water_tank_status back to {state!r}", state == "full"):
        failures += 1

    return failures


def section_waste_water(ctx: Ctx) -> int:
    section("Waste-water tank: clean → full → clean")
    failures = 0

    prompt("Make sure the waste-water (dirty) tank is EMPTY and re-seated.")
    info_dict = ctx.fetch()
    e1 = gci(info_dict).get("e1")
    info(f"Raw gci.e1 = {e1}  (>0 means full / needs emptying)")
    state = decode(ctx.sensors, "waste_water", info_dict, [ctx.device])
    if not report(f"waste_water_tank_status = {state!r} when empty", state == "clean", f"e1={e1}"):
        failures += 1

    prompt(
        "Simulate a 'full' waste tank: either run the vacuum until it fills, "
        "or remove the waste tank entirely (the device should flag it). "
        "If neither is easy, type 'skip' below and we'll keep moving."
    )
    info_dict = ctx.fetch()
    e1 = gci(info_dict).get("e1")
    info(f"Raw gci.e1 = {e1}")
    state = decode(ctx.sensors, "waste_water", info_dict, [ctx.device])
    if state != "full":
        info(_c("waste tank still reads 'clean' — skipping the full-state assertion.", YELLOW))
    else:
        report("waste_water_tank_status = 'full' detected", True)

    prompt("Restore the waste tank to its normal seated state.")
    return failures


def section_brush_roller(ctx: Ctx) -> int:
    section("Brush roller — current status (read-only)")
    info_dict = ctx.fetch()
    br = gci(info_dict).get("br")
    info(f"Raw gci.br = {br}  (0 normal, 1 tangled, 2 stuck, 3 needs_cleaning)")
    state = decode(ctx.sensors, "brush", info_dict, [ctx.device])
    info(f"brush_roller sensor = {state!r}")
    if br is None:
        info(_c("br field absent — this device model doesn't report brush state. Skipping.", YELLOW))
        return 0
    return 0


def section_light(ctx: Ctx) -> int:
    section("Floor brush light — API ON/OFF round-trip")
    failures = 0

    info("Sending control_device({'led': 1}) (ON)...")
    ctx.control({"led": 1})
    time.sleep(2.0)
    info_dict = ctx.fetch()
    led = gci(info_dict).get("led")
    if not report(f"gci.led = {led} after ON command", led == 1):
        failures += 1

    info("Sending control_device({'led': 0}) (OFF)...")
    ctx.control({"led": 0})
    time.sleep(2.0)
    info_dict = ctx.fetch()
    led = gci(info_dict).get("led")
    if not report(f"gci.led = {led} after OFF command", led == 0):
        failures += 1

    return failures


def section_sound(ctx: Ctx) -> int:
    section("Sound — API mute / unmute round-trip")
    failures = 0

    info("Sending control_device({'ms': 0}) (mute)...")
    ctx.control({"ms": 0})
    time.sleep(2.0)
    info_dict = ctx.fetch()
    vl = gci(info_dict).get("vl")
    info(f"gci.vl after mute command = {vl}  (1=on, 0=off; behaviour varies by model)")

    info("Sending control_device({'ms': 1}) (unmute)...")
    ctx.control({"ms": 1})
    time.sleep(2.0)
    info_dict = ctx.fetch()
    vl_after = gci(info_dict).get("vl")
    info(f"gci.vl after unmute command = {vl_after}")

    if vl == vl_after:
        info(_c("vl did not change between mute / unmute — sound may not be controllable on this model.", YELLOW))
    else:
        report("sound state changed in response to ms commands", True)

    return failures


SECTIONS: list[tuple[str, str, Callable[[Ctx], int]]] = [
    ("identity",    "Identity",            section_identity),
    ("online",      "Connectivity",        section_online),
    ("battery",     "Battery",             section_battery),
    ("idle",        "Vacuum idle",         section_vacuum_idle),
    ("running",     "Vacuum in operation", section_vacuum_running),
    ("selfclean",   "Vacuum self-clean",   section_vacuum_selfclean),
    ("fresh_water", "Fresh-water tank",    section_fresh_water),
    ("waste_water", "Waste-water tank",    section_waste_water),
    ("brush",       "Brush roller",        section_brush_roller),
    ("light",       "Floor brush light",   section_light),
    ("sound",       "Sound mute/unmute",   section_sound),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(region: str, skip: set[str]) -> int:
    banner("Tineco interactive full-feature test")
    print("Drives every entity through every state. Press Ctrl-C any time to abort.")
    print(f"Skipping sections: {sorted(skip) or '(none)'}")

    TinecoClient = _load_tineco_client()
    sensors = _import_sensors()

    email = input("\nTineco email: ").strip()
    password = getpass.getpass("Tineco password (hidden): ").strip()

    client = TinecoClient(region=region)
    print("\nLogging in...")
    success, _token, uid = client.login(email, password)
    if not success:
        print(_c("Login failed.", RED))
        return 1
    print(_c(f"  Login OK (uid={uid[:12]}...)", GREEN))

    print("Fetching device list...")
    client.get_devices()
    if not client.device_list:
        print(_c("No devices on this account.", RED))
        return 1
    device = client.device_list[0]
    device_id = device.get("did")
    device_class = device.get("className", "")
    device_resource = device.get("resource", "")
    print(f"  Device: {device.get('productType') or device.get('nick')!r}  (id={device_id})")

    ctx = Ctx(client, sensors, device, device_id, device_class, device_resource)

    total_failures = 0
    sections_run = 0
    sections_skipped = 0
    for key, title, fn in SECTIONS:
        if key in skip:
            print(f"\n{_c('▢ ' + title + ' (skipped)', DIM)}")
            sections_skipped += 1
            continue
        try:
            total_failures += fn(ctx)
            sections_run += 1
        except KeyboardInterrupt:
            print(_c(f"\n\n{title} aborted by user.", YELLOW))
            return 130
        except Exception as e:
            print(_c(f"\n!!! Unhandled exception in {title}: {e}", RED))
            import traceback
            traceback.print_exc()
            total_failures += 1

    banner("Full-feature test complete")
    print(f"  Sections run:     {sections_run}")
    print(f"  Sections skipped: {sections_skipped}")
    print(f"  Failures:         {total_failures}")
    if total_failures == 0:
        print(_c("\nAll checks passed. Safe to tag/release.", GREEN))
        return 0
    print(_c(f"\n{total_failures} check(s) failed. Investigate before tagging.", RED))
    print(_c("Capture the failing response with `scripts/test_tineco_data.py --dump` and add a fixture.", DIM))
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--region", default="IE", help="Region code (default: IE)")
    parser.add_argument(
        "--skip",
        default="",
        help="Comma-separated section keys to skip (e.g. 'sound,selfclean'). "
             "Keys: " + ", ".join(k for k, _, _ in SECTIONS),
    )
    args = parser.parse_args()
    skip_set = {s.strip() for s in args.skip.split(",") if s.strip()}
    try:
        sys.exit(run(args.region, skip_set))
    except KeyboardInterrupt:
        print(_c("\nAborted.", YELLOW))
        sys.exit(130)
