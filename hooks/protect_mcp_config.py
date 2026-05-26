#!/usr/bin/env python3
"""
Pre-tool hook: blocks @latest in MCP server args when writing or editing settings files.
Fires on Edit and Write tool calls targeting any file whose name contains "settings" and ends in ".json".

Note: You may want to temporarily disable or remove this hook when you are actively
developing, testing, or working with local MCP servers that legitimately need to
reference `@latest` (e.g. pointing at an unreleased local build during iteration).
Re-enable it before committing or returning to normal use so supply-chain protection
is restored. See docs/hooks.md and docs/mcp.md for context.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from hook_logger import log_event
except Exception:
    def log_event(event_type, details):
        return None

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool_name = payload.get("tool_name", "")
tool_input = payload.get("tool_input", {})

if tool_name not in ("Edit", "Write"):
    sys.exit(0)

file_path = tool_input.get("file_path", "")
file_name = Path(file_path).name

if not (file_name.endswith(".json") and "settings" in file_name):
    sys.exit(0)

# Extract the text being written (Write) or inserted (Edit).
if tool_name == "Write":
    content = tool_input.get("content", "")
elif tool_name == "Edit":
    content = tool_input.get("new_string", "")
else:
    content = ""

# Match @latest at the end of an npm package specifier inside JSON
# e.g. "@scope/server@latest"  or  "@latest"
if re.search(r'@latest["\s,\]]', content):
    reason = (
        f"BLOCKED: @latest detected in {file_name}. "
        "Pin the MCP server version (e.g. @1.2.3) to prevent silent supply-chain updates. "
        "See docs/mcp.md for guidance."
    )
    log_event("pretool_block", {"reason": reason, "file_path": file_path})
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)

sys.exit(0)
