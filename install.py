#!/usr/bin/env python3
"""
Installer for Claude Code security hooks.

Copies hook scripts to ~/.claude/hooks/ and wires them into
~/.claude/settings.json with absolute paths resolved at install time.

Usage:
    python3 install.py            # install
    python3 install.py --dry-run  # preview changes, write nothing
    python3 install.py --uninstall # remove hook entries added by this script
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT     = Path(__file__).parent
REPO_HOOKS    = REPO_ROOT / "hooks"
CLAUDE_DIR    = Path.home() / ".claude"
HOOKS_DIR     = CLAUDE_DIR / "hooks"
SETTINGS      = CLAUDE_DIR / "settings.json"
BACKUP_SUFFIX = ".bak"

HOOK_SCRIPTS = [
    "hook_logger.py",
    "protect.py",
    "protect_secrets.py",
    "protect_output.py",
    "protect_mcp_config.py",
]

# Each entry: (event, matcher, [scripts])
# Hooks are upserted by script filename — safe to re-run after adding new scripts.
WIRED_HOOKS: list[tuple[str, str, list[str]]] = [
    ("PreToolUse",  "Bash",  ["protect.py", "protect_secrets.py"]),
    ("PostToolUse", "Bash",  ["protect_output.py"]),
    ("PreToolUse",  "Edit",  ["protect_mcp_config.py"]),
    ("PreToolUse",  "Write", ["protect_mcp_config.py"]),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _script_label(cmd: str) -> str:
    """Return the basename of the script referenced in a hook command string."""
    return Path(cmd.split()[-1]).name


def _load_settings() -> dict:
    if not SETTINGS.exists():
        return {}
    try:
        with SETTINGS.open(encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        print(f"ERROR: {SETTINGS} is not valid JSON: {exc}")
        sys.exit(1)


def _save_settings(data: dict, dry_run: bool) -> None:
    if dry_run:
        print(f"  [dry-run] would write {SETTINGS}:")
        print("  " + json.dumps(data, indent=2).replace("\n", "\n  "))
        return
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    backup = SETTINGS.with_suffix(BACKUP_SUFFIX)
    if SETTINGS.exists():
        shutil.copy2(SETTINGS, backup)
        print(f"  backed up {SETTINGS} → {backup}")
    with SETTINGS.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    print(f"  wrote     {SETTINGS}")


def _hook_command(script_name: str) -> str:
    return f"python3 {HOOKS_DIR / script_name}"


# ---------------------------------------------------------------------------
# Core: merge hooks into settings (idempotent — upserts by script filename)
# ---------------------------------------------------------------------------

def _upsert_hooks(settings: dict) -> tuple[dict, list[str]]:
    """
    Merge this installer's hook entries into settings, keyed by script filename.
    Returns (updated_settings, list_of_change_descriptions).
    """
    changes: list[str] = []
    hooks_root = settings.setdefault("hooks", {})

    for event, matcher, scripts in WIRED_HOOKS:
        event_list = hooks_root.setdefault(event, [])

        matcher_block = next(
            (b for b in event_list if b.get("matcher") == matcher), None
        )
        if matcher_block is None:
            matcher_block = {"matcher": matcher, "hooks": []}
            event_list.append(matcher_block)

        hook_entries: list[dict] = matcher_block.setdefault("hooks", [])

        for script in scripts:
            new_cmd = _hook_command(script)
            existing = next(
                (e for e in hook_entries if _script_label(e.get("command", "")) == script),
                None,
            )
            if existing is None:
                hook_entries.append({"type": "command", "command": new_cmd})
                changes.append(f"  added    {event}[{matcher}] → {new_cmd}")
            elif existing["command"] != new_cmd:
                old_cmd = existing["command"]
                existing["command"] = new_cmd
                changes.append(f"  updated  {event}[{matcher}] {script}: {old_cmd!r} → {new_cmd!r}")
            else:
                changes.append(f"  ok       {event}[{matcher}] → {new_cmd} (no change)")

    return settings, changes


def _remove_hooks(settings: dict) -> tuple[dict, list[str]]:
    """Remove all hook entries added by this installer, keyed by (event, matcher)."""
    changes: list[str] = []
    # Build {(event, matcher): {scripts}} for lookup
    hook_map: dict[tuple[str, str], set[str]] = {}
    for event, matcher, scripts in WIRED_HOOKS:
        hook_map.setdefault((event, matcher), set()).update(scripts)

    hooks_root = settings.get("hooks", {})
    for event, event_list in hooks_root.items():
        for matcher_block in event_list:
            matcher = matcher_block.get("matcher", "")
            to_remove = hook_map.get((event, matcher), set())
            if not to_remove:
                continue
            before = list(matcher_block.get("hooks", []))
            matcher_block["hooks"] = [
                e for e in before
                if _script_label(e.get("command", "")) not in to_remove
            ]
            for e in before:
                if e not in matcher_block["hooks"]:
                    changes.append(f"  removed  {event}[{matcher}] → {e['command']}")

    return settings, changes


# ---------------------------------------------------------------------------
# Copy scripts
# ---------------------------------------------------------------------------

def copy_scripts(dry_run: bool) -> None:
    print(f"\n[1/2] Hook scripts → {HOOKS_DIR}")
    for script in HOOK_SCRIPTS:
        src = REPO_HOOKS / script
        dst = HOOKS_DIR / script
        if not src.exists():
            print(f"  MISSING  {src} — skipped")
            continue
        if dry_run:
            print(f"  [dry-run] would copy {src} → {dst}")
        else:
            HOOKS_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            dst.chmod(0o644)
            print(f"  copied   {dst}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run",    action="store_true", help="Preview changes without writing anything")
    parser.add_argument("--uninstall",  action="store_true", help="Remove hook entries added by this script")
    args = parser.parse_args()

    print("\nClaude Code security hooks installer")
    print("=====================================")

    if sys.version_info < (3, 7):
        print("ERROR: Python 3.7+ required.")
        sys.exit(1)

    if args.dry_run:
        print("(dry-run mode — nothing will be written)\n")

    if args.uninstall:
        print(f"\n[1/2] Hook scripts — skipped (uninstall keeps files on disk)")
        print(f"\n[2/2] Removing hook entries from {SETTINGS}")
        settings = _load_settings()
        settings, changes = _remove_hooks(settings)
        if changes:
            for c in changes:
                print(c)
            _save_settings(settings, args.dry_run)
        else:
            print("  nothing to remove")
        print("\nDone. Hook scripts remain at ~/.claude/hooks/ — delete manually if desired.")
        return

    # --- install ---
    copy_scripts(args.dry_run)

    print(f"\n[2/2] Wiring hooks in {SETTINGS}")
    settings = _load_settings()
    settings, changes = _upsert_hooks(settings)
    for c in changes:
        print(c)
    _save_settings(settings, args.dry_run)

    if not args.dry_run:
        print("\nDone.")
        print(f"  Hook scripts : {HOOKS_DIR}")
        print(f"  Settings     : {SETTINGS}")
        print(f"  Audit log    : {HOOKS_DIR / 'logs' / 'security-hooks.jsonl'}")
        print("\nStart a new Claude Code session and run /hooks to verify.")
    print()


if __name__ == "__main__":
    main()
