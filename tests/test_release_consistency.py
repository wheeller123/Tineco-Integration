"""Tests for the release-consistency guardrails.

These run as part of the normal pytest suite so the guard logic itself
can't silently rot, and so a version/URL/CHANGELOG drift fails tests too
(not just the dedicated Release Consistency CI job).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_release_consistency.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_release_consistency", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


crc = _load_module()


def test_repo_is_currently_consistent():
    """The checked-in manifest/README/CHANGELOG must be self-consistent."""
    errors: list[str] = []
    version = crc.check_manifest_version(errors)
    crc.check_manifest_urls(errors)
    crc.check_readme_version(errors, version)
    crc.check_changelog(errors, version)
    assert errors == [], "Release consistency drift: " + "; ".join(errors)


def test_tag_check_strips_prerelease_suffixes():
    """v2.4.2 / v2.4.2-rc1 / v2.4.2-beta3 all match manifest 2.4.2."""
    for tag in ("v2.4.2", "v2.4.2-rc1", "v2.4.2-beta3", "2.4.2-alpha1"):
        errors: list[str] = []
        crc.check_tag(errors, "2.4.2", tag)
        assert errors == [], f"{tag} should match 2.4.2 but got {errors}"


def test_tag_check_rejects_mismatch():
    errors: list[str] = []
    crc.check_tag(errors, "2.4.2", "v9.9.9")
    assert errors, "mismatched tag should be rejected"


@pytest.mark.parametrize("url", [
    "https://github.com/owner/wrong-repo",
    "https://github.com/owner/Tineco-HACS-Integration",
])
def test_url_check_rejects_wrong_repo(url, monkeypatch, tmp_path):
    """A manifest URL pointing at a different repo must be flagged."""
    import json

    fake_manifest = tmp_path / "manifest.json"
    fake_manifest.write_text(json.dumps({
        "version": "2.4.2",
        "documentation": url,
        "issue_tracker": url + "/issues",
    }), encoding="utf-8")

    monkeypatch.setattr(crc, "MANIFEST", fake_manifest)
    monkeypatch.setattr(crc, "_expected_repo_slug", lambda: "owner/Tineco-Integration")

    errors: list[str] = []
    crc.check_manifest_urls(errors)
    assert errors, f"URL {url} should be rejected"
