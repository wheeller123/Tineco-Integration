"""Walk every fixture file and assert each sensor produces a usable state.

Adding a new fixture to ``tests/fixtures/*.json`` automatically grows coverage
of the model/firmware/vacuum/battery/water/brush sensors. Use this to lock
the common-case payload shape across known devices.

A "usable state" excludes the integration's sentinel-bad values:
``None``, ``"Unknown"``, ``"Tineco Device"``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.tineco.sensor import (
    TinecoBatterySensor,
    TinecoBrushRollerSensor,
    TinecoFreshWaterTankSensor,
    TinecoModelSensor,
    TinecoVacuumStatusSensor,
    TinecoWaterTankSensor,
)

from .conftest import make_sensor

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Sensor classes covered by the parametrized walk. We deliberately leave
# firmware and api_version out because not every captured device exposes
# those fields and we don't want to penalise sparse fixtures.
SENSOR_CLASSES = [
    TinecoModelSensor,
    TinecoBatterySensor,
    TinecoVacuumStatusSensor,
    TinecoWaterTankSensor,
    TinecoFreshWaterTankSensor,
    TinecoBrushRollerSensor,
]

BAD_STATES = {None, "Unknown", "Tineco Device"}


def _all_fixtures():
    """Yield (fixture_name, fixture_dict) for every JSON in the fixtures dir."""
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as fh:
            yield path.stem, json.load(fh)


@pytest.mark.parametrize("fixture_name,fixture_data", list(_all_fixtures()))
@pytest.mark.parametrize("sensor_cls", SENSOR_CLASSES, ids=lambda c: c.__name__)
def test_sensor_produces_usable_state(fixture_name, fixture_data, sensor_cls):
    """Each sensor must produce a non-sentinel state from each fixture."""
    devices = fixture_data.get("devices") or []
    info = fixture_data.get("info") or {}

    sensor = make_sensor(sensor_cls, devices=devices)
    sensor._update_state_from_data(info)

    assert sensor._state not in BAD_STATES, (
        f"{sensor_cls.__name__} produced sentinel state {sensor._state!r} "
        f"for fixture {fixture_name!r}. Either the fixture is missing the "
        f"source field for this sensor, or the sensor's _update_state_from_data "
        f"regressed."
    )


# ---------------------------------------------------------------------------
# Per-model assertions (release checklist: "When a new device model gets
# reported in issues" → add a one-line assertion for the new fixture).
# ---------------------------------------------------------------------------

def test_s5_combo_model_and_battery(load_fixture):
    """Floor One S5 Combo (#33) — model comes from productType, and the
    bp=240 fully-charged sentinel clamps to 100%."""
    fx = load_fixture("s5_combo_no_led")

    model = make_sensor(TinecoModelSensor, devices=fx["devices"])
    model._update_state_from_data(fx["info"])
    battery = make_sensor(TinecoBatterySensor, devices=fx["devices"])
    battery._update_state_from_data(fx["info"])

    assert model._state == "Floor One S5 Combo"
    assert battery._state == 100
