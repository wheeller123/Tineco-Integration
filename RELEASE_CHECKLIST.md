# Release checklist

Five steps. Skip none.

## 1. Tests pass

```
pytest tests/ -v
```

Green locally **and** on CI for the tag's commit. `.github/workflows/tests.yml`
gates the PR — don't merge red.

## 2. CHANGELOG up to date

`CHANGELOG.md`'s `## [Unreleased]` section must contain every notable change
since the previous release. On release day, rename the heading to
`## [vX.Y.Z] - YYYY-MM-DD` and bump the link references at the bottom.

## 3. Manifest version matches the tag

```
grep '"version"' custom_components/tineco/manifest.json
```

Whatever's there is what the tag must be. `.github/workflows/release.yml`
will reject a mismatch.

## 4. Pre-release flow for risky changes

If the PR touches **either**:

- `custom_components/tineco/sensor.py` — `_update_state_from_data` priority
  chains, **or**
- `custom_components/tineco/tineco_client_impl.py` — URL construction, `org`,
  region/timezone/language maps

Then tag as `vX.Y.Z-rc1` first, mark the GitHub release as **pre-release**,
and wait at least 48 hours for one community confirmation before promoting
to plain `vX.Y.Z`.

HACS only offers `-rc` / `-beta` / `-alpha` tags to users who toggle "Show
beta versions" per integration, so this naturally gates the change behind
opt-in testers (`wlchapple` for CN, maintainer for IE).

## 5. Smoke checks against the real vacuum + your test HA

Two complementary smoke scripts, run in this order:

```
# A. Drive the vacuum through known states, verify decoding matches.
python scripts/smoke_vacuum_state.py --region IE

# B. Deploy to the test HA instance, then verify all entities are sane.
./deploy-to-homeassistant.ps1
export HA_URL=http://192.168.0.160:8123
export HA_TOKEN=<long-lived token from HA → profile → security>
python scripts/smoke_ha_api.py
```

Both must report `All checks passed` / `All HA smoke checks passed`. If
either fails, capture the failing API payload with
`python test_tineco_data.py --dump tests/fixtures/<name>.json`, add a
matching unit test, fix the underlying issue, and retry from step 1.

## When a new device model gets reported in issues

Before closing the issue:

1. Ask the reporter to run `python test_tineco_data.py --dump <name>.json`.
2. Review the JSON; manually scrub any PII the automatic scrub missed.
3. Commit it as `tests/fixtures/<name>.json`.
4. Add a one-line assertion to `tests/test_sensors_parametrized.py` so
   the next regression on that device shape is caught.
