# Tineco integration tests

These tests guard against regressions in field-priority logic, region-specific
URL/`org` construction, entity unique-id stability, and the HA config-flow /
setup-entry surface.

## Running

```
pip install pytest pytest-asyncio pytest-homeassistant-custom-component
pytest tests/ -v
```

The same command is what CI runs (`.github/workflows/tests.yml`).

## Adding a fixture for a new device

The fastest path is the `--dump` flag on the existing manual capture script:

```
python test_tineco_data.py --dump tests/fixtures/<device>.json
```

That writes `{"devices": [...], "info": {...}}` straight into the fixtures
directory with PII scrubbed (account, email, mobile, tokens, did, mid,
tuyaId). Verify the JSON looks right, then add a corresponding assertion to
`tests/test_sensors.py` and (optionally) `tests/test_sensors_parametrized.py`.

See `tests/fixtures/_schema.md` for the expected shape.
