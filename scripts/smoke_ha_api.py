#!/usr/bin/env python3
"""Post-deploy smoke test against a running Home Assistant instance.

After ``deploy-to-homeassistant.ps1`` pushes the new build to your test HA,
run this to verify all Tineco entities exist and are reporting sane values.

It hits HA's REST API at ``$HA_URL`` (default ``http://192.168.0.160:8123``)
with a long-lived access token from ``$HA_TOKEN``. It does NOT call the
Tineco API directly — it asserts that what HA *sees* through the integration
matches expectations.

Checks performed:

* Every ``sensor.tineco_*``, ``switch.tineco_*``, ``select.tineco_*``,
  ``binary_sensor.tineco_*`` entity must exist.
* No entity may be ``unknown`` / ``unavailable``.
* The model sensor (``sensor.tineco_model``) must not look like an internal
  project code (e.g. ``Floor One-1580``) — that's the v2.2.10→v2.2.12
  regression signature.
* Battery sensor must be a valid percentage (0–100).
* Vacuum status must be one of the enum options.

Run::

    export HA_URL=http://192.168.0.160:8123
    export HA_TOKEN=ey...   # HA → profile → security → long-lived token
    python scripts/smoke_ha_api.py

Exits non-zero on any failure so it can gate a release script.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any

try:
    import requests
except ImportError:
    print("requests not installed — pip install requests", file=sys.stderr)
    sys.exit(2)


# ----------------------------------------------------------------------------
# Output helpers (same style as smoke_vacuum_state.py)
# ----------------------------------------------------------------------------

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
DIM = "\033[2m"
RESET = "\033[0m"


def _color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(text: str, color: str) -> str:
    return f"{color}{text}{RESET}" if _color() else text


def report(check: str, ok: bool, detail: str = "") -> bool:
    mark = _c("PASS", GREEN) if ok else _c("FAIL", RED)
    suffix = f"  {_c(detail, DIM)}" if detail else ""
    print(f"  [{mark}] {check}{suffix}")
    return ok


# ----------------------------------------------------------------------------
# Required entities. Update this list when adding a new platform/entity.
# ----------------------------------------------------------------------------

REQUIRED_ENTITY_PREFIXES = {
    "sensor.tineco_": [
        "firmware_version",
        "api_version",
        "model",
        "battery",
        "vacuum_status",
    ],
    "switch.tineco_": [
        # Suffix matched against the entity_id; HA slugifies "Sound" → "tineco_sound" etc.
        "sound",
        "floor_brush_light",
    ],
    "binary_sensor.tineco_": [
        "online",
        "charging",
    ],
}

VACUUM_STATUS_OPTIONS = {"idle", "in_operation", "self_cleaning"}

# Pattern that identifies an internal project code mistakenly used as a model
# name — e.g. "Floor One-1580", "CL2349-Switch", etc.
INTERNAL_CODE_RE = re.compile(r".*-\d{3,5}$")


# ----------------------------------------------------------------------------
# HA REST API client
# ----------------------------------------------------------------------------

def fetch_states(base_url: str, token: str) -> list[dict[str, Any]]:
    url = base_url.rstrip("/") + "/api/states"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ----------------------------------------------------------------------------
# Smoke checks
# ----------------------------------------------------------------------------

def run(base_url: str, token: str) -> int:
    print(_c(f"\nQuerying {base_url}/api/states ...", DIM))
    try:
        states = fetch_states(base_url, token)
    except Exception as e:
        print(_c(f"Cannot reach HA: {e}", RED))
        return 2

    tineco_states = {s["entity_id"]: s for s in states if "tineco" in s["entity_id"]}
    if not tineco_states:
        print(_c("No Tineco entities found. Is the integration installed/configured?", RED))
        return 1

    print(_c(f"Found {len(tineco_states)} Tineco entities", DIM))
    failures = 0

    # ---- Required entities present ----
    print("\nRequired entities:")
    for prefix, suffixes in REQUIRED_ENTITY_PREFIXES.items():
        for suffix in suffixes:
            entity_id = prefix + suffix
            ok = entity_id in tineco_states
            if not report(f"{entity_id} present", ok):
                failures += 1

    # ---- No entity is unknown/unavailable ----
    print("\nEntity states:")
    for entity_id, state in sorted(tineco_states.items()):
        value = state.get("state")
        ok = value not in ("unknown", "unavailable", None, "")
        if not report(f"{entity_id} = {value!r}", ok):
            failures += 1

    # ---- Model sensor not an internal project code ----
    model = tineco_states.get("sensor.tineco_model", {}).get("state")
    if model:
        looks_like_code = bool(INTERNAL_CODE_RE.match(model))
        if not report(
            f"sensor.tineco_model = {model!r} is a real model name",
            not looks_like_code,
            detail="resembles internal project code (regression of v2.2.10→v2.2.12)" if looks_like_code else "",
        ):
            failures += 1

    # ---- Battery in valid percentage range ----
    battery = tineco_states.get("sensor.tineco_battery", {}).get("state")
    if battery is not None:
        try:
            pct = float(battery)
            ok = 0 <= pct <= 100
            report(f"sensor.tineco_battery = {pct}% in [0,100]", ok)
            if not ok:
                failures += 1
        except (TypeError, ValueError):
            report(f"sensor.tineco_battery = {battery!r} is numeric", False)
            failures += 1

    # ---- Vacuum status is a known enum option ----
    vacuum = tineco_states.get("sensor.tineco_vacuum_status", {}).get("state")
    if vacuum:
        if not report(
            f"sensor.tineco_vacuum_status = {vacuum!r} is a known option",
            vacuum in VACUUM_STATUS_OPTIONS,
            detail=f"valid options: {sorted(VACUUM_STATUS_OPTIONS)}",
        ):
            failures += 1

    print()
    if failures == 0:
        print(_c("All HA smoke checks passed.", GREEN))
        return 0
    print(_c(f"{failures} check(s) failed. Do not promote this build.", RED))
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--url",
        default=os.environ.get("HA_URL", "http://192.168.0.160:8123"),
        help="HA base URL (default: $HA_URL or http://192.168.0.160:8123)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("HA_TOKEN"),
        help="HA long-lived access token (default: $HA_TOKEN env var)",
    )
    args = parser.parse_args()

    if not args.token:
        print("Provide a long-lived access token via --token or $HA_TOKEN.", file=sys.stderr)
        print("Create one in HA → user profile → Security → Long-lived access tokens.", file=sys.stderr)
        sys.exit(2)

    try:
        sys.exit(run(args.url, args.token))
    except KeyboardInterrupt:
        print(_c("\nAborted.", YELLOW))
        sys.exit(130)
