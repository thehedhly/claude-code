#!/usr/bin/env python3
"""Shared logger for Claude hook security events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

LOG_PATH = Path.home() / ".claude" / "hooks" / "logs" / "security-hooks.jsonl"


def log_event(event_type: str, details: Dict[str, Any]) -> None:
    """Append a single security event to a local JSONL log file."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "details": details,
        }
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=True) + "\n")
    except Exception:
        # Logging failures must never break hook enforcement.
        pass
