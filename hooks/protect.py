#!/usr/bin/env python3
"""
Pre-tool hook: blocks dangerous deletions and git force pushes.
Reads Claude Code tool input JSON from stdin, outputs a block decision if needed.
"""

import sys
import json
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from hook_logger import log_event
except Exception:
    def log_event(event_type, details):
        # Logging should never break enforcement.
        return None

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

cmd = payload.get("tool_input", {}).get("command", "")

DANGEROUS_DELETIONS = [
    (r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|--force\s+)",   "rm with -f/--force"),
    (r"rm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+|--recursive\s+)", "rm with -r/--recursive"),
    (r"rm\s+-rf",                                        "rm -rf"),
    (r"rm\s+-fr",                                        "rm -fr"),
    (r"rmdir",                                           "rmdir"),
    (r"find\s+.*-delete",                                "find -delete"),
    (r"find\s+.*-exec\s+rm",                             "find -exec rm"),
    (r"shred\s+",                                        "shred"),
    (r"srm\s+",                                          "srm (secure-delete)"),
    (r"diskutil\s+(erase|zeroDisk|secureErase)",         "diskutil erase/wipe"),
    (r">\s*/dev/(disk|rdisk)",                           "write to raw disk device"),
    (r"dd\s+.*of=/dev/(disk|rdisk)",                     "dd to raw disk device"),
]

FORCE_PUSH_PATTERNS = [
    (r"git\s+push\s+(?!.*--force-with-lease).*--force", "git push --force"),
    (r"git\s+push\s+(?!.*--force-with-lease).*\s-f(\s|$)", "git push -f"),
]

def block(reason, command_text):
    log_event("pretool_block", {"reason": reason, "command": command_text})
    print(json.dumps({"decision": "block", "reason": f"BLOCKED: {reason}"}))
    sys.exit(0)

for pattern, label in DANGEROUS_DELETIONS:
    if re.search(pattern, cmd, re.IGNORECASE):
        block(f"Dangerous deletion detected ({label}). Run manually in your terminal if truly intended.", cmd)

for pattern, label in FORCE_PUSH_PATTERNS:
    if re.search(pattern, cmd, re.IGNORECASE):
        block(f"Git force push detected ({label}). Use --force-with-lease instead, or run manually if truly intended.", cmd)

sys.exit(0)
