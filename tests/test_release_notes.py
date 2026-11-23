"""Tests for scripts/release_notes.py (GitHub release body shown by HACS)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("release_notes", REPO_ROOT / "scripts" / "release_notes.py")
rn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rn)

SAMPLE = """# Changelog

## [Unreleased]

## [v2.5.0] - 2026-11-23

### Breaking changes
- values changed

## [v2.4.3] - 2026-07-29

### Fixed
- older fix
"""


def test_extracts_only_the_requested_section():
    notes = rn.changelog_section("v2.5.0", SAMPLE)
    assert notes.startswith("### Breaking changes")
    assert "older fix" not in notes


def test_prerelease_tag_uses_stable_section():
    assert rn.changelog_section("v2.5.0-rc1", SAMPLE) == rn.changelog_section("2.5.0", SAMPLE)


def test_missing_section_is_empty():
    assert rn.changelog_section("v9.9.9", SAMPLE) == ""


def test_current_release_notes_include_breaking_changes():
    """The release HACS shows for the current manifest version must list the
    #40 breaking change so users see it before updating."""
    manifest = REPO_ROOT / "custom_components" / "tineco" / "manifest.json"
    version = json.loads(manifest.read_text(encoding="utf-8"))["version"]
    notes = rn.changelog_section(version)
    if version == "2.5.0":
        assert "### Breaking changes" in notes
        assert "`rinse`" in notes and "`Rinse`" in notes
    assert notes, f"CHANGELOG has no notes for {version}"
