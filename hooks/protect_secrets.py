#!/usr/bin/env python3
"""Pre-tool hook: blocks secret reads/copies and obvious exfil commands."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable, Tuple

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


def _extract_command(payload: dict) -> str:
    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, dict):
        return str(tool_input.get("command", ""))
    return ""


def _block(reason: str, cmd: str) -> None:
    log_event("pretool_block", {"reason": reason, "command": cmd})
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def _matches_any(cmd: str, patterns: Iterable[Tuple[str, str]]) -> Tuple[bool, str]:
    for pattern, label in patterns:
        if re.search(pattern, cmd, re.IGNORECASE):
            return True, label
    return False, ""


payload = _load_payload()
command = _extract_command(payload)

if not command:
    sys.exit(0)

# Strongly protect home/credential store paths.
HOME_SENSITIVE_PATHS = [
    r"~\/\.ssh(?:\/|\b)",
    r"~\/\.aws(?:\/|\b)",
    r"~\/\.config\/gcloud(?:\/|\b)",
    r"~\/\.kube(?:\/|\b)",
    r"~\/\.azure(?:\/|\b)",
    r"\/\.ssh(?:\/|\b)",
    r"\/\.aws(?:\/|\b)",
    r"\/\.config\/gcloud(?:\/|\b)",
    r"\/\.kube(?:\/|\b)",
    r"\/\.azure(?:\/|\b)",
]

# Protect common project-local credential files, but do not treat sample/template files as secrets.
PROJECT_SENSITIVE_PATHS = [
    r"(?:^|\s)\.azure(?:\/|\s|$)",
    r"(?:^|\s)\.env(?:\.(?!example\b|sample\b|template\b|dist\b)[\w.-]+)?(?:\s|$)",
    r"(?:^|\s)\.npmrc(?:\s|$)",
    r"(?:^|\s)\.pypirc(?:\s|$)",
    r"(?:^|\s)\.netrc(?:\s|$)",
]

ALLOWLIST_SAFE_SAMPLE_PATHS = [
    r"(?:^|\s)\.env\.(?:example|sample|template|dist)(?:\s|$)",
    r"(?:^|\s)(?:docs\/examples\/|examples\/|fixtures\/)",
]

READ_COPY_VERBS = [
    r"\bcat\b", r"\bless\b", r"\bmore\b", r"\bhead\b", r"\btail\b", r"\bsed\b", r"\bawk\b",
    r"\bgrep\b", r"\brg\b", r"\bfind\b", r"\bcp\b", r"\brsync\b", r"\bscp\b", r"\btar\b",
    r"\bzip\b", r"\bunzip\b", r"\bpbcopy\b",
]

EXFIL_PATTERNS = [
    (r"\bcurl\b.*(--data|-d|--form|--upload-file)", "curl payload upload"),
    (r"\bwget\b.*--post-data", "wget post data"),
    (r"\bhttp\b\s+(post|put|patch)\b", "httpie post/put/patch"),
    (r"\bnc\b\s+", "netcat transfer"),
    (r"\bgh\b\s+api\b.*(-f|--field|--raw-field)", "gh api data send"),
]

SECRET_LITERAL_PATTERNS = [
    (r"BEGIN\s+OPENSSH\s+PRIVATE\s+KEY", "openssh private key marker"),
    (r"BEGIN\s+RSA\s+PRIVATE\s+KEY", "rsa private key marker"),
    (r"AKIA[0-9A-Z]{16}", "aws access key id"),
    (r"\bghp_[A-Za-z0-9]{20,}\b", "github token ghp"),
    (r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", "github pat"),
    (r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", "slack token"),
    (r"\bsk_live_[A-Za-z0-9]{10,}\b", "live api key"),
]

has_home_sensitive_path = any(re.search(pattern, command, re.IGNORECASE) for pattern in HOME_SENSITIVE_PATHS)
has_project_sensitive_path = any(re.search(pattern, command, re.IGNORECASE) for pattern in PROJECT_SENSITIVE_PATHS)
is_allowlisted_sample = any(re.search(pattern, command, re.IGNORECASE) for pattern in ALLOWLIST_SAFE_SAMPLE_PATHS)

# Allowlist only suppresses project-local detections, never home credential stores.
if is_allowlisted_sample and not has_home_sensitive_path:
    has_project_sensitive_path = False

has_sensitive_path = has_home_sensitive_path or has_project_sensitive_path
has_read_or_copy = any(re.search(pattern, command, re.IGNORECASE) for pattern in READ_COPY_VERBS)

if has_sensitive_path and has_read_or_copy:
    _block("BLOCKED: Sensitive path read/copy detected (credentials policy).", command)

matched, label = _matches_any(command, EXFIL_PATTERNS)
if matched and has_sensitive_path:
    _block(f"BLOCKED: Sensitive path exfiltration risk detected ({label}).", command)

matched, label = _matches_any(command, SECRET_LITERAL_PATTERNS)
if matched:
    _block(f"BLOCKED: Secret material detected in command ({label}).", command)

sys.exit(0)
