#!/usr/bin/env python3
"""Print the CHANGELOG section for a release, for use as GitHub release notes.

HACS shows the GitHub release body in Home Assistant's update dialog, so the
release workflow publishes this section there. That is how users see breaking
changes before they update.

    python scripts/release_notes.py v2.5.0 > release_notes.md

Pre-release suffixes (-rc1/-beta1/-alpha1) are stripped, so v2.5.0-rc1 uses
the v2.5.0 section. Exits 1 if the section is missing or empty.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def changelog_section(version: str, text: str | None = None) -> str:
    """Return the body of the ``## [vX.Y.Z]`` section (without its heading)."""
    version = version.removeprefix("v").split("-", 1)[0]
    text = CHANGELOG.read_text(encoding="utf-8") if text is None else text
    heading = re.compile(rf"^## \[v?{re.escape(version)}\].*$", re.MULTILINE)
    match = heading.search(text)
    if not match:
        return ""
    rest = text[match.end():]
    nxt = re.search(r"^## \[", rest, re.MULTILINE)
    return (rest[: nxt.start()] if nxt else rest).strip()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    notes = changelog_section(sys.argv[1])
    if not notes:
        print(f"CHANGELOG has no non-empty section for {sys.argv[1]}", file=sys.stderr)
        return 1
    sys.stdout.reconfigure(encoding="utf-8")
    print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
