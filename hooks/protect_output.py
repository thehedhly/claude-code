#!/usr/bin/env python3
"""Post-tool hook: blocks responses that appear to contain credentials."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Tuple

sys.path.insert(0, str(Path(__file__).parent))

try:
    from hook_logger import log_event
except Exception:
    def log_event(event_type, details):
        return None


def _load_payload() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=True)
    except Exception:
        return str(value)


def _extract_output_text(payload: dict) -> str:
    candidates = [
        payload.get("tool_output"),
        payload.get("output"),
        payload.get("result"),
        payload.get("response"),
    ]

    text_parts = [_to_text(candidate) for candidate in candidates if candidate is not None]

    tool_output = payload.get("tool_output")
    if isinstance(tool_output, dict):
        for key in ("stdout", "stderr", "text"):
            if key in tool_output:
                text_parts.append(_to_text(tool_output.get(key)))

    return "\n".join(part for part in text_parts if part)


def _block(reason: str, excerpt: str) -> None:
    log_event("posttool_block", {"reason": reason, "excerpt": excerpt[:240]})
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def _match_any(text: str, patterns: Iterable[Tuple[str, str]]) -> Tuple[bool, str]:
    for pattern, label in patterns:
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            return True, label
    return False, ""


payload = _load_payload()
output_text = _extract_output_text(payload)

if not output_text:
    sys.exit(0)

LEAK_PATTERNS = [
    (r"-----BEGIN\s+(?:OPENSSH|RSA|EC|DSA)\s+PRIVATE\s+KEY-----", "private key block"),
    (r"AKIA[0-9A-Z]{16}", "aws access key id"),
    (r"\bASIA[0-9A-Z]{16}\b", "aws temporary access key id"),
    (r"\bghp_[A-Za-z0-9]{20,}\b", "github token ghp"),
    (r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", "github pat"),
    (r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", "slack token"),
    (r"\bsk_live_[A-Za-z0-9]{10,}\b", "live api key"),
    (r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9._-]{10,}\.[A-Za-z0-9._-]{10,}", "jwt-like token"),
]

matched, label = _match_any(output_text, LEAK_PATTERNS)
if matched:
    _block(f"BLOCKED: Potential secret leak detected in tool output ({label}).", output_text)

sys.exit(0)
