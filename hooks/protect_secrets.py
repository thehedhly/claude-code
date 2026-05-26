#!/usr/bin/env python3
"""Pre-tool hook: blocks secret reads/copies and secret-bearing writes.

Branches on `tool_name`:
- Bash         : inspects tool_input.command (existing behavior)
- Read         : inspects tool_input.file_path for credential-store paths
- Write        : inspects tool_input.file_path and tool_input.content
- Edit         : inspects tool_input.file_path and tool_input.new_string
- MultiEdit    : inspects tool_input.file_path and each edit's new_string

Unknown tool_name => exit 0 (pass-through). Empty payload => exit 0.
"""

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


# ---------------------------------------------------------------------------
# Shared patterns
# ---------------------------------------------------------------------------

# Used by the Bash command-text scanner (whitespace-anchored, command syntax).
HOME_SENSITIVE_PATHS_CMD = [
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

PROJECT_SENSITIVE_PATHS_CMD = [
    r"(?:^|\s)\.azure(?:\/|\s|$)",
    r"(?:^|\s)\.env(?:\.(?!example\b|sample\b|template\b|dist\b)[\w.-]+)?(?:\s|$)",
    r"(?:^|\s)\.npmrc(?:\s|$)",
    r"(?:^|\s)\.pypirc(?:\s|$)",
    r"(?:^|\s)\.netrc(?:\s|$)",
]

ALLOWLIST_SAFE_SAMPLE_PATHS_CMD = [
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

# Path-based check for Read/Write/Edit/MultiEdit. Works on absolute paths.
HOME_SENSITIVE_PATH_PARTS = [
    (r"(?:^|/)\.ssh(?:/|$)",            "home ssh dir"),
    (r"(?:^|/)\.aws(?:/|$)",            "home aws creds dir"),
    (r"(?:^|/)\.config/gcloud(?:/|$)",  "gcloud creds dir"),
    (r"(?:^|/)\.kube(?:/|$)",           "kube config dir"),
    (r"(?:^|/)\.azure(?:/|$)",          "azure creds dir"),
]

# Allowlisted basename suffixes for env files (template/example variants).
ENV_ALLOWLIST_SUFFIXES = {"example", "sample", "template", "dist"}

# Allowlisted path fragments (sample/fixture directories).
ALLOWLIST_PATH_FRAGMENTS = ["/docs/examples/", "/examples/", "/fixtures/"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_payload() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def _block(reason: str, ctx: dict) -> None:
    log_event("pretool_block", {**ctx, "reason": reason})
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def _matches_any(text: str, patterns: Iterable[Tuple[str, str]]) -> Tuple[bool, str]:
    for pattern, label in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True, label
    return False, ""


def _path_is_allowlisted(file_path: str) -> bool:
    """Sample/fixture directories and .env.example-style basenames pass."""
    if not file_path:
        return False
    normalized = "/" + file_path.lstrip("/")
    if any(frag in normalized for frag in ALLOWLIST_PATH_FRAGMENTS):
        return True
    basename = Path(file_path).name
    if basename.startswith(".env."):
        suffix = basename[len(".env."):]
        if suffix in ENV_ALLOWLIST_SUFFIXES:
            return True
    return False


def _path_sensitivity(file_path: str) -> Tuple[bool, str]:
    """Return (is_sensitive, label). Empty path => (False, '')."""
    if not file_path:
        return False, ""

    for pattern, label in HOME_SENSITIVE_PATH_PARTS:
        if re.search(pattern, file_path):
            # Home credential dirs are NEVER allowlisted, even if they happen
            # to live under an examples/ tree.
            return True, label

    if _path_is_allowlisted(file_path):
        return False, ""

    basename = Path(file_path).name
    if basename == ".env":
        return True, "project .env file"
    if basename.startswith(".env.") and basename[len(".env."):] not in ENV_ALLOWLIST_SUFFIXES:
        return True, "project .env variant"
    if basename in {".npmrc", ".pypirc", ".netrc"}:
        return True, basename
    return False, ""


# ---------------------------------------------------------------------------
# Per-tool checks
# ---------------------------------------------------------------------------

def _check_bash(command: str) -> None:
    if not command:
        return

    has_home_sensitive_path = any(
        re.search(p, command, re.IGNORECASE) for p in HOME_SENSITIVE_PATHS_CMD
    )
    has_project_sensitive_path = any(
        re.search(p, command, re.IGNORECASE) for p in PROJECT_SENSITIVE_PATHS_CMD
    )
    is_allowlisted_sample = any(
        re.search(p, command, re.IGNORECASE) for p in ALLOWLIST_SAFE_SAMPLE_PATHS_CMD
    )

    if is_allowlisted_sample and not has_home_sensitive_path:
        has_project_sensitive_path = False

    has_sensitive_path = has_home_sensitive_path or has_project_sensitive_path
    has_read_or_copy = any(re.search(p, command, re.IGNORECASE) for p in READ_COPY_VERBS)

    if has_sensitive_path and has_read_or_copy:
        _block(
            "BLOCKED: Sensitive path read/copy detected (credentials policy).",
            {"tool": "Bash", "command": command},
        )

    matched, label = _matches_any(command, EXFIL_PATTERNS)
    if matched and has_sensitive_path:
        _block(
            f"BLOCKED: Sensitive path exfiltration risk detected ({label}).",
            {"tool": "Bash", "command": command},
        )

    matched, label = _matches_any(command, SECRET_LITERAL_PATTERNS)
    if matched:
        _block(
            f"BLOCKED: Secret material detected in command ({label}).",
            {"tool": "Bash", "command": command},
        )


def _check_read(file_path: str) -> None:
    sensitive, label = _path_sensitivity(file_path)
    if sensitive:
        _block(
            f"BLOCKED: Read of credential path detected ({label}).",
            {"tool": "Read", "file_path": file_path},
        )


def _check_write_like(tool: str, file_path: str, content: str) -> None:
    sensitive, label = _path_sensitivity(file_path)
    if sensitive:
        _block(
            f"BLOCKED: {tool} targets credential path ({label}).",
            {"tool": tool, "file_path": file_path},
        )

    if not content:
        return

    matched, label = _matches_any(content, SECRET_LITERAL_PATTERNS)
    if matched:
        _block(
            f"BLOCKED: Secret material detected in {tool} content ({label}).",
            {"tool": tool, "file_path": file_path},
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

payload = _load_payload()
tool_name = payload.get("tool_name", "")
tool_input = payload.get("tool_input") or {}

if not isinstance(tool_input, dict):
    sys.exit(0)

if tool_name == "Bash":
    _check_bash(str(tool_input.get("command", "")))
elif tool_name == "Read":
    _check_read(str(tool_input.get("file_path", "")))
elif tool_name == "Write":
    _check_write_like(
        "Write",
        str(tool_input.get("file_path", "")),
        str(tool_input.get("content", "")),
    )
elif tool_name == "Edit":
    _check_write_like(
        "Edit",
        str(tool_input.get("file_path", "")),
        str(tool_input.get("new_string", "")),
    )
elif tool_name == "MultiEdit":
    file_path = str(tool_input.get("file_path", ""))
    sensitive, label = _path_sensitivity(file_path)
    if sensitive:
        _block(
            f"BLOCKED: MultiEdit targets credential path ({label}).",
            {"tool": "MultiEdit", "file_path": file_path},
        )
    for edit in tool_input.get("edits", []) or []:
        if not isinstance(edit, dict):
            continue
        new_string = str(edit.get("new_string", ""))
        matched, label = _matches_any(new_string, SECRET_LITERAL_PATTERNS)
        if matched:
            _block(
                f"BLOCKED: Secret material detected in MultiEdit content ({label}).",
                {"tool": "MultiEdit", "file_path": file_path},
            )
elif not tool_name and tool_input.get("command"):
    # Backwards compat: payload without tool_name but with a command string.
    _check_bash(str(tool_input.get("command", "")))

sys.exit(0)
