#!/usr/bin/env python3
"""Post-tool hook: redacts credentials from tool output (warn by default, block in strict mode).

Mode is controlled by the PROTECT_OUTPUT_MODE env var:
  warn  (default) — redact matches in the logged excerpt, emit {"decision": "warn"}.
                    Claude still receives the original output; the user sees the warning.
  block           — block the entire output (original behaviour, preserved for high-security
                    environments). Also activated by PROTECT_OUTPUT_STRICT=1.
  off             — disable scanning entirely (use only for trusted debugging sessions).

Trade-off: warn mode keeps Claude functional when output incidentally contains a secret-like
string (e.g. an old commit message, a log file) but does not prevent Claude from seeing the
raw value. Set PROTECT_OUTPUT_MODE=block or PROTECT_OUTPUT_STRICT=1 when that is unacceptable.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable, List, Tuple

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


def _redact(text: str, patterns: Iterable[Tuple[str, str]]) -> Tuple[str, List[Tuple[str, str]]]:
    """Replace each pattern match with [REDACTED]. Returns (redacted_text, [(match, label), ...])."""
    matches: List[Tuple[str, str]] = []
    for pattern, label in patterns:
        def _sub(m, label=label):
            matches.append((m.group(0), label))
            return "[REDACTED]"
        text = re.sub(pattern, _sub, text, flags=re.IGNORECASE | re.MULTILINE)
    return text, matches


def _match_any(text: str, patterns: Iterable[Tuple[str, str]]) -> Tuple[bool, str]:
    for pattern, label in patterns:
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            return True, label
    return False, ""


def _resolve_mode() -> str:
    if os.environ.get("PROTECT_OUTPUT_STRICT", "").strip() == "1":
        return "block"
    return os.environ.get("PROTECT_OUTPUT_MODE", "warn").strip().lower()


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

mode = _resolve_mode()

if mode == "off":
    sys.exit(0)

if mode == "block":
    matched, label = _match_any(output_text, LEAK_PATTERNS)
    if matched:
        _block(f"BLOCKED: Potential secret leak detected in tool output ({label}).", output_text)
    sys.exit(0)

# Default: warn — redact matches in the log excerpt, surface a warning to the user.
_, matches = _redact(output_text, LEAK_PATTERNS)
if matches:
    labels = ", ".join(sorted(set(label for _, label in matches)))
    log_event("posttool_redact", {"labels": list(set(label for _, label in matches)), "count": len(matches)})
    print(json.dumps({
        "decision": "warn",
        "reason": (
            f"Secret pattern(s) detected in tool output ({labels}). "
            "Claude received the original output. Set PROTECT_OUTPUT_MODE=block "
            "or PROTECT_OUTPUT_STRICT=1 to block instead."
        ),
    }))

sys.exit(0)
