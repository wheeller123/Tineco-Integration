"""Shared pytest fixtures for the Tineco integration tests."""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

# Ensure repo root is importable so `from custom_components.tineco...` works.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# NOTE: there is no global ``enable_custom_integrations`` autouse here.
# That fixture transitively depends on the async ``hass`` fixture, so
# resolving it from a sync autouse via ``getfixturevalue`` returns an
# unawaited ``async_generator`` and the plugin then trips
# ``AttributeError: 'async_generator' object has no attribute 'data'``.
#
# Instead, each WS3 test module (test_config_flow.py, test_integration_setup.py,
# test_coordinator.py) declares its own module-level autouse fixture that
# takes ``enable_custom_integrations`` as a *declared dependency* —
# pytest then resolves the fixture chain in the right order inside an
# async event loop. WS1/WS2 unit tests don't import that fixture and
# remain pure-sync.


@pytest.fixture
def load_fixture():
    """Return a loader that reads tests/fixtures/<name>.json."""
    def _load(name: str) -> dict:
        path = FIXTURES_DIR / name
        if not path.suffix:
            path = path.with_suffix(".json")
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    return _load


@pytest.fixture
def all_fixture_paths():
    """Return every fixture JSON file (sorted, excluding _schema.md/README)."""
    return sorted(FIXTURES_DIR.glob("*.json"))


def make_sensor(cls, *, devices=None, email="user@example.com", entry_id="test_entry"):
    """Construct a Tineco sensor without invoking CoordinatorEntity.__init__.

    Real construction requires a live DataUpdateCoordinator; we only need to test
    the pure ``_update_state_from_data`` logic. ``__new__`` skips the parent
    chain and we populate the attributes the method touches.
    """
    from custom_components.tineco.const import DOMAIN  # local import — keeps HA off the import path

    sensor = cls.__new__(cls)
    sensor._state = None
    sensor.config_entry = types.SimpleNamespace(entry_id=entry_id, data={"email": email})
    fake_client = types.SimpleNamespace(devices=list(devices or []))
    sensor.hass = types.SimpleNamespace(
        data={DOMAIN: {entry_id: {"client": fake_client}}}
    )
    return sensor


@pytest.fixture
def make_sensor_factory():
    """Expose make_sensor() to tests as a fixture."""
    return make_sensor
