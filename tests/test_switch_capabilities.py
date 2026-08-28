"""Floor Brush Light capability-detection tests (issue #33).

The Floor One S5 Combo has no floor brush light hardware and never reports the
``led`` field in its ``gci`` payload — but the Tineco cloud API still answers a
``{'led': 0}`` command with a success response. The old code created the switch
unconditionally, so users got a control that reported success and did nothing.

These tests pin the three guarantees of the fix:

1. A device whose ``gci`` lacks ``led`` gets no Floor Brush Light entity.
2. A device whose ``gci`` has ``led`` still gets one (no regression for the
   S7 Flashdry / Floor One S5).
3. Absence of a ``gci`` payload (failed first refresh, timed-out endpoint) is
   *not* treated as "unsupported" — the entity is still created, because a
   transient API failure must never silently drop a working control.
"""
from __future__ import annotations

import asyncio
import types

import pytest

from custom_components.tineco.const import DOMAIN
from custom_components.tineco.switch import (
    TinecoFloorBrushLightSwitch,
    async_setup_entry,
    led_supported,
)

EMAIL = "capability@example.com"
ENTRY_ID = "capability-test"

# Exactly the field set from the issue #33 debug log.
S5_COMBO_GCI = {
    "cds": 0, "wm": 2, "scm": 0, "cnv": 0, "scs": 0, "smr": 0, "sr": 2,
    "dv": 0, "bp": 240, "bc": 2500, "msr": 0, "vl": 4, "vs": 2, "e": 0, "cc": 0,
}

S7_FLASHDRY_GCI = {
    "selectmode": 0, "wheel": 2, "cleanway": 1, "led": 0, "msr": 0, "vl": 1,
    "wm": 2, "dv": 0, "bp": 93, "vs": 1, "e1": 0, "e2": 0, "e3": 0, "wp": 238,
}


def _make_entry():
    return types.SimpleNamespace(entry_id=ENTRY_ID, data={"email": EMAIL})


def _make_hass(info):
    """Fake hass whose coordinator returns ``info`` as its last-fetched data."""
    coordinator = types.SimpleNamespace(data=info)
    return types.SimpleNamespace(
        data={DOMAIN: {ENTRY_ID: {"coordinator": coordinator}}}
    )


def _setup_switch_types(info):
    """Run the platform setup against ``info`` and return the switch_types added."""
    added = []

    def _async_add_entities(entities):
        added.extend(entities)

    asyncio.run(async_setup_entry(_make_hass(info), _make_entry(), _async_add_entities))
    return [e.switch_type for e in added]


# ---------------------------------------------------------------------------
# led_supported() — the pure capability predicate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("info,expected", [
    ({"gci": S5_COMBO_GCI}, False),                      # S5 Combo: no LED hardware
    ({"gci": S7_FLASHDRY_GCI}, True),                    # S7 Flashdry: has LED
    ({"gci": {"led": 1}}, True),                         # led=1 (off) still means supported
    ({}, None),                                          # no endpoints at all → unknown
    ({"cfp": {"wm": 2}}, None),                          # cfp alone can't settle it
    ({"gav": {"vv": "1.0"}}, None),                      # unrelated endpoint → unknown
    (None, None),                                        # no coordinator data → unknown
])
def test_led_supported(info, expected):
    assert led_supported(info) is expected


def test_led_supported_ignores_cfp_absence():
    """``cfp`` omits ``led`` even on models that have the light, so a present
    ``gci`` must win over an ``led``-less ``cfp``. Keying off ``cfp`` would
    wrongly delete the switch for every S7 Flashdry."""
    info = {"gci": S7_FLASHDRY_GCI, "cfp": {"wm": 2, "bp": 93}}

    assert led_supported(info) is True


# ---------------------------------------------------------------------------
# Platform setup — which entities actually get created
# ---------------------------------------------------------------------------

def test_setup_skips_brush_light_when_led_absent():
    """Issue #33: no ``led`` field → no Floor Brush Light entity, but the other
    switches are unaffected."""
    switch_types = _setup_switch_types({"gci": S5_COMBO_GCI})

    assert "floor_brush_light" not in switch_types
    assert switch_types == ["sound", "water_only_mode"]


def test_setup_creates_brush_light_when_led_present():
    switch_types = _setup_switch_types({"gci": S7_FLASHDRY_GCI})

    assert switch_types == ["sound", "floor_brush_light", "water_only_mode"]


@pytest.mark.parametrize("info", [None, {}, {"cfp": {"wm": 2}}], ids=["no-data", "empty", "cfp-only"])
def test_setup_creates_brush_light_when_capability_unknown(info):
    """A failed first refresh must not delete a working control — unknown is
    treated as supported, and the entity's ``available`` sorts it out later."""
    switch_types = _setup_switch_types(info)

    assert "floor_brush_light" in switch_types


def test_setup_uses_fixture_payload(load_fixture):
    """The committed S5 Combo fixture must drive the same outcome as the log."""
    fx = load_fixture("s5_combo_no_led")

    switch_types = _setup_switch_types(fx["info"])

    assert "floor_brush_light" not in switch_types


# ---------------------------------------------------------------------------
# Entity behaviour for an entry set up before the capability was known
# ---------------------------------------------------------------------------

def _make_brush_light(info):
    switch = TinecoFloorBrushLightSwitch(_make_entry(), _make_hass(info))
    return switch


def test_brush_light_available_until_proven_absent():
    """Freshly constructed with no data, the switch stays available."""
    switch = _make_brush_light(None)

    assert switch.available is True


def test_brush_light_goes_unavailable_when_led_absent():
    """An entity created during an API outage marks itself unavailable once a
    payload proves the model has no LED."""
    switch = _make_brush_light({"gci": S5_COMBO_GCI})

    asyncio.run(switch.async_update())

    assert switch.available is False


def test_brush_light_stays_available_and_tracks_state_when_led_present():
    switch = _make_brush_light({"gci": dict(S7_FLASHDRY_GCI, led=0)})

    asyncio.run(switch.async_update())

    assert switch.available is True
    assert switch.is_on is True  # led=0 means light ON (inverted)


def test_brush_light_reads_led_1_as_off():
    switch = _make_brush_light({"gci": dict(S7_FLASHDRY_GCI, led=1)})

    asyncio.run(switch.async_update())

    assert switch.available is True
    assert switch.is_on is False


def test_brush_light_unknown_capability_does_not_flip_unavailable():
    """A refresh that returned no ``gci`` leaves availability untouched."""
    switch = _make_brush_light({"cfp": {"wm": 2}})

    asyncio.run(switch.async_update())

    assert switch.available is True


def test_brush_light_command_is_suppressed_when_unsupported():
    """Turning on an unsupported switch must not reach the API — the cloud
    replies success regardless, which is what made #33 look like it worked."""
    switch = _make_brush_light({"gci": S5_COMBO_GCI})
    sent = []

    async def _record(on: bool):
        sent.append(on)

    switch._send_command = _record
    switch.async_write_ha_state = lambda: None

    asyncio.run(switch.async_turn_on())
    asyncio.run(switch.async_turn_off())

    assert sent == []
    # The optimistic state must not latch on either — reporting "on" for a
    # light that doesn't exist is the bug we're fixing.
    assert switch.is_on is False


def test_brush_light_command_is_sent_when_supported():
    """The guard must not break the models that do have the light."""
    switch = _make_brush_light({"gci": S7_FLASHDRY_GCI})
    sent = []

    async def _record(on: bool):
        sent.append(on)

    switch._send_command = _record
    switch.async_write_ha_state = lambda: None

    asyncio.run(switch.async_turn_on())

    assert sent == [True]
    assert switch.is_on is True


def test_brush_light_command_is_sent_when_capability_unknown():
    """No ``gci`` to judge by → still send, don't strand a working control."""
    switch = _make_brush_light(None)
    sent = []

    async def _record(on: bool):
        sent.append(on)

    switch._send_command = _record
    switch.async_write_ha_state = lambda: None

    asyncio.run(switch.async_turn_on())

    assert sent == [True]
