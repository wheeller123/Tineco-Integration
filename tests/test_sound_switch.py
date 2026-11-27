"""Sound switch state tests.

The switch mutes with ``{'ms': 1}`` and unmutes with ``{'ms': 0}``. The device
reports the result in ``msr`` (1 = muted, 0 = sound on), in both ``gci`` and
``cfp``. The old code read the state from ``vl`` instead, which is the volume
level and never changes on mute, so the next poll always flipped the switch
back to "on" even though the device stayed muted.

Payloads below are from a Floor One S9 Artist Premium (CL2343c-04), captured
before and after the mute commands.
"""
from __future__ import annotations

import asyncio
import types

import pytest

from custom_components.tineco.const import DOMAIN
from custom_components.tineco.switch import TinecoAudioSwitch, sound_enabled

ENTRY_ID = "sound-test"

S9_GCI_MUTED = {
    "selfclean_mode": 0, "selfclean_process": 1, "selfclean_progress": 0,
    "selfclean_duration": 0, "selectmode": 0, "wheel": 2, "lywheel": 1,
    "upright": 1, "cleanway": 1, "msr": 1, "vl": 1, "wp": 238, "wm": 2,
    "dv": 0, "bp": 240, "vs": 4, "e1": 0, "e2": 0, "e3": 0, "attitude": 1,
}
S9_CFP_MUTED = {
    "cleanway": 1, "lywheel": 1, "upright": 1, "msr": 1, "vl": 1, "wp": 238,
    "wm": 2, "bp": 240, "dv": 0, "vs": 4, "e1": 0, "e2": 0, "e3": 0,
}
S9_GCI_SOUND_ON = {**S9_GCI_MUTED, "msr": 0}
S9_CFP_SOUND_ON = {**S9_CFP_MUTED, "msr": 0}


# ---------------------------------------------------------------------------
# sound_enabled() — the pure state predicate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("info,expected", [
    ({"gci": S9_GCI_MUTED, "cfp": S9_CFP_MUTED}, False),       # muted, vl unchanged
    ({"gci": S9_GCI_SOUND_ON, "cfp": S9_CFP_SOUND_ON}, True),  # sound on
    ({"cfp": S9_CFP_MUTED}, False),                            # gci missing: cfp answers
    ({"gci": {"vl": 1}, "cfp": S9_CFP_MUTED}, False),          # gci without msr: cfp answers
    ({"gci": {"msr": 0, "vl": 4}}, True),                      # S5 Combo style vl=4
    ({"gci": {"vl": 1}}, None),                                # vl alone says nothing
    ({}, None),
    (None, None),
])
def test_sound_enabled(info, expected):
    assert sound_enabled(info) is expected


# ---------------------------------------------------------------------------
# TinecoAudioSwitch — state after polling
# ---------------------------------------------------------------------------

def _make_switch(info):
    coordinator = types.SimpleNamespace(data=info)
    hass = types.SimpleNamespace(data={DOMAIN: {ENTRY_ID: {"coordinator": coordinator}}})
    entry = types.SimpleNamespace(entry_id=ENTRY_ID, data={"email": "sound@example.com"})
    switch = TinecoAudioSwitch(entry, hass)
    switch.async_write_ha_state = lambda: None
    return switch, coordinator


def test_poll_reports_muted_device_as_off():
    switch, _ = _make_switch({"gci": S9_GCI_MUTED, "cfp": S9_CFP_MUTED})
    asyncio.run(switch.async_update())
    assert switch.is_on is False


def test_mute_survives_next_poll():
    """The regression: turn off, poll after the 5 s grace window, stay off."""
    switch, coordinator = _make_switch({"gci": S9_GCI_SOUND_ON, "cfp": S9_CFP_SOUND_ON})
    asyncio.run(switch.async_update())
    assert switch.is_on is True

    sent = []

    async def _fake_send(on):
        sent.append(on)
        coordinator.data = {"gci": S9_GCI_MUTED, "cfp": S9_CFP_MUTED}

    switch._send_command = _fake_send
    asyncio.run(switch.async_turn_off())
    assert sent == [False]
    assert switch.is_on is False

    switch._last_command_time = None  # past the post-command grace window
    asyncio.run(switch.async_update())
    assert switch.is_on is False


def test_poll_without_msr_keeps_last_state():
    switch, coordinator = _make_switch({"gci": S9_GCI_MUTED})
    asyncio.run(switch.async_update())
    assert switch.is_on is False

    coordinator.data = {"gci": {"vl": 1}}
    asyncio.run(switch.async_update())
    assert switch.is_on is False
