"""Entity unique-id stability tests.

A unique-id rename (e.g. ``"model"`` → ``"device_model"``) silently orphans
every existing user's HA history for that entity and creates a duplicate.
These tests pin the exact strings each entity class produces, so a refactor
that touches a ``super().__init__(..., <sensor_type>, ...)`` call shows up
as a failing test rather than as broken history three weeks after release.
"""
from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

from custom_components.tineco.const import DOMAIN


EMAIL = "stable@example.com"
ENTRY_ID = "unique-id-test"


def _make_entry():
    return types.SimpleNamespace(entry_id=ENTRY_ID, data={"email": EMAIL})


def _make_fake_hass():
    return types.SimpleNamespace(
        data={DOMAIN: {ENTRY_ID: {"client": types.SimpleNamespace(devices=[])}}}
    )


# ---------------------------------------------------------------------------
# Sensor platform — concrete signature: (config_entry, hass, coordinator)
# ---------------------------------------------------------------------------

SENSOR_EXPECTED_SUFFIXES = [
    ("TinecoFirmwareVersionSensor", "firmware_version"),
    ("TinecoAPISensor",             "api_version"),
    ("TinecoModelSensor",           "model"),
    ("TinecoBatterySensor",         "battery"),
    ("TinecoVacuumStatusSensor",    "vacuum_status"),
    ("TinecoWaterTankSensor",       "waste_water_tank_status"),
    ("TinecoFreshWaterTankSensor",  "fresh_water_tank_status"),
    ("TinecoBrushRollerSensor",     "brush_roller"),
]


@pytest.mark.parametrize("cls_name,suffix", SENSOR_EXPECTED_SUFFIXES)
def test_sensor_unique_id(cls_name, suffix):
    from custom_components.tineco import sensor as sensor_mod

    cls = getattr(sensor_mod, cls_name)
    instance = cls(_make_entry(), _make_fake_hass(), coordinator=MagicMock())

    assert instance._attr_unique_id == f"{DOMAIN}_{EMAIL}_{suffix}"


# ---------------------------------------------------------------------------
# Switch platform — concrete signature: (config_entry, hass)
# ---------------------------------------------------------------------------

SWITCH_EXPECTED_SUFFIXES = [
    ("TinecoDevicePowerSwitch",     "power"),
    ("TinecoAudioSwitch",           "sound"),
    ("TinecoFloorBrushLightSwitch", "floor_brush_light"),
    ("TinecoWaterOnlyModeSwitch",   "water_only_mode"),
]


@pytest.mark.parametrize("cls_name,suffix", SWITCH_EXPECTED_SUFFIXES)
def test_switch_unique_id(cls_name, suffix):
    from custom_components.tineco import switch as switch_mod

    cls = getattr(switch_mod, cls_name)
    instance = cls(_make_entry(), _make_fake_hass())

    assert instance._attr_unique_id == f"{DOMAIN}_{EMAIL}_{suffix}"


# ---------------------------------------------------------------------------
# Binary sensor platform — concrete signature: (config_entry, hass, coordinator)
#
# These are now CoordinatorEntity-based (state derived from the shared
# DataUpdateCoordinator rather than per-entity IoT polling).
# ---------------------------------------------------------------------------

BINARY_SENSOR_EXPECTED_SUFFIXES = [
    ("TinecoDeviceOnlineSensor",   "online"),
    ("TinecoChargingSensor",       "charging"),
]


@pytest.mark.parametrize("cls_name,suffix", BINARY_SENSOR_EXPECTED_SUFFIXES)
def test_binary_sensor_unique_id(cls_name, suffix):
    from custom_components.tineco import binary_sensor as bs_mod

    cls = getattr(bs_mod, cls_name)
    instance = cls(_make_entry(), _make_fake_hass(), coordinator=MagicMock())

    assert instance._attr_unique_id == f"{DOMAIN}_{EMAIL}_{suffix}"


# ---------------------------------------------------------------------------
# Select platform — VolumeSelect uses a hardcoded "volume_level" suffix,
# the others go through TinecoBaseSelect with a select_type argument.
# ---------------------------------------------------------------------------

def test_volume_select_unique_id_stable():
    """Volume select hardcodes its unique_id suffix to "volume_level" rather
    than the generic ``{select_type}`` pattern. Lock that exact string so an
    accidental refactor doesn't lose its history."""
    from custom_components.tineco.select import TinecoVolumeSelect

    instance = TinecoVolumeSelect(_make_entry(), _make_fake_hass())

    assert instance._attr_unique_id == f"{DOMAIN}_{EMAIL}_volume_level"


# Concrete TinecoBaseSelect subclasses each pass their own select_type literal
# to super().__init__. Lock each one.
BASE_SELECT_EXPECTED_SUFFIXES = [
    "running_speed",
    "cleaning_method",
    "suction_power",
    "max_power",
    "max_spray_volume",
    "water_mode_power",
    "water_mode_spray_volume",
]


@pytest.mark.parametrize("suffix", BASE_SELECT_EXPECTED_SUFFIXES)
def test_base_select_suffix_present_in_source(suffix):
    """Static check — confirms the ``select_type`` literal still appears as
    a string in ``select.py``. Catches accidental renames in
    ``super().__init__(config_entry, hass, "<suffix>", ...)`` calls."""
    from custom_components.tineco import select as select_mod
    from pathlib import Path

    source = Path(select_mod.__file__).read_text(encoding="utf-8")
    assert f'"{suffix}"' in source, (
        f'Expected select_type literal "{suffix}" not found in select.py. '
        f'If you intentionally renamed it, update this test AND add an '
        f'entity-id migration so existing users do not lose history.'
    )
