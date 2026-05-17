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
