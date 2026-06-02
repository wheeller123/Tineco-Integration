# Changelog

All notable changes to this project are documented in this file.

Two rules for contributors:

1. **Every PR that touches** `custom_components/tineco/sensor.py`
   `_update_state_from_data` priority chains **or**
   `custom_components/tineco/tineco_client_impl.py` URL construction / `org`
   / region maps adds an entry under `## [Unreleased]`.
2. **Every release** moves all `## [Unreleased]` entries under a new
   `## [vX.Y.Z]` heading on the day of the tag.

## [Unreleased]

### Fixed
- **Fresh (clean) water tank status not tracking empty/full correctly**
  (S7 Flashdry). Determined empirically from a captured full→empty transition:
  water present reports `wp=238, e2=0`; empty / "insufficient water" reports
  `wp=239, e2=64`. The definitive empty signal is the `e2` bit 64, corroborated
  by `wp` flipping 238→239. The sensor now reports `empty` on `e2 & 64`
  (or the `e3` bit-13 warning, or `wp` in {239, 240}) and `full` otherwise.
  Note: `wp=238` is the *has-water* value — a brief earlier pre-release
  (rc2) wrongly treated 238/239/240 as "empty" and so got stuck reporting
  empty; that is corrected here.
- **Waste (dirty) water tank status always showing "Clean"** (#29). The sensor
  keyed off the `e1` field, but the dirty-water-tank-full warning (app code 44)
  is actually bit 12 of the `e3` bitmask (`e3 & 4096`). Decoded from the Tineco
  Android app (`FloorFourDeviceFragment.setErrorStatus`). The fresh water tank
  sensor was corrected the same way: empty (code 45) is bit 13 of `e3`
  (`e3 & 8192`). The old `e1`/`e2` checks remain as a fallback for firmware that
  doesn't report `e3`.
- **Online binary sensor reported "on" at startup then flipped "off" regardless
  of actual state**, with repeated `Update of binary_sensor...online is taking
  over 10 seconds` warnings. The online/charging binary sensors no longer issue
  their own independent IoT queries; they now derive state from the shared
  `DataUpdateCoordinator` (online = the last refresh succeeded). This removes the
  duplicate per-entity API calls and the false state flip.
- **`gcf` (Get Config File) read timeouts spamming the log every refresh** as
  `ERROR ... Read timed out. (read timeout=10)`. This upstream endpoint is
  intermittently unresponsive; it is now best-effort with a shorter (4s) timeout,
  and a per-action timeout is logged once as a `WARNING` instead of an `ERROR`
  every cycle. Core state comes from `gci`/`QueryMode`, so a `gcf` timeout no
  longer slows or fails the refresh. (#29)

### Added
- Pytest unit-test suite under `tests/` covering sensor field-priority logic,
  region/URL construction, entity unique-id stability, and the HA config-flow
  / setup-entry / coordinator surface.
- `scripts/smoke_vacuum_state.py` — interactive pre-release smoke test against
  a real Tineco vacuum.
- `scripts/smoke_ha_api.py` — post-deploy verification against a running HA
  instance via the REST API.
- `RELEASE_CHECKLIST.md` documenting the pre/post-release sequence and the
  `-rc` tag convention for risky changes.
- `--dump <path>` flag on `test_tineco_data.py` to generate fixtures with PII
  scrubbed.

### Changed
- `.github/workflows/tests.yml` no longer ignores test failures
  (`continue-on-error` removed). Failing tests now gate PRs.
- `.github/workflows/release.yml` accepts pre-release tags
  (`vX.Y.Z-rc<N>` / `-beta<N>` / `-alpha<N>`) by stripping the suffix before
  comparing against `manifest.version`.

## [v2.2.13] - 2026-05-17

### Fixed
- CN-region IoT login now sends `org=TEK` instead of `TEKWW`. Resolves the
  IoT login `errno=1202 invalid org` error reported on v2.2.12. (#22)

## [v2.2.12] - 2026-05-16

### Fixed
- Tineco model sensor now prefers `productType` over `nick`. Stops showing
  `Floor One-1580` (Tineco's default nickname for the S7 Flashdry) and
  shows the canonical model name `S7 Flashdry` instead.

## [v2.2.11] - 2026-05-16

### Added
- Diagnostic debug log in the model sensor that dumps every candidate field
  on `client.devices[0]` so a future "wrong model" report can be triaged
  from one log line.

## [v2.2.10] - 2026-05-16

### Fixed
- CN-region REST login now hits `qas-gl-cn-appapi.tineco.com` instead of
  `qas-gl-cn-api.tineco.com`. The China app uses a distinct `-appapi`
  host suffix that we previously didn't replicate, causing CN accounts to
  fail authentication with `code 1010 invalid credentials`. (#22)

## [v2.2.8] - 2026-05-16

### Added
- `REGION_TIMEZONE_MAP` entries for CN (`Asia/Shanghai`), HK, TW, JP, KR,
  SG, AU, GB.
- `REGION_LANGUAGE_MAP` providing default `lang` per region (CN→`ZH_CN`,
  TW→`ZH_TW`, etc.). Caller-supplied `language=` still wins.
- Redacted debug log of the signed REST login URL for easier triage.

[Unreleased]: https://github.com/wheeller123/Tineco-Integration/compare/v2.2.13...HEAD
[v2.2.13]: https://github.com/wheeller123/Tineco-Integration/releases/tag/v2.2.13
[v2.2.12]: https://github.com/wheeller123/Tineco-Integration/releases/tag/v2.2.12
[v2.2.11]: https://github.com/wheeller123/Tineco-Integration/releases/tag/v2.2.11
[v2.2.10]: https://github.com/wheeller123/Tineco-Integration/releases/tag/v2.2.10
[v2.2.8]: https://github.com/wheeller123/Tineco-Integration/releases/tag/v2.2.8
