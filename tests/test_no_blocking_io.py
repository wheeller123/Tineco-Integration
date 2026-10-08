"""Regression locks for Home Assistant event-loop blocking calls.

Home Assistant flags synchronous socket I/O performed on the event loop:

    Detected blocking call to load_verify_locations / putrequest inside the
    event loop by custom integration 'tineco' at
    custom_components/tineco/tineco_client_impl.py, line 134

The cause was ``TinecoClient.__init__`` calling ``_resolve_iot_datacenter()``
(a blocking ``requests`` GET) while being constructed on the loop from
``async_setup_entry`` → ``TinecoDeviceClient.async_login``.

These tests assert the two invariants that keep it fixed:

1. Constructing a ``TinecoClient`` performs no HTTP at all.
2. Every ``TinecoDeviceClient`` coroutine dispatches its blocking work to a
   thread — nothing touches ``requests`` from the loop thread.

They run without ``pytest-homeassistant-custom-component`` (a minimal fake
``hass`` supplies ``async_add_executor_job``) so they also execute on Windows,
where the HA test runner can't load.
"""
from __future__ import annotations

import asyncio
import threading
from unittest.mock import patch

import pytest

from custom_components.tineco import tineco_client_impl as impl
from custom_components.tineco.client import TinecoDeviceClient
from custom_components.tineco.tineco_client_impl import TinecoClient


class FakeHass:
    """Minimal stand-in exposing only ``async_add_executor_job``."""

    def async_add_executor_job(self, func, *args):
        return asyncio.get_running_loop().run_in_executor(None, func, *args)


@pytest.fixture
def loop_guard():
    """Patch ``requests.Session`` verbs to fail if called on the loop thread.

    Returns the thread that must stay I/O-free. Off-thread calls raise a
    benign ``Exception`` so the client's own error handling takes over.
    """
    loop_thread = threading.current_thread()

    def guard(*args, **kwargs):
        if threading.current_thread() is loop_thread:
            raise AssertionError("blocking HTTP call made on the event loop thread")
        raise Exception("offline test — network blocked")

    with patch.object(impl.requests.Session, "get", side_effect=guard), \
         patch.object(impl.requests.Session, "post", side_effect=guard):
        yield loop_thread


def test_client_construction_does_no_http():
    """``TinecoClient()`` must be pure — the DC lookup is deferred."""
    with patch.object(impl.requests.Session, "get") as get:
        get.side_effect = AssertionError("DC lookup must not run in __init__")
        client = TinecoClient(device_id="d" * 32, region="IE")

    assert get.call_count == 0
    assert client._dc is None


def test_login_resolves_datacenter_off_the_loop(loop_guard):
    """async_login constructs the impl client and resolves the DC in a thread."""
    async def run():
        client = TinecoDeviceClient("u@e.com", "pw", "d" * 32, "IE", hass=FakeHass())
        # Login fails because the network is blocked; what matters is *where*
        # the attempt happened.
        assert await client.async_login() is False
        assert client.client is not None, "impl client was never constructed"
        # The DC lookup ran and fell back statically — off the loop thread.
        assert client.client._dc == "eu"

    asyncio.run(run())


def test_all_adapter_calls_dispatch_to_executor(loop_guard):
    """Every adapter coroutine must run its blocking call in a thread.

    Guards against a future method being added with a direct (unwrapped) call.
    """
    async def run():
        client = TinecoDeviceClient("u@e.com", "pw", "d" * 32, "IE", hass=FakeHass())
        await client.async_login()
        # async_login returned False, so force the initialized flag on to let
        # the remaining methods past their guard clause.
        client._initialized = True

        # Each returns None because the network is blocked; an AssertionError
        # from the guard would mean the call ran on the loop.
        assert await client.async_get_devices() is None
        assert await client.async_get_device_info("dev", "cls", "res") is None
        assert await client.async_get_controller_info("dev", "cls", "res") is None
        assert await client.async_get_api_version("dev", "cls", "res") is None
        assert await client.async_get_config_file("dev", "cls", "res") is None
        assert await client.async_query_device_mode("dev", "cls", "res") is None
        assert await client.async_control_device("dev", {"wm": 1}, "sn", "cls") is None

    asyncio.run(run())


def test_adapter_works_without_hass():
    """The ``scripts/`` entrypoints construct the adapter with no ``hass``;
    it must still offload rather than raising."""
    loop_thread = threading.current_thread()
    seen: list[threading.Thread] = []

    def record(*args, **kwargs):
        seen.append(threading.current_thread())
        raise Exception("offline test — network blocked")

    async def run():
        with patch.object(impl.requests.Session, "get", side_effect=record):
            client = TinecoDeviceClient("u@e.com", "pw", "d" * 32, "IE")
            assert client.hass is None
            await client.async_login()

    asyncio.run(run())

    assert seen, "no HTTP attempt was made"
    assert all(t is not loop_thread for t in seen), "ran on the loop thread"


def test_config_flow_init_does_no_http():
    """``TinecoConfigFlow.__init__`` used to build a throwaway TinecoClient
    purely to read a device ID, firing a DC lookup on the loop every time the
    flow was opened. It must now read the class constant instead."""
    pytest.importorskip("homeassistant")
    from custom_components.tineco.config_flow import TinecoConfigFlow

    with patch.object(impl.requests.Session, "get") as get:
        get.side_effect = AssertionError("config flow init must not do HTTP")
        flow = TinecoConfigFlow()

    assert get.call_count == 0
    assert flow._device_id == TinecoClient.DEFAULT_DEVICE_ID
    # The value is part of the login signature — changing it re-triggers
    # new-device verification for every existing user.
    assert flow._device_id == "57938f751acc6897088c718770edcd00"
