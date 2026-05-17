# Fixture schema

Each `.json` file in this directory captures one device's state as returned
by the Tineco API. The shape is:

```json
{
  "devices": [
    { "did": "<scrubbed>", "nick": "...", "productType": "...", "name": "...", ...}
  ],
  "info": {
    "gci":        { ... },
    "gav":        { ... },
    "gcf":        { ... },
    "cfp":        { ... },
    "query_mode": { ... }
  }
}
```

- `devices` — what `TinecoDeviceClient.devices` exposes (a list of device dicts
  from the `getDeviceListV2` endpoint).
- `info` — what `get_complete_device_info()` returns (per-endpoint payloads
  keyed by lowercased endpoint name).

## PII to scrub before committing

Strip or replace these values with placeholders:

- `did`, `didIos` — device IDs (replace with a UUID literal)
- `mid`, `tuyaId` — internal IDs
- `account`, `email`, `mobile` — anywhere they appear
- `token`, `accessToken`, `authCode`, `iotToken` — credentials
- `uid`, `ucUid`, `userId` — user IDs

`test_tineco_data.py --dump <path>` does this automatically.
