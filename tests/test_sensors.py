"""Sensor _update_state_from_data unit tests against captured fixtures.

The regression-of-record is:
    nick='Floor One-1580', productType='S7 Flashdry'  →  model sensor must
    report 'S7 Flashdry'.

Other sensors are checked against the same fixture so the most-common
device payload shape is locked in.
"""
from __future__ import annotations

import pytest

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

from .conftest import make_sensor


# ---------------------------------------------------------------------------
# Keystone test — would have caught the v2.2.10→v2.2.12 Floor One-1580 regression
# ---------------------------------------------------------------------------

def test_model_sensor_prefers_producttype_over_nick(load_fixture):
    """Tineco's default nick now embeds an internal project code
    ('Floor One-1580'). The canonical model name lives in productType
    ('S7 Flashdry'). The model sensor must surface productType."""
    fx = load_fixture("s7_flashdry")
    sensor = make_sensor(TinecoModelSensor, devices=fx["devices"])

    sensor._update_state_from_data(fx["info"])

    assert sensor._state == "S7 Flashdry"
    assert "Floor One-1580" not in sensor._state


def test_model_sensor_falls_back_to_nick_when_producttype_empty(load_fixture):
    """If Tineco ever stops returning productType, nick is acceptable as
    a last resort — guarded so we don't drift back to 'Unknown'."""
    fx = load_fixture("s7_flashdry")
    device = dict(fx["devices"][0])
    device["productType"] = ""
    device["productName"] = ""
    device["nick"] = "S7 Flashdry"
    sensor = make_sensor(TinecoModelSensor, devices=[device])

    sensor._update_state_from_data(fx["info"])

    assert sensor._state == "S7 Flashdry"


def test_model_sensor_skips_device_id_style_name():
    """If only `name` is available and it looks like a device ID
    (starts with '0000'), don't use it as a model label."""
    device = {"name": "0000000abc123def4567"}
    sensor = make_sensor(TinecoModelSensor, devices=[device])

    sensor._update_state_from_data({})

    # No model found → falls through to the endpoint scan → "Tineco Device"
    assert sensor._state in ("Tineco Device", "Unknown")
    assert not sensor._state.startswith("0000")


# ---------------------------------------------------------------------------
# Other sensors against the same fixture — lock in the common payload shape
# ---------------------------------------------------------------------------

def test_battery_sensor_reads_bp_from_gci(load_fixture):
    fx = load_fixture("s7_flashdry")
    sensor = make_sensor(TinecoBatterySensor, devices=fx["devices"])

    sensor._update_state_from_data(fx["info"])

    assert sensor._state == 93


def test_battery_sensor_clamps_240_to_100():
    sensor = make_sensor(TinecoBatterySensor)

    sensor._update_state_from_data({"gci": {"bp": 240}})

    assert sensor._state == 100


def test_vacuum_status_idle_from_wm_2(load_fixture):
    """wm=2 (charging) → idle, per the decompiled CL2349 state machine."""
    fx = load_fixture("s7_flashdry")
    sensor = make_sensor(TinecoVacuumStatusSensor, devices=fx["devices"])

    sensor._update_state_from_data(fx["info"])

    assert sensor._state == "idle"


def test_vacuum_status_in_operation_from_wm_3():
    sensor = make_sensor(TinecoVacuumStatusSensor)

    sensor._update_state_from_data({"gci": {"wm": 3}})

    assert sensor._state == "in_operation"


def test_vacuum_status_self_cleaning_wm_8_no_selfclean_process():
    """S7 Flashdry (no station): wm=8 alone means self-cleaning."""
    sensor = make_sensor(TinecoVacuumStatusSensor)

    sensor._update_state_from_data({"gci": {"wm": 8}})

    assert sensor._state == "self_cleaning"


def test_vacuum_status_idle_during_preclean_charge_wm_8_process_1():
    """CL2349 Switch S7 (station): wm=8 + selfclean_process 1-4 = pre-clean charging → idle."""
    sensor = make_sensor(TinecoVacuumStatusSensor)

    sensor._update_state_from_data({"gci": {"wm": 8, "selfclean_process": 2}})

    assert sensor._state == "idle"


def test_vacuum_status_self_cleaning_wm_8_process_5():
    sensor = make_sensor(TinecoVacuumStatusSensor)

    sensor._update_state_from_data({"gci": {"wm": 8, "selfclean_process": 5}})

    assert sensor._state == "self_cleaning"


def test_water_tank_clean_when_e1_zero(load_fixture):
    fx = load_fixture("s7_flashdry")
    sensor = make_sensor(TinecoWaterTankSensor, devices=fx["devices"])

    sensor._update_state_from_data(fx["info"])

    assert sensor._state == "clean"


def test_water_tank_full_when_e1_nonzero():
    sensor = make_sensor(TinecoWaterTankSensor)

    sensor._update_state_from_data({"gci": {"e1": 1}})

    assert sensor._state == "full"


def test_fresh_water_tank_full_when_e2_zero(load_fixture):
    fx = load_fixture("s7_flashdry")
    sensor = make_sensor(TinecoFreshWaterTankSensor, devices=fx["devices"])

    sensor._update_state_from_data(fx["info"])

    assert sensor._state == "full"


def test_fresh_water_tank_empty_when_e2_is_64():
    sensor = make_sensor(TinecoFreshWaterTankSensor)

    sensor._update_state_from_data({"gci": {"e2": 64}})

    assert sensor._state == "empty"


def test_brush_roller_normal_when_no_br_field(load_fixture):
    """Default to 'normal' when the device doesn't report a brush-roller state."""
    fx = load_fixture("s7_flashdry")
    sensor = make_sensor(TinecoBrushRollerSensor, devices=fx["devices"])

    sensor._update_state_from_data(fx["info"])

    assert sensor._state == "normal"


@pytest.mark.parametrize("br,expected", [
    (0, "normal"),
    (1, "tangled"),
    (2, "stuck"),
    (3, "needs_cleaning"),
])
def test_brush_roller_status_mapping(br, expected):
    sensor = make_sensor(TinecoBrushRollerSensor)

    sensor._update_state_from_data({"gci": {"br": br}})

    assert sensor._state == expected


def test_firmware_sensor_reads_vv_from_gav(load_fixture):
    fx = load_fixture("s7_flashdry")
    sensor = make_sensor(TinecoFirmwareVersionSensor, devices=fx["devices"])

    sensor._update_state_from_data(fx["info"])

    # Fixture has gav.vv = "1.0.5"
    assert sensor._state == "1.0.5"


def test_firmware_sensor_strips_garbage_chars():
    sensor = make_sensor(TinecoFirmwareVersionSensor)

    sensor._update_state_from_data({"gav": {"vv": "1.0.5\x00\x01"}})

    assert sensor._state == "1.0.5"


def test_api_version_sensor_reads_av_from_gav(load_fixture):
    fx = load_fixture("s7_flashdry")
    sensor = make_sensor(TinecoAPISensor, devices=fx["devices"])

    sensor._update_state_from_data(fx["info"])

    assert sensor._state == "v3"
