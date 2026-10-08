"""Tineco API client adapter for Home Assistant integration."""

import asyncio
import logging
from typing import Optional, Dict, List
from .const import DOMAIN
from .tineco_client_impl import TinecoClient

_LOGGER = logging.getLogger(__name__)


async def async_get_or_create_client(hass, config_entry) -> Optional["TinecoDeviceClient"]:
    """Return the stored client for an entry, creating and logging in if absent.

    Entity handlers use this as a fallback when ``async_setup_entry`` hasn't
    stored a client yet. Returns ``None`` if login failed, in which case the
    caller should abort. Always passes ``hass`` so the blocking API calls run in
    an executor rather than on the event loop.
    """
    stored = hass.data.setdefault(DOMAIN, {}).setdefault(config_entry.entry_id, {})
    client = stored.get("client")
    if client is not None:
        return client

    client = TinecoDeviceClient(
        config_entry.data.get("email"),
        config_entry.data.get("password"),
        config_entry.data.get("device_id"),
        config_entry.data.get("region", "IE"),
        hass=hass,
    )
    stored["client"] = client
    if not await client.async_login():
        return None
    return client


class TinecoDeviceClient:
    """Adapter for Tineco IoT API client.

    Every method of the underlying :class:`TinecoClient` performs blocking
    ``requests`` I/O, so nothing here may run on the event loop. All calls are
    dispatched via ``hass.async_add_executor_job``.
    """

    def __init__(self, email: str, password: str, device_id: str = None, region: str = "IE", hass=None):
        """Initialize Tineco device client.

        ``hass`` is optional only so the standalone scripts in ``scripts/`` can
        reuse this adapter; inside the integration it is always supplied.
        """
        self.email = email
        self.password = password
        self.device_id = device_id
        self.region = region
        self.hass = hass
        self.client = None
        self.devices: List[Dict] = []
        self._initialized = False
        self._device_cache: Dict = {}

    async def _async_run(self, func, *args):
        """Run a blocking client call in an executor thread."""
        if self.hass is not None:
            return await self.hass.async_add_executor_job(func, *args)
        # No hass (script usage): use the running loop's default executor.
        return await asyncio.get_running_loop().run_in_executor(None, func, *args)

    async def async_login(self) -> bool:
        """Authenticate with Tineco API."""
        try:
            # TinecoClient construction is cheap, but its IoT datacenter lookup
            # is not — both the constructor and login() run in the executor so
            # no HTTP call can ever touch the event loop.
            self.client, success, token, user_id = await self._async_run(self._login)

            if success:
                _LOGGER.info(f"Successfully logged into Tineco API ({self.region}). UID: {user_id}")
                self._initialized = True
                return True
            else:
                _LOGGER.error("Failed to login to Tineco API - invalid credentials")
                return False
        except Exception as err:
            _LOGGER.error(f"Error during login: {err}", exc_info=True)
            return False

    def _login(self):
        """Construct the client and log in. Blocking — executor only."""
        client = self.client or TinecoClient(device_id=self.device_id, region=self.region)
        success, token, user_id = client.login(self.email, self.password, request_code=False)
        return client, success, token, user_id

    async def async_get_devices(self) -> Optional[List[Dict]]:
        if not self._initialized or not self.client:
            return None
        try:
            devices_response = await self._async_run(self.client.get_devices)
            if devices_response:
                self.devices = self.client.device_list
                return self.devices
            return None
        except Exception as err:
            _LOGGER.error(f"Error getting devices: {err}")
            return None

    async def async_get_device_info(self, device_id: str, device_class: str = "", device_resource: str = "") -> Optional[Dict]:
        if not self._initialized or not self.client:
            return None
        try:
            info = await self._async_run(
                self.client.get_complete_device_info, device_id, device_class, device_resource
            )
            return info if info else None
        except Exception as err:
            _LOGGER.error(f"Error getting device info: {err}")
            return None

    async def async_get_controller_info(self, device_id: str,
                                        device_class: str = "",
                                        device_resource: str = "") -> Optional[Dict]:
        """Get controller info (GCI)."""
        if not self._initialized or not self.client:
            return None

        try:
            return await self._async_run(
                self.client.get_controller_info, device_id, device_class, device_resource
            )
        except Exception as err:
            _LOGGER.error(f"Error getting controller info: {err}")
            return None

    async def async_get_api_version(self, device_id: str,
                                    device_class: str = "",
                                    device_resource: str = "") -> Optional[Dict]:
        """Get API version (GAV)."""
        if not self._initialized or not self.client:
            return None

        try:
            return await self._async_run(
                self.client.get_api_version, device_id, device_class, device_resource
            )
        except Exception as err:
            _LOGGER.error(f"Error getting API version: {err}")
            return None

    async def async_get_config_file(self, device_id: str,
                                    device_class: str = "",
                                    device_resource: str = "") -> Optional[Dict]:
        """Get config file (GCF)."""
        if not self._initialized or not self.client:
            return None

        try:
            return await self._async_run(
                self.client.get_config_file, device_id, device_class, device_resource
            )
        except Exception as err:
            _LOGGER.error(f"Error getting config file: {err}")
            return None

    async def async_query_device_mode(self, device_id: str,
                                      device_class: str = "",
                                      device_resource: str = "") -> Optional[Dict]:
        """Query device mode (QueryMode)."""
        if not self._initialized or not self.client:
            return None

        try:
            return await self._async_run(
                self.client.query_device_mode, device_id, device_class, device_resource
            )
        except Exception as err:
            _LOGGER.error(f"Error querying device mode: {err}")
            return None

    async def async_control_device(self, device_id: str,
                                   command: Dict,
                                   device_sn: str = "",
                                   device_class: str = "",
                                   action: str = "cfp") -> Optional[Dict]:
        """Send control command to device.

        Args:
            device_id: Device ID
            command: Command payload
            device_sn: Device serial number
            device_class: Device class
            action: API action (cfp, UpdateMode, DeleteMode, QueryMode)
        """
        if not self._initialized or not self.client:
            return None

        try:
            return await self._async_run(
                lambda: self.client.control_device(
                    device_id, command, device_sn, device_class, action=action
                )
            )
        except Exception as err:
            _LOGGER.error(f"Error sending device command: {err}")
            return None
