#!/usr/bin/env python3
"""
Standalone MCP settings validator.

Checks settings JSON files for @latest in MCP server args.
Exits non-zero if any violations are found — suitable for CI and git hooks.

Usage:
    python3 hooks/validate-mcp.py                         # scan ~/.claude/ and .claude/
    python3 hooks/validate-mcp.py path/to/settings.json   # scan specific file(s)
    python3 hooks/validate-mcp.py --staged                 # scan git-staged settings files only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SETTINGS_GLOBS = [
    Path.home() / ".claude" / "settings.json",
    Path(".claude") / "settings.json",
    Path(".claude") / "settings.local.json",
]


def get_staged_settings_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=True,
        )
        return [
            Path(f)
            for f in result.stdout.splitlines()
            if f.endswith(".json") and "settings" in Path(f).name and Path(f).exists()
        ]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def check_file(path: Path) -> list[str]:
    """Return a list of violation messages for the given settings file."""
    violations: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return violations  # not valid JSON or unreadable — skip

    mcp_servers = data.get("mcpServers", {})
    if not isinstance(mcp_servers, dict):
        return violations

    for server_name, config in mcp_servers.items():
        if not isinstance(config, dict):
            continue
        for arg in config.get("args", []):
            if isinstance(arg, str) and arg.endswith("@latest"):
                violations.append(
                    f"  {path}  →  mcpServers.{server_name}.args: {arg!r}"
                )

    return violations


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Settings files to check (default: scan ~/.claude/ and .claude/)",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Check only git-staged settings files",
    )
    args = parser.parse_args()

    if args.staged:
        files = get_staged_settings_files()
        if not files:
            print("No staged settings files found.")
            sys.exit(0)
    elif args.files:
        files = [Path(f) for f in args.files]
    else:
        files = [f for f in SETTINGS_GLOBS if f.exists()]
        if not files:
            print("No settings files found in default locations.")
            sys.exit(0)

    all_violations: list[str] = []
    for path in files:
        all_violations.extend(check_file(path))

    if all_violations:
        print(f"FAIL  MCP version check — @latest is not allowed:\n")
        for v in all_violations:
            print(v)
        print(
            "\nPin each MCP server to an explicit version (e.g. @1.2.3).\n"
            "See docs/mcp.md for guidance."
        )
        sys.exit(1)

    checked = ", ".join(str(f) for f in files)
    print(f"OK    MCP version check passed ({len(files)} file(s): {checked})")
    sys.exit(0)


if __name__ == "__main__":
    main()
