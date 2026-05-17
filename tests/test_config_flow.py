"""Config flow tests — exercise async_step_user with TinecoClient mocked.

These tests depend on ``pytest-homeassistant-custom-component``'s ``hass``
fixture, which can't load on Windows (HA's runner imports ``fcntl``). They
run on CI's Ubuntu runners; locally they're skipped via
``pytest.importorskip``.
"""
from __future__ import annotations

import sys

import pytest

# Skip the whole module if the HA test plugin can't load (e.g. on Windows
# where `homeassistant.runner` requires the POSIX-only ``fcntl`` module).
pytest.importorskip("pytest_homeassistant_custom_component")
if sys.platform == "win32":
    pytest.skip("HA runner requires fcntl (POSIX-only)", allow_module_level=True)

from unittest.mock import patch

from homeassistant import data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.tineco.const import DOMAIN


@pytest.mark.asyncio
async def test_invalid_credentials_show_invalid_auth_error(hass: HomeAssistant):
    """A failed login surfaces as ``errors['base'] == 'invalid_auth'`` so the
    user sees the right message in the config-flow UI."""
    with patch(
        "custom_components.tineco.config_flow.TinecoClient"
    ) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.login.return_value = (False, None, None)
        mock_client.DEVICE_ID = "test_device_id"

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        # First step shows the form.
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                "email": "test@example.com",
                "password": "wrong-password",
                "region": "IE",
            },
        )

        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_successful_login_creates_entry(hass: HomeAssistant):
    """Happy path creates a config entry with the supplied credentials and region."""
    with patch(
        "custom_components.tineco.config_flow.TinecoClient"
    ) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.login.return_value = (True, "access-token", "uid-1234")
        mock_client.DEVICE_ID = "device-abc"

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                "email": "good@example.com",
                "password": "right-password",
                "region": "IE",
            },
        )

        assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
        assert result["title"] == "good@example.com"
        assert result["data"]["region"] == "IE"
        assert result["data"]["email"] == "good@example.com"


@pytest.mark.asyncio
async def test_new_device_routes_to_otp_step(hass: HomeAssistant):
    """When login raises ``TinecoNewDeviceException``, the flow advances to the OTP step."""
    from custom_components.tineco.tineco_client_impl import TinecoNewDeviceException

    with patch(
        "custom_components.tineco.config_flow.TinecoClient"
    ) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.login.side_effect = TinecoNewDeviceException(verify_id="verify-xyz")
        mock_client.DEVICE_ID = "device-abc"

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                "email": "newdevice@example.com",
                "password": "password",
                "region": "CN",
            },
        )

        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "otp"
