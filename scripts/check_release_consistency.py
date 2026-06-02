#!/usr/bin/env python3
"""Release-consistency guardrails for the Tineco HACS integration.

Encodes the lessons learned from past releases so they can't silently
regress. Run with no args for the static checks (safe anywhere):

    python scripts/check_release_consistency.py

On a tagged release, also pass the tag to cross-check it against the
manifest version:

    python scripts/check_release_consistency.py --tag v2.4.2

Checks performed:

1. manifest.json version is valid semver (X.Y.Z).
2. manifest.json documentation / issue_tracker URLs point at THIS repo
   (derived from the git remote, or $GITHUB_REPOSITORY in CI). Catches the
   Tineco-HACS-Integration -> Tineco-Integration broken-link regression.
3. README "Current version" line matches manifest.version.
4. CHANGELOG has a `## [vX.Y.Z]` section for manifest.version (i.e. the
   [Unreleased] entries were promoted on release).
5. With --tag: the tag's version (minus any -rc/-beta/-alpha suffix) equals
   manifest.version. Mirrors release.yml so a local check catches it first.

Exit code 0 = all good; 1 = one or more failures (each printed).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "custom_components" / "tineco" / "manifest.json"
README = REPO_ROOT / "README.md"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _fail(errors: list[str], msg: str) -> None:
    errors.append(msg)


def _expected_repo_slug() -> str | None:
    """Return 'owner/name' for this repo, from CI env or the git remote."""
    env = os.environ.get("GITHUB_REPOSITORY")
    if env:
        return env.strip()
    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=REPO_ROOT, text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    # git@github.com:owner/name.git  or  https://github.com/owner/name.git
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else None


def check_manifest_version(errors: list[str]) -> str:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    version = str(data.get("version", "")).strip()
    if not SEMVER_RE.match(version):
        _fail(errors, f"manifest version {version!r} is not valid semver (X.Y.Z)")
    return version


def check_manifest_urls(errors: list[str]) -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    slug = _expected_repo_slug()
    if not slug:
        print("  (skipping URL repo-match check: could not determine repo slug)")
        return
    expected = f"https://github.com/{slug}"
    for key in ("documentation", "issue_tracker"):
        url = str(data.get(key, ""))
        if not url.startswith(expected):
            _fail(
                errors,
                f"manifest '{key}' = {url!r} does not point at this repo "
                f"({expected}...). Update it so HACS links resolve.",
            )


def check_readme_version(errors: list[str], version: str) -> None:
    text = README.read_text(encoding="utf-8")
    m = re.search(r"Current version:\s*\*\*([0-9.]+)\*\*", text)
    if not m:
        _fail(errors, "README has no 'Current version: **X.Y.Z**' line")
    elif m.group(1) != version:
        _fail(
            errors,
            f"README 'Current version' = {m.group(1)} but manifest = {version}",
        )


def check_changelog(errors: list[str], version: str) -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    if f"## [v{version}]" not in text and f"## [{version}]" not in text:
        _fail(
            errors,
            f"CHANGELOG has no '## [v{version}]' section. Promote the "
            f"[Unreleased] entries to a v{version} heading on release.",
        )


def check_tag(errors: list[str], version: str, tag: str) -> None:
    raw = tag[1:] if tag.startswith("v") else tag
    tag_version = raw.split("-", 1)[0]  # strip -rc1 / -beta1 / -alpha1
    if tag_version != version:
        _fail(
            errors,
            f"tag {tag!r} -> version {tag_version} does not match manifest "
            f"version {version}",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="release tag to cross-check (e.g. v2.4.2)")
    args = parser.parse_args()

    errors: list[str] = []

    print("Checking release consistency...")
    version = check_manifest_version(errors)
    print(f"  manifest version: {version}")
    check_manifest_urls(errors)
    check_readme_version(errors, version)
    check_changelog(errors, version)
    if args.tag:
        print(f"  cross-checking tag: {args.tag}")
        check_tag(errors, version, args.tag)

    if errors:
        print("\nFAILED release-consistency checks:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\nAll release-consistency checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
