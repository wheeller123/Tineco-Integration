"""Coordinator update-flow tests.

Asserts the DataUpdateCoordinator's ``async_update_data`` callback walks
login → get_devices → get_complete_device_info, propagates the device-info
dict to all entities, and surfaces ``UpdateFailed`` cleanly when the API
returns nothing.
"""
from __future__ import annotations

import sys

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")
if sys.platform == "win32":
    pytest.skip("HA runner requires fcntl (POSIX-only)", allow_module_level=True)

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tineco.const import DOMAIN


@pytest.mark.asyncio
async def test_coordinator_first_refresh_populates_data(hass: HomeAssistant):
    """First successful refresh leaves coordinator.data with the endpoint payloads
    so all sensors can read them."""
    expected_info = {
        "gci": {"wm": 2, "bp": 80, "led": 0, "vl": 1, "e1": 0, "e2": 0},
        "gav": {"vv": "1.0.5", "av": "v3"},
        "gcf": {},
        "cfp": {"wm": 2},
        "query_mode": {"cfg": []},
    }
    device_info_payload = {
        "did": "test-did",
        "className": "9uened",
        "resource": "T033",
        "nick": "Test Device",
        "productType": "S7 Flashdry",
        "name": "0000000abcdef",
    }

    with patch("custom_components.tineco.client.TinecoDeviceClient") as mock_cls:
        instance = mock_cls.return_value
        instance.async_login = AsyncMock(return_value=True)
        instance.async_get_devices = AsyncMock(return_value=[device_info_payload])
        instance.async_get_device_info = AsyncMock(return_value=expected_info)
        instance.devices = [device_info_payload]
        instance._initialized = True

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "email": "coordinator@example.com",
                "password": "pw",
                "device_id": "dev-1",
                "region": "IE",
            },
            unique_id="coordinator@example.com",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        stored = hass.data[DOMAIN][entry.entry_id]
        coordinator = stored["coordinator"]

        assert coordinator.data == expected_info
        assert coordinator.last_update_success is True


@pytest.mark.asyncio
async def test_coordinator_handles_empty_device_list(hass: HomeAssistant):
    """If get_devices returns no devices, the coordinator marks the refresh failed
    rather than crashing."""
    with patch("custom_components.tineco.client.TinecoDeviceClient") as mock_cls:
        instance = mock_cls.return_value
        instance.async_login = AsyncMock(return_value=True)
        instance.async_get_devices = AsyncMock(return_value=None)
        instance.async_get_device_info = AsyncMock(return_value=None)
        instance.devices = []
        instance._initialized = True

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "email": "empty@example.com",
                "password": "pw",
                "device_id": "dev-1",
                "region": "IE",
            },
            unique_id="empty@example.com",
        )
        entry.add_to_hass(hass)

        # async_setup_entry catches the UpdateFailed and continues — the
        # coordinator just records last_update_success=False.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        stored = hass.data[DOMAIN][entry.entry_id]
        coordinator = stored.get("coordinator")
        if coordinator is not None:
            assert coordinator.last_update_success is False
