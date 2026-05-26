#!/usr/bin/env python3
"""Post-tool hook: surface prompt-injection markers in WebFetch / mcp__* output.

Defaults to `warn` (non-blocking surface) on first detection. The patterns
target the most common instruction-override and chat-template tokens. Real
content (security blog posts, research papers about jailbreaks) will
false-positive here; that's why warn is the default rather than block.

Mode is controlled by `DETECT_INJECTION_MODE`:
- off    : do nothing, exit 0
- warn   : emit {"decision": "warn", ...} and log on match (default)
- block  : emit {"decision": "block", ...} and log on match

Every detection is logged via hook_logger regardless of mode.
"""

from __future__ import annotations

import json
import os
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


MODE_DEFAULT = "warn"
MODE_ENV_VAR = "DETECT_INJECTION_MODE"
VALID_MODES = {"off", "warn", "block"}

# Heuristic threshold for an inline base64-looking blob.
BASE64_BLOB_THRESHOLD = 200


# Instruction-override and template-injection markers.
INJECTION_PATTERNS: list[Tuple[str, str]] = [
    (
        r"(?i)ignore\s+(?:(?:all|the)\s+)*(?:previous|prior|earlier|above)\s+"
        r"(?:instructions?|prompts?|directives?|messages?)",
        "instruction override",
    ),
    (
        r"(?i)disregard\s+(?:your\s+|the\s+|all\s+)?"
        r"(?:prior|earlier|previous|above)\s+(?:instructions?|directives?)",
        "instruction disregard",
    ),
    (
        r"(?i)forget\s+(?:everything|all\s+(?:prior|previous|of\s+the\s+above))",
        "memory wipe attempt",
    ),
    (
        r"(?i)you\s+are\s+now\s+(?:a|an)\s+\w+",
        "role reassignment",
    ),
    (
        r"<\|(?:im_start|im_end|system|user|assistant)\|>",
        "openai chat template token",
    ),
    (
        r"\[/?INST\]|<<SYS>>|<</SYS>>",
        "llama/mistral instruction token",
    ),
    (
        r"(?i)new\s+(?:system\s+)?(?:prompt|message|instructions?|task)\s*:",
        "fake new-instructions header",
    ),
    (
        r"(?i)(?:^|\n)\s*system\s*:\s*(?:you\s+are|new\s+task|you\s+must)",
        "fake system role prefix",
    ),
    (
        r"(?i)(?:execute|run|perform)\s+(?:the\s+)?following\s+"
        r"(?:command|code|instructions?)",
        "execute-following directive",
    ),
]

BASE64_BLOB_RE = re.compile(rf"[A-Za-z0-9+/=]{{{BASE64_BLOB_THRESHOLD},}}")


def _resolve_mode() -> str:
    raw = (os.environ.get(MODE_ENV_VAR) or MODE_DEFAULT).strip().lower()
    return raw if raw in VALID_MODES else MODE_DEFAULT


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
    """Best-effort flattening of every text-like field in the payload."""
    candidates = [
        payload.get("tool_output"),
        payload.get("output"),
        payload.get("result"),
        payload.get("response"),
    ]
    parts = [_to_text(c) for c in candidates if c is not None]

    tool_output = payload.get("tool_output")
    if isinstance(tool_output, dict):
        for key in ("stdout", "stderr", "text", "content", "body"):
            if key in tool_output:
                parts.append(_to_text(tool_output.get(key)))

    return "\n".join(p for p in parts if p)


def _find_matches(text: str) -> list[Tuple[str, str]]:
    """Return [(matched_excerpt, label)] for every pattern that matched."""
    hits: list[Tuple[str, str]] = []
    for pattern, label in INJECTION_PATTERNS:
        m = re.search(pattern, text)
        if m:
            hits.append((m.group(0)[:80], label))
    blob = BASE64_BLOB_RE.search(text)
    if blob:
        hits.append((f"{blob.group(0)[:40]}…", f"base64 blob ≥{BASE64_BLOB_THRESHOLD} chars"))
    return hits


def _emit(decision: str, hits: list[Tuple[str, str]], tool_name: str) -> None:
    labels = sorted({label for _, label in hits})
    reason = (
        f"Prompt-injection markers detected in {tool_name or 'tool'} output "
        f"({', '.join(labels)}). Review the tool result before acting on it."
    )
    log_event(
        "posttool_injection",
        {
            "decision": decision,
            "tool": tool_name,
            "labels": labels,
            "match_count": len(hits),
            "first_excerpt": hits[0][0] if hits else "",
        },
    )
    print(json.dumps({"decision": decision, "reason": reason}))


def main() -> int:
    mode = _resolve_mode()
    if mode == "off":
        return 0

    payload = _load_payload()
    text = _extract_output_text(payload)
    if not text:
        return 0

    hits = _find_matches(text)
    if not hits:
        return 0

    tool_name = str(payload.get("tool_name", ""))
    decision = "warn" if mode == "warn" else "block"
    _emit(decision, hits, tool_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
