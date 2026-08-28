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
- Floor Brush Light switch appearing on models that have no floor brush light,
  where it reported success and changed nothing (#33, Floor One S5 Combo). The
  `led` field is absent from these devices' `gci` payload, but the cloud API
  accepts `{'led': 0}` and answers with a normal success response, so neither
  the command nor the state read could tell the switch was a no-op.
  - `switch.async_setup_entry` now checks the coordinator's first `gci` payload
    and skips `TinecoFloorBrushLightSwitch` when `led` is absent. Only `gci` is
    consulted — `cfp` omits `led` even on models that do have the light, so its
    absence there proves nothing.
  - Absence of a `gci` payload (failed first refresh, timed-out endpoint) counts
    as *unknown*, not unsupported, so a transient API failure can't drop the
    switch for a device that does have the light. Such an entity marks itself
    unavailable and refuses commands as soon as a payload settles the question.
  - An entity left in the registry by an earlier version is removed on setup, so
    affected users don't keep a permanently unavailable switch.
- Added `tests/fixtures/s5_combo_no_led.json` (captured from the #33 debug log)
  and `tests/test_switch_capabilities.py`. Confirms the Floor One S5 Combo as a
  working model apart from the brush light.

### Added
- Floor One S5 Combo listed as a confirmed model. Battery, vacuum status, water
  tank tracking and all mode/power/suction selects were verified working by the
  reporter of #33.

## [v2.4.3] - 2026-07-29

### Fixed
- Blocking calls in the Home Assistant event loop during startup (reported as
  `Detected blocking call to load_verify_locations ... tineco_client_impl.py,
  line 134`). `TinecoClient.__init__` resolved the IoT datacenter with a
  synchronous `requests` GET, and the constructor was invoked on the event loop
  from `async_setup_entry` → `async_login`, from `TinecoConfigFlow.__init__`,
  and from the `switch`/`select` client-fallback paths.
  - The datacenter lookup is now lazy: `IOT_API_BASE` / `IOT_LOGIN_ENDPOINT`
    are properties resolving `dc` on first read (cached, thread-safe), and
    `login()` warms it while already in an executor. Construction does no I/O.
  - `TinecoDeviceClient` takes `hass` and dispatches every blocking call via
    `hass.async_add_executor_job`, replacing the deprecated
    `asyncio.get_event_loop().run_in_executor` (removed in favour of the HA
    helper; `get_event_loop` warns from Python 3.12).
  - `TinecoConfigFlow.__init__` no longer builds a throwaway client just to read
    a device ID — it reads the new `TinecoClient.DEFAULT_DEVICE_ID` constant
    (same value as before, so login signatures are unchanged). The real client
    is constructed inside the executor alongside `login()`.
  - The seven duplicated client-fallback blocks in `switch.py` / `select.py` are
    replaced by `client.async_get_or_create_client()`, which always passes
    `hass`, `device_id` and `region` (the fallbacks previously dropped the last
    two, silently logging in against the default device ID and region `IE`).

### Added
- Release guardrails encoding lessons from past releases:
  - `scripts/check_release_consistency.py` verifies manifest version is valid
    semver, `documentation`/`issue_tracker` URLs point at this repo, the README
    "Current version" matches, the CHANGELOG has the version's section, and
    (with `--tag`) the tag matches the manifest version.
  - `validate.yml` runs it on every push/PR (**Release Consistency** job).
  - `release.yml` runs it with `--tag` on publish and additionally verifies a
    stable release tag is an ancestor of `main` (pre-releases exempt).
  - `tests/test_release_consistency.py` exercises the guard logic and fails if
    the checked-in metadata drifts.

## [v2.4.2] - 2026-06-02

### Fixed
- `manifest.json` `documentation` and `issue_tracker` URLs (and the README
  links) pointed at the non-existent `Tineco-HACS-Integration` repo; corrected
  to `Tineco-Integration`. The HACS "Documentation" / "Issues" buttons now
  resolve.

### Changed
- GitHub Actions upgraded off the deprecated Node 20 runtime:
  `actions/checkout` v3/v4 → v5, `actions/setup-python` v5 → v6.

## [v2.4.1] - 2026-06-02

### Fixed
- **Water tank statuses (waste/dirty and fresh/clean) not tracking
  empty/full** (#29, S7 Flashdry). Determined empirically from captured
  full↔empty transitions: `e2` is a **bitmask** of tank conditions —
  `e2 & 64` = fresh/clean tank empty, `e2 & 256` = waste/dirty tank full —
  while `e1`/`e3` stay 0 on this firmware. The fresh tank also corroborates
  via the `wp` level reading flipping from 238 (has water) to 239 (empty);
  `wp=238` is the *has-water* value, not an empty sentinel. The sensors now:
    - waste/dirty: `full` on `e2 & 256` (or `e3` bit-12 warning code 44, or
      legacy `e1 > 0`), else `clean`.
    - fresh/clean: `empty` on `e2 & 64` (or `e3` bit-13 warning code 45, or
      `wp` in {239, 240}), else `full`.
  Both sensors check every available signal before concluding the
  not-triggered state (a prior short-circuit on `e3` hid the real `e2`
  signal), and the two `e2` bits are independent so they never cross-trigger.
  The `e3`/`e1` paths remain for firmware that reports tank state that way.
  (An earlier pre-release wrongly treated `wp` 238/239/240 as "empty" and got
  stuck reporting empty; corrected here.)
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
