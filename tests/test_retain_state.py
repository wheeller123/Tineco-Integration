"""Retain/restore behaviour tests for issue #35.

Issue #35: the Tineco S11 handheld only reports "online" while its trigger is
held, so the coordinator refresh fails almost immediately and — because every
entity subclasses ``CoordinatorEntity`` with no ``available`` override — the
sensors flip to *unavailable* right away.

The fix (``TinecoRetainingSensor``) makes the chosen sensors RETAIN their last
reported value across offline periods and RESTORE it on restart. The binary
sensors (online/charging) deliberately do NOT retain.

Pure-logic tests use the ``make_sensor()`` helper and run on any OS. The
HA-runner restore test is guarded exactly like ``tests/test_coordinator.py``
(importorskip + win32 skip) and primes a last state to assert the battery
sensor restores it in ``async_added_to_hass``.
"""
from __future__ import annotations

import sys
import types

import pytest

from custom_components.tineco.binary_sensor import (
    TinecoChargingSensor,
    TinecoDeviceOnlineSensor,
)
from custom_components.tineco.sensor import (
    TinecoBatterySensor,
    TinecoBrushRollerSensor,
    TinecoFreshWaterTankSensor,
    TinecoModelSensor,
    TinecoRetainingSensor,
    TinecoVacuumStatusSensor,
    TinecoWaterTankSensor,
)

from .conftest import make_sensor


# ---------------------------------------------------------------------------
# (a) Battery keeps its last value across an empty refresh
# ---------------------------------------------------------------------------

def test_battery_keeps_last_value_on_empty_update(load_fixture):
    """After a good reading (93 from s7_flashdry), an empty/no-data update must
    KEEP 93 rather than reset to None (issue #35 primary scenario)."""
    fx = load_fixture("s7_flashdry")
    sensor = make_sensor(TinecoBatterySensor, devices=fx["devices"])

    sensor._update_state_from_data(fx["info"])
    assert sensor._state == 93

    # Device went offline → coordinator produced no usable reading.
    sensor._update_state_from_data({})

    assert sensor._state == 93


def test_battery_stays_none_before_first_reading():
    """Before the very first real reading, battery is still None/unknown."""
    sensor = make_sensor(TinecoBatterySensor)

    sensor._update_state_from_data({})

    assert sensor._state is None
    assert sensor._has_value is False


def test_battery_marks_has_value_after_reading():
    """A real reading flips the _has_value flag that drives availability."""
    sensor = make_sensor(TinecoBatterySensor)

    sensor._update_state_from_data({"gci": {"bp": 50}})

    assert sensor._state == 50
    assert sensor._has_value is True


# ---------------------------------------------------------------------------
# (b) `available` stays True once a value is known, even when the coordinator's
#     last refresh failed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sensor_cls", [
    TinecoBatterySensor,
    TinecoModelSensor,
    TinecoVacuumStatusSensor,
    TinecoWaterTankSensor,
    TinecoFreshWaterTankSensor,
    TinecoBrushRollerSensor,
], ids=lambda c: c.__name__)
def test_available_true_once_value_known_despite_failed_refresh(sensor_cls):
    """A retaining sensor that already holds a value must report available=True
    even when coordinator.last_update_success is False (device offline).

    make_sensor() bypasses __init__, so we set the attributes the property
    reads: the retained-value flag and a failed coordinator.
    """
    sensor = make_sensor(sensor_cls)
    sensor._has_value = True
    sensor.coordinator = types.SimpleNamespace(last_update_success=False, data=None)

    assert sensor.available is True


def test_retaining_sensor_is_base_for_all_eight():
    """All eight retaining sensors subclass TinecoRetainingSensor."""
    from custom_components.tineco.sensor import (
        TinecoAPISensor,
        TinecoFirmwareVersionSensor,
    )

    for cls in (
        TinecoFirmwareVersionSensor,
        TinecoAPISensor,
        TinecoModelSensor,
        TinecoBatterySensor,
        TinecoVacuumStatusSensor,
        TinecoWaterTankSensor,
        TinecoFreshWaterTankSensor,
        TinecoBrushRollerSensor,
    ):
        assert issubclass(cls, TinecoRetainingSensor)


# ---------------------------------------------------------------------------
# (c) Non-retaining guard for the binary sensors
# ---------------------------------------------------------------------------

def test_binary_sensors_do_not_retain():
    """online/charging must NOT inherit the retaining behaviour: they track the
    live coordinator so a stale 'online'/'charging' can't mislead."""
    for cls in (TinecoDeviceOnlineSensor, TinecoChargingSensor):
        assert not issubclass(cls, TinecoRetainingSensor)
        # No custom `available` override / no _has_value retention flag:
        assert "available" not in vars(cls)


def test_online_sensor_follows_live_coordinator():
    """Online reflects the live coordinator; it does not retain a prior True."""
    sensor = TinecoDeviceOnlineSensor.__new__(TinecoDeviceOnlineSensor)
    sensor._state = True
    sensor.coordinator = types.SimpleNamespace(last_update_success=False, data=None)

    sensor._update_state_from_coordinator()

    assert sensor._state is False


# ---------------------------------------------------------------------------
# HA-runner restore test — guarded exactly like tests/test_coordinator.py
# ---------------------------------------------------------------------------

pytest.importorskip("pytest_homeassistant_custom_component")
if sys.platform == "win32":
    pytest.skip("HA runner requires fcntl (POSIX-only)", allow_module_level=True)

from unittest.mock import MagicMock  # noqa: E402

from homeassistant.components.sensor import SensorExtraStoredData  # noqa: E402
from homeassistant.core import HomeAssistant, State  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from custom_components.tineco.const import DOMAIN  # noqa: E402


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    """Declare the plugin's ``enable_custom_integrations`` as a fixture
    dependency so pytest resolves the async ``hass`` chain correctly."""
    yield


@pytest.mark.asyncio
async def test_battery_sensor_restores_last_value(hass: HomeAssistant):
    """Priming a stored battery value should be restored by the battery sensor
    in async_added_to_hass (RestoreSensor path)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"email": "restore@example.com"},
        unique_id="restore@example.com",
    )

    coordinator = MagicMock()
    coordinator.data = None
    coordinator.last_update_success = False

    sensor = TinecoBatterySensor(entry, hass, coordinator)
    # RestoreSensor keys its stored data on the entity_id, so assign one and
    # prime the restore cache for exactly that id.
    sensor.entity_id = "sensor.tineco_battery_restore"
    sensor.hass = hass

    extra = SensorExtraStoredData(
        native_value=77,
        native_unit_of_measurement="%",
    )
    mock_restore_cache_with_extra_data(
        hass,
        ((State(sensor.entity_id, "77"), extra.as_dict()),),
    )

    await sensor.async_added_to_hass()

    assert sensor._state == 77
    assert sensor._has_value is True
    # Once a value is restored the entity is available even though the
    # coordinator's last refresh failed (device offline).
    assert sensor.available is True
