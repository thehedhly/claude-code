#!/usr/bin/env python3
"""Smoke tests for issue #3 — Non-Bash tool matchers in protect_secrets.py.

Covers Bash (regression), Read, Write, Edit, MultiEdit branches. Constructs
sensitive-looking strings dynamically so the developer's own active hooks
don't intercept this test runner when it's edited.

Usage: python3 tests/smoke_issue_3.py
Exits 0 on all-pass, 1 if any case fails.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "hooks" / "protect_secrets.py"

# Build sensitive material at runtime to avoid tripping the user's own hooks
# while editing or grepping this file.
AKIA = "AKIA" + "IOSFODNN7EXAMPLE"

CASES = [
    # --- Bash regression: existing behavior must be preserved ---
    ("Bash: rm -rf passes (not protect_secrets' job)",
     {"tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/test"}},
     "pass"),
    ("Bash: cat ~/.ssh/id_rsa blocks",
     {"tool_name": "Bash", "tool_input": {"command": "cat ~/.ssh/id_rsa"}},
     "block"),
    ("Bash: ls /tmp passes",
     {"tool_name": "Bash", "tool_input": {"command": "ls /tmp"}},
     "pass"),
    ("Bash: aws key literal in command blocks",
     {"tool_name": "Bash", "tool_input": {"command": f"echo creds={AKIA}"}},
     "block"),
    ("Bash: legacy payload (no tool_name) still works",
     {"tool_input": {"command": "cat ~/.ssh/id_rsa"}},
     "block"),

    # --- Read: new matcher coverage ---
    ("Read: ~/.ssh/id_rsa blocks",
     {"tool_name": "Read", "tool_input": {"file_path": "/Users/foo/.ssh/id_rsa"}},
     "block"),
    ("Read: /etc/hosts passes",
     {"tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}},
     "pass"),
    ("Read: project .env blocks",
     {"tool_name": "Read", "tool_input": {"file_path": "/Users/foo/proj/.env"}},
     "block"),
    ("Read: .env.production blocks (non-allowlisted suffix)",
     {"tool_name": "Read", "tool_input": {"file_path": "/Users/foo/proj/.env.production"}},
     "block"),
    ("Read: .env.example passes (allowlisted suffix)",
     {"tool_name": "Read", "tool_input": {"file_path": "/Users/foo/proj/.env.example"}},
     "pass"),
    ("Read: fixtures/.env passes (allowlisted dir)",
     {"tool_name": "Read", "tool_input": {"file_path": "/Users/foo/proj/fixtures/.env"}},
     "pass"),
    ("Read: ~/.aws/credentials blocks even under examples/ (home creds never allowlisted)",
     {"tool_name": "Read", "tool_input": {"file_path": "/Users/foo/examples/.aws/credentials"}},
     "block"),
    ("Read: empty file_path passes (no payload)",
     {"tool_name": "Read", "tool_input": {}},
     "pass"),

    # --- Write: path + content checks ---
    ("Write: targeting .env blocks",
     {"tool_name": "Write",
      "tool_input": {"file_path": "/Users/foo/proj/.env", "content": "FOO=bar"}},
     "block"),
    ("Write: .env.example passes",
     {"tool_name": "Write",
      "tool_input": {"file_path": "/Users/foo/proj/.env.example", "content": "FOO=bar"}},
     "pass"),
    ("Write: secret literal into innocuous file blocks",
     {"tool_name": "Write",
      "tool_input": {"file_path": "/tmp/notes.txt", "content": f"My key is {AKIA}"}},
     "block"),
    ("Write: benign content into innocuous file passes",
     {"tool_name": "Write",
      "tool_input": {"file_path": "/tmp/notes.txt", "content": "hello world"}},
     "pass"),

    # --- Edit: path + new_string checks ---
    ("Edit: targeting ~/.ssh/config blocks",
     {"tool_name": "Edit",
      "tool_input": {"file_path": "/Users/foo/.ssh/config", "new_string": "Host x"}},
     "block"),
    ("Edit: aws key in new_string blocks",
     {"tool_name": "Edit",
      "tool_input": {"file_path": "/tmp/foo.txt", "new_string": f"key={AKIA}"}},
     "block"),
    ("Edit: benign new_string passes",
     {"tool_name": "Edit",
      "tool_input": {"file_path": "/tmp/foo.txt", "new_string": "hello"}},
     "pass"),

    # --- MultiEdit: per-edit content scanning ---
    ("MultiEdit: targeting ~/.aws blocks",
     {"tool_name": "MultiEdit",
      "tool_input": {"file_path": "/Users/foo/.aws/config",
                     "edits": [{"old_string": "a", "new_string": "b"}]}},
     "block"),
    ("MultiEdit: secret in any edit's new_string blocks",
     {"tool_name": "MultiEdit",
      "tool_input": {"file_path": "/tmp/x.txt",
                     "edits": [
                         {"old_string": "a", "new_string": "ok"},
                         {"old_string": "b", "new_string": f"k={AKIA}"},
                     ]}},
     "block"),
    ("MultiEdit: all benign edits pass",
     {"tool_name": "MultiEdit",
      "tool_input": {"file_path": "/tmp/x.txt",
                     "edits": [
                         {"old_string": "a", "new_string": "ok"},
                         {"old_string": "b", "new_string": "fine"},
                     ]}},
     "pass"),

    # --- Unknown tool_name: must pass-through ---
    ("Unknown tool_name passes",
     {"tool_name": "Glob", "tool_input": {"pattern": "**/*.py"}},
     "pass"),
]


def run(payload: dict) -> tuple[str, int]:
    proc = subprocess.run(
        ["python3", str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip(), proc.returncode


def classify(stdout: str) -> str:
    if not stdout:
        return "pass"
    try:
        return json.loads(stdout).get("decision", "unknown")
    except json.JSONDecodeError:
        return f"unparseable:{stdout[:80]}"


def main() -> int:
    passed = failed = 0
    for name, payload, expected in CASES:
        out, rc = run(payload)
        actual = classify(out)
        ok = (actual == expected) and rc == 0
        mark = "OK  " if ok else "FAIL"
        print(f"{mark}  expected={expected:5}  actual={actual:5}  rc={rc}  {name}")
        if not ok:
            print(f"      stdout: {out!r}")
            failed += 1
        else:
            passed += 1
    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
