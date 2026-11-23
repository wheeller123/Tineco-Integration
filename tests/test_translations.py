"""Translation coverage for selects and enum sensors (issue #40).

Select option values are stable lowercase keys; Home Assistant shows the
translated label from ``entity.<platform>.<translation_key>.state.<option>``.
These tests make sure every language ships a label for every translatable
option and that all languages expose the same keys as English.
"""
from __future__ import annotations

import json
import re
import types
from pathlib import Path

import pytest

from custom_components.tineco import select as select_mod
from custom_components.tineco import sensor as sensor_mod

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "tineco"
LANGUAGES = ["en", "es", "fr"]
KEY_RE = re.compile(r"^[a-z0-9_-]+$")
WATT_RE = re.compile(r"^\d+W$")

SELECT_CLASSES = [
    select_mod.TinecoVolumeSelect,
    select_mod.TinecoRunningSpeedSelect,
    select_mod.TinecoCleaningMethodSelect,
    select_mod.TinecoSuctionPowerSelect,
    select_mod.TinecoMaxPowerSelect,
    select_mod.TinecoMaxSprayVolumeSelect,
    select_mod.TinecoWaterModePowerSelect,
    select_mod.TinecoWaterModeSprayVolumeSelect,
]

ENUM_SENSOR_CLASSES = [
    sensor_mod.TinecoVacuumStatusSensor,
    sensor_mod.TinecoWaterTankSensor,
    sensor_mod.TinecoFreshWaterTankSensor,
    sensor_mod.TinecoBrushRollerSensor,
]


def _load(folder: str, lang: str) -> dict:
    return json.loads((COMPONENT / folder / f"{lang}.json").read_text(encoding="utf-8"))


def _keys(obj, prefix=""):
    """Flatten a nested dict into dotted key paths."""
    if not isinstance(obj, dict):
        return {prefix}
    out = set()
    for k, v in obj.items():
        out |= _keys(v, f"{prefix}.{k}" if prefix else k)
    return out


def _entry():
    return types.SimpleNamespace(entry_id="e1", data={"email": "user@example.com"})


def _select(cls):
    return cls(_entry(), types.SimpleNamespace(data={}))


def _sensor(cls):
    return cls(_entry(), types.SimpleNamespace(data={}), coordinator=None)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_language_has_same_keys_as_english(lang):
    """Every language translates exactly the keys English defines."""
    assert _keys(_load("translations", lang)) == _keys(_load("translations", "en"))


@pytest.mark.parametrize("lang", LANGUAGES)
def test_strings_mirror_translations(lang):
    """strings/ is a mirror of translations/ and must not drift."""
    assert _load("strings", lang) == _load("translations", lang)


@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("cls", SELECT_CLASSES, ids=lambda c: c.__name__)
def test_select_options_translated(cls, lang):
    """Each select has a translation entry and a label for each word option."""
    entity = _select(cls)
    entry = _load("translations", lang)["entity"]["select"][entity.translation_key]
    assert entry["name"]
    for option in entity.options:
        if WATT_RE.match(option):
            continue  # watt values are shown as-is, not translated
        assert KEY_RE.match(option), f"{option!r} is not a valid translation key"
        assert entry["state"][option], f"{lang}: missing label for {option!r}"


@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("cls", ENUM_SENSOR_CLASSES, ids=lambda c: c.__name__)
def test_enum_sensor_states_translated(cls, lang):
    """Every enum sensor option has a label (fixes the old 'dirty'/'full' mismatch)."""
    entity = _sensor(cls)
    states = _load("translations", lang)["entity"]["sensor"][entity.translation_key]["state"]
    assert set(states) == set(entity.options)


def test_select_option_values_unchanged_on_device():
    """Renaming option keys must not change the values sent to the device."""
    assert select_mod.VOLUME_LEVELS == {"low": 1, "medium": 2, "high": 3}
    assert select_mod.RUNNING_SPEED_LEVELS == {"soft": 0, "medium": 1, "max": 2}
    assert select_mod.CLEANING_METHOD_LEVELS == {"clean_water": 0, "detergent": 1}
    assert select_mod.MAX_SPRAY_VOLUME_LEVELS == {"rinse": 3, "max": 4}
    assert select_mod.WATER_MODE_SPRAY_VOLUME_LEVELS == {
        "mist": 0, "wet": 1, "medium": 2, "rinse": 3, "max": 4,
    }
