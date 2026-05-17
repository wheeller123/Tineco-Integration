"""Integration setup tests — verify all platforms forward and entities are registered.

Catches the silent-orphan class of regression: if ``PLATFORMS`` ever loses
``sensor`` or any platform stops registering its entities, this test fails
before the release. Mirrors a ``MockConfigEntry`` through ``async_setup_entry``.

Skipped on Windows where the HA runner's ``fcntl`` import blocks the test
plugin.
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


@pytest.fixture
def mock_tineco_device_client():
    """Patch the wrapper used by async_setup_entry to avoid live API calls."""
    with patch("custom_components.tineco.client.TinecoDeviceClient") as mock_cls:
        instance = mock_cls.return_value
        instance.async_login = AsyncMock(return_value=True)
        instance.async_get_devices = AsyncMock(return_value=[{
            "did": "test-device-id",
            "className": "9uened",
            "resource": "T033",
            "nick": "Test Device",
            "productType": "S7 Flashdry",
            "name": "0000000abcdef",
        }])
        instance.async_get_device_info = AsyncMock(return_value={
            "gci": {"wm": 2, "bp": 80, "led": 0, "vl": 1, "e1": 0, "e2": 0},
            "gav": {"vv": "1.0.5", "av": "v3"},
            "gcf": {},
            "cfp": {"wm": 2},
            "query_mode": {"cfg": []},
        })
        instance.devices = [{
            "did": "test-device-id",
            "className": "9uened",
            "resource": "T033",
            "nick": "Test Device",
            "productType": "S7 Flashdry",
            "name": "0000000abcdef",
        }]
        instance._initialized = True
        yield instance


@pytest.mark.asyncio
async def test_setup_entry_loads_all_platforms(hass: HomeAssistant, mock_tineco_device_client):
    """async_setup_entry must return True and forward all four platforms."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "email": "setup@example.com",
            "password": "pw",
            "device_id": "dev-1",
            "region": "IE",
        },
        unique_id="setup@example.com",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id) is True
    await hass.async_block_till_done()

    # All four platforms should have at least one entity registered.
    from homeassistant.helpers import entity_registry as er
    registry = er.async_get(hass)
    entities = [e for e in registry.entities.values() if e.config_entry_id == entry.entry_id]

    domains = {e.domain for e in entities}
    assert "sensor" in domains, "sensor platform did not register any entities"
    assert "switch" in domains, "switch platform did not register any entities"
    assert "binary_sensor" in domains, "binary_sensor platform did not register any entities"
    assert "select" in domains, "select platform did not register any entities"


@pytest.mark.asyncio
async def test_setup_entry_handles_login_failure_gracefully(hass: HomeAssistant):
    """If login fails at setup time we still return True so HA shows the entry
    as 'not ready' rather than crashing; the coordinator retries on next tick."""
    with patch("custom_components.tineco.client.TinecoDeviceClient") as mock_cls:
        instance = mock_cls.return_value
        instance.async_login = AsyncMock(return_value=False)
        instance.async_get_devices = AsyncMock(return_value=None)
        instance.devices = []
        instance._initialized = False

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "email": "fail@example.com",
                "password": "wrong",
                "device_id": "dev-1",
                "region": "IE",
            },
            unique_id="fail@example.com",
        )
        entry.add_to_hass(hass)

        # Should not raise — the integration logs a warning and continues.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
