# Hook System Reference

Claude Code hooks are shell commands wired to tool lifecycle events in `settings.json`. They run synchronously and can block a tool call before it executes or scrub output before Claude sees it.

## Event Types

| Event | Fires | Typical use |
|-------|-------|-------------|
| `PreToolUse` | Before any tool call | Block dangerous commands, validate inputs |
| `PostToolUse` | After the tool runs, before output reaches Claude | Scrub secrets from outputs |
| `PreCompact` | Before conversation compaction | Preserve critical context |
| `Notification` | On idle/system notifications | Custom desktop alerts |
| `Stop` | When Claude's turn ends | Post-run logging, summaries |

## Hook Protocol

Hooks receive a JSON payload on `stdin`. For `PreToolUse[Bash]`:

```json
{
  "tool_name": "Bash",
  "tool_input": { "command": "cat ~/.ssh/id_rsa" }
}
```

For `PostToolUse[Bash]`:

```json
{
  "tool_name": "Bash",
  "tool_input": { "command": "..." },
  "tool_output": "...command stdout/stderr..."
}
```

### Decision Outputs

| stdout | Exit code | Effect |
|--------|-----------|--------|
| `{"decision": "block", "reason": "..."}` | `0` | Tool call is blocked; reason shown to user |
| `{"decision": "warn", "reason": "..."}` | `0` | Non-blocking warning surfaced to user |
| *(empty)* | `0` | Pass-through — tool proceeds normally |
| *(any)* | non-zero | Hook infrastructure error; warning surfaced, tool still runs |

## Hook Scripts in This Repo

### `protect.py` — Dangerous Operations Guard

**Event:** `PreToolUse` on `Bash`

Blocks the following patterns (case-insensitive regex on `tool_input.command`):

**Destructive deletions**

| Pattern | Label |
|---------|-------|
| `rm -f`, `rm --force` | rm with force flag |
| `rm -r`, `rm --recursive` | rm with recursive flag |
| `rm -rf`, `rm -fr` | rm -rf |
| `rmdir` | rmdir |
| `find … -delete` | find with -delete action |
| `find … -exec rm` | find piped to rm |
| `shred` | shred |
| `srm` | secure-delete |
| `diskutil erase/zeroDisk/secureErase` | diskutil wipe |
| `> /dev/disk*`, `> /dev/rdisk*` | raw disk write |
| `dd … of=/dev/disk*` | dd to raw disk |

**Git force push**

| Pattern | Allowed alternative |
|---------|-------------------|
| `git push --force` | `git push --force-with-lease` |
| `git push -f` | `git push --force-with-lease` |

`--force-with-lease` is explicitly allowed — it is the safe alternative because it fails if the remote has moved since your last fetch.

---

### `protect_secrets.py` — Credential Exfiltration Guard

**Event:** `PreToolUse` on `Bash`, `Read`, `Write`, `Edit`, `MultiEdit`

The script branches on `tool_name` so the same enforcement applies whether Claude opens a shell, reads a file directly via the `Read` tool, or writes content via `Write`/`Edit`/`MultiEdit`. A non-Bash matcher is required because the `Read` tool bypasses the shell entirely — a hook bound only to `Bash` cannot see `Read("/Users/x/.ssh/id_rsa")`.

| `tool_name` | Inspects | Blocks when |
|---|---|---|
| `Bash` | `tool_input.command` | sensitive-path read/copy verbs, exfil patterns with sensitive paths, or secret literals in the command |
| `Read` | `tool_input.file_path` | path resolves to a credential-store dir or a project-local secret file |
| `Write` | `tool_input.file_path` and `tool_input.content` | path is a credential store, or content contains a secret literal |
| `Edit` | `tool_input.file_path` and `tool_input.new_string` | same as Write |
| `MultiEdit` | `tool_input.file_path` and each `edits[*].new_string` | same as Write, applied per edit |

Unknown `tool_name` is a pass-through (`exit 0`). The matcher list in `settings.json` is the gate; the script defends against a misconfigured matcher rather than enforcing on every tool unconditionally.

**Bash-mode detection layers (unchanged)**

Three independent detection layers apply to `tool_name == "Bash"`:

**1. Sensitive path reads**

Blocks read/copy commands targeting credential store paths:

| Blocked paths | Read verbs blocked |
|---------------|-------------------|
| `~/.ssh/`, `~/.aws/`, `~/.config/gcloud/`, `~/.kube/`, `~/.azure/` | `cat`, `less`, `more`, `head`, `tail`, `sed`, `awk`, `grep`, `rg`, `find`, `cp`, `rsync`, `scp`, `tar`, `zip`, `unzip`, `pbcopy` |
| `.env`, `.npmrc`, `.pypirc`, `.netrc` (project-local) | same verbs |

Allowlisted (never blocked): `.env.example`, `.env.sample`, `.env.template`, `.env.dist`, paths under `docs/examples/` or `examples/` or `fixtures/`.

**2. Exfiltration commands + sensitive path**

Blocked when a sensitive path AND a data-sending command appear together:

| Pattern | Label |
|---------|-------|
| `curl … --data/-d/--form/--upload-file` | curl payload upload |
| `wget … --post-data` | wget post data |
| `http post/put/patch` | httpie write methods |
| `nc` (netcat) | netcat transfer |
| `gh api … -f/--field` | gh api data send |

**3. Secret literal detection**

Blocked regardless of path context if the command itself contains:

| Pattern | What it detects |
|---------|----------------|
| `BEGIN OPENSSH PRIVATE KEY` | OpenSSH private key |
| `BEGIN RSA PRIVATE KEY` | RSA private key |
| `AKIA[0-9A-Z]{16}` | AWS access key ID |
| `ghp_[A-Za-z0-9]{20,}` | GitHub personal token |
| `github_pat_[A-Za-z0-9_]{20,}` | GitHub fine-grained PAT |
| `xox[baprs]-[A-Za-z0-9-]{10,}` | Slack token |
| `sk_live_[A-Za-z0-9]{10,}` | Stripe live API key |

**Path-mode detection (Read / Write / Edit / MultiEdit)**

For non-Bash tools the script does a basename/path check rather than command-string parsing:

| File path matches | Outcome |
|---|---|
| Contains `/.ssh/`, `/.aws/`, `/.config/gcloud/`, `/.kube/`, `/.azure/` (anywhere) | Always blocked — home credential dirs are not allowlistable. |
| Basename is exactly `.env`, `.npmrc`, `.pypirc`, `.netrc` | Blocked unless inside a sample/fixture path. |
| Basename matches `.env.<suffix>` where suffix ∉ {`example`, `sample`, `template`, `dist`} | Blocked. |
| Path contains `/examples/`, `/docs/examples/`, or `/fixtures/` (and is not a home credential dir) | Allowlisted. |

For `Write`/`Edit`/`MultiEdit`, the `content` / `new_string` is also scanned against the same `SECRET_LITERAL_PATTERNS` as Bash — so Claude cannot launder a secret literal by writing it to an arbitrary file.

---

### `protect_output.py` — Output Scrubber

**Event:** `PostToolUse` on `Bash`, `Read`, `Write`, `Edit`, `WebFetch`, `mcp__.*`

The same script is wired across every tool that returns text Claude will ingest. The `Bash`-only wiring used in earlier versions missed file content read via `Read`, content fetched via `WebFetch`, and any output from MCP servers — all of which are common credential-leak surfaces.

Scans the full tool output text before Claude's context receives it. Detects:

| Pattern | What it detects |
|---------|----------------|
| `-----BEGIN (OPENSSH\|RSA\|EC\|DSA) PRIVATE KEY-----` | Private key PEM block |
| `AKIA[0-9A-Z]{16}` | AWS access key ID |
| `ASIA[0-9A-Z]{16}` | AWS temporary STS key |
| `ghp_[A-Za-z0-9]{20,}` | GitHub token |
| `github_pat_[A-Za-z0-9_]{20,}` | GitHub fine-grained PAT |
| `xox[baprs]-[A-Za-z0-9-]{10,}` | Slack token |
| `sk_live_[A-Za-z0-9]{10,}` | Stripe live key |
| `eyJ…[three-segment base64]` | JWT-like token |

#### Mode control

Set via the `PROTECT_OUTPUT_MODE` environment variable (or the `PROTECT_OUTPUT_STRICT` shorthand):

| Mode | Env var | Behavior |
|------|---------|----------|
| `warn` (default) | _(unset)_ or `PROTECT_OUTPUT_MODE=warn` | On match: log the detection and emit `{"decision": "warn"}`. Claude still receives the original output; the user sees a warning. Keeps Claude functional when output incidentally contains a secret-like pattern (old commit message, log file, etc.). |
| `block` | `PROTECT_OUTPUT_MODE=block` or `PROTECT_OUTPUT_STRICT=1` | On match: block the entire output — Claude sees only the block reason. Use for high-security or automated environments where no false-negative is acceptable. |
| `off` | `PROTECT_OUTPUT_MODE=off` | Disable scanning entirely. Use only for trusted debugging sessions. |

**Trade-off:** `warn` mode avoids the "Claude can't see anything useful" failure mode that drove users to disable the hook, but it does not prevent Claude from reading a raw secret. If that risk is unacceptable, set `PROTECT_OUTPUT_STRICT=1` in your shell profile or in the `env` block of your `settings.json`.

> ⚠️ The JWT-like pattern (`eyJ...`) may false-positive against legitimate API responses returned by MCP servers or `WebFetch`. If the noise outweighs the value, narrow that pattern in `protect_output.py` or remove the `WebFetch` / `mcp__.*` matchers from `settings.json`.

---

### `detect_injection.py` — Prompt-Injection Detector

**Event:** `PostToolUse` on `WebFetch` and `mcp__.*`

Surfaces likely prompt-injection markers in tool returns from untrusted sources. The two wired matchers cover the canonical injection vectors: web pages fetched into context and MCP tool responses (which often pull from external systems — Jira tickets, GitHub issues, docs search results, etc.).

**Default mode is `warn`, not `block`.** Real content discussing prompt injection — security research articles, jailbreak datasets, the issue tracker for this repo — will match these patterns legitimately. Warning surfaces the detection without throwing away the entire tool result.

#### Mode control

Set via the `DETECT_INJECTION_MODE` environment variable:

| Mode | Behavior |
|---|---|
| `off` | Script exits 0, no scan. Use for sessions intentionally browsing adversarial content. |
| `warn` (default) | Emits `{"decision": "warn", ...}` on match. Claude still sees the output, but the user gets a flag. |
| `block` | Emits `{"decision": "block", ...}` on match. Use for sessions in high-trust automation contexts where no false positive is acceptable. |

Every detection is logged via `hook_logger.py` (event type `posttool_injection`) regardless of mode — so you can audit what the warn mode is catching even when the user doesn't notice it.

#### Patterns

| Pattern | What it catches |
|---|---|
| `(?i)ignore\s+(all\|the\|prior\|previous\|earlier\|above)\s+instructions/prompts/directives` | Classic instruction override |
| `(?i)disregard\s+…\s+(prior\|earlier\|previous)\s+instructions` | Override variant |
| `(?i)forget\s+(everything\|all\s+(prior\|previous))` | Memory wipe attempt |
| `(?i)you\s+are\s+now\s+(a\|an)\s+\w+` | Role reassignment ("you are now a system administrator…") |
| `<\|im_start\|>`, `<\|system\|>`, `<\|user\|>`, `<\|assistant\|>` | OpenAI chat-template tokens |
| `[INST]`, `[/INST]`, `<<SYS>>`, `<</SYS>>` | Llama / Mistral instruction tokens |
| `(?i)new\s+(system\s+)?(prompt\|message\|instructions\|task):` | Fake new-instructions header |
| `(?i)^system\s*:\s*(you\s+are\|new\s+task\|you\s+must)` | Fake system role prefix at line start |
| `(?i)(execute\|run\|perform)\s+(the\s+)?following\s+(command\|code\|instructions)` | Execute-following directive |
| `[A-Za-z0-9+/=]{200,}` | Inline base64 blob ≥200 chars (possible hidden payload) |

#### Wire in `settings.json`

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "WebFetch", "hooks": [{ "type": "command", "command": "python3 /your/home/.claude/hooks/detect_injection.py" }] },
      { "matcher": "mcp__.*",  "hooks": [{ "type": "command", "command": "python3 /your/home/.claude/hooks/detect_injection.py" }] }
    ]
  }
}
```

`install.py` wires this automatically alongside `protect_output.py` on the same matchers.

> **Tuning false positives:** If you regularly fetch security content or work in this repo (which discusses these patterns), expect occasional warns. The right responses are (a) ignore individual warns when you've inspected the source, (b) set `DETECT_INJECTION_MODE=off` for the session, or (c) remove specific patterns from the script if a single pattern is dominating noise. Do not blanket-disable; the surface is too useful to lose.

---

### `hook_logger.py` — Shared Audit Logger

Utility module imported by all three hooks above. Appends JSONL to:

```
~/.claude/hooks/logs/security-hooks.jsonl
```

Example entry:

```json
{"ts": "2026-01-01T12:00:00+00:00", "event": "pretool_block", "details": {"reason": "BLOCKED: rm -rf", "command": "rm -rf /tmp"}}
```

Event types: `pretool_block`, `posttool_block`, `posttool_redact`. Logging failures are silently suppressed so they never interfere with enforcement.

---

### `protect_mcp_config.py` — MCP Version Pin Guard

**Event:** `PreToolUse` on `Edit` and `Write`

Blocks Claude from writing `@latest` into any file whose name matches `settings*.json`. This prevents Claude Code itself from adding an unpinned MCP server to your settings during a session.

Detection: regex scan of `tool_input.new_string` (Edit) or `tool_input.content` (Write) for the pattern `@latest` followed by `"`, whitespace, `,`, or `]` — the characters that can follow a package specifier in JSON.

Example block:
```
BLOCKED: @latest detected in settings.json. Pin the MCP server version (e.g. @1.2.3)
to prevent silent supply-chain updates. See docs/mcp.md for guidance.
```

This hook covers the **Claude Code layer** only. For coverage of manual edits, use the git pre-commit hook and standalone validator described in [docs/mcp.md — Enforcing Version Pinning](mcp.md#enforcing-version-pinning).

**Wire in `settings.json`:**

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Edit",  "hooks": [{ "type": "command", "command": "python3 /your/home/.claude/hooks/protect_mcp_config.py" }] },
      { "matcher": "Write", "hooks": [{ "type": "command", "command": "python3 /your/home/.claude/hooks/protect_mcp_config.py" }] }
    ]
  }
}
```

`install.py` wires this automatically.

> **Dev-mode caveat:** If you are developing, testing, or otherwise working with local MCP servers that may legitimately reference `@latest` (e.g. pointing at an unreleased local build), you may want to temporarily disable or remove this hook. Comment out the two `PreToolUse` entries in `settings.json`, or remove the script, while iterating — then restore it before returning to normal use so supply-chain protection is back in place.

---

### PreCompact Hook Example

**Event:** `PreCompact` (no matcher — fires before every compaction)

The PreCompact hook runs just before Claude summarizes the conversation. It receives a JSON payload on stdin:

```json
{
  "trigger": "manual",
  "custom_instructions": "Focus on the auth module changes."
}
```

`trigger` is either `"manual"` (user ran `/compact`) or `"auto"` (Claude Code triggered compaction automatically). `custom_instructions` contains any hint the user typed before compacting.

The hook cannot block compaction — its return value is ignored. Its purpose is to log or export decisions before the full conversation history is replaced by the summary.

**Minimal logging snippet** — save as `~/.claude/hooks/precompact_log.py`:

```python
#!/usr/bin/env python3
"""PreCompact hook: logs compact events before conversation history is replaced."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path.home() / ".claude" / "hooks" / "logs" / "security-hooks.jsonl"

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

try:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "precompact",
        "details": {
            "trigger": payload.get("trigger"),
            "custom_instructions": payload.get("custom_instructions", ""),
        },
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
except Exception:
    pass  # Logging must never block the compaction.

sys.exit(0)
```

**Wire it in `~/.claude/settings.json`:**

```json
{
  "hooks": {
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /your/home/.claude/hooks/precompact_log.py"
          }
        ]
      }
    ]
  }
}
```

Note: PreCompact does not use a `matcher` field — it always fires regardless of what triggered the compaction.

See `settings/settings.precompact.json.example` for a complete settings file with this hook wired alongside the security hooks. See [docs/context-management.md](context-management.md) for when and why to use compaction.

---

## Installation

### Automated (recommended)

```bash
python3 install.py
```

`install.py` (at the repo root) copies all hook scripts to `~/.claude/hooks/`, resolves your home directory at install time, and writes absolute paths into `~/.claude/settings.json`. It is idempotent — re-running it updates paths if your install location changed. It backs up `settings.json` to `settings.json.bak` before writing.

```bash
python3 install.py --dry-run   # preview changes without writing
python3 install.py --uninstall # remove hook entries (scripts stay on disk)
```

### Manual

```bash
mkdir -p ~/.claude/hooks
cp hooks/*.py ~/.claude/hooks/
```

Then add to `~/.claude/settings.json` (note: `~` is **not** expanded — use the full path from `echo $HOME`). The full recommended wiring is in [`settings/settings.json.example`](../settings/settings.json.example); the minimum is:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "python3 /your/home/.claude/hooks/protect.py" },
          { "type": "command", "command": "python3 /your/home/.claude/hooks/protect_secrets.py" }
        ]
      },
      {
        "matcher": "Read",
        "hooks": [
          { "type": "command", "command": "python3 /your/home/.claude/hooks/protect_secrets.py" }
        ]
      },
      {
        "matcher": "Write",
        "hooks": [
          { "type": "command", "command": "python3 /your/home/.claude/hooks/protect_secrets.py" },
          { "type": "command", "command": "python3 /your/home/.claude/hooks/protect_mcp_config.py" }
        ]
      },
      {
        "matcher": "Edit",
        "hooks": [
          { "type": "command", "command": "python3 /your/home/.claude/hooks/protect_secrets.py" },
          { "type": "command", "command": "python3 /your/home/.claude/hooks/protect_mcp_config.py" }
        ]
      },
      {
        "matcher": "MultiEdit",
        "hooks": [
          { "type": "command", "command": "python3 /your/home/.claude/hooks/protect_secrets.py" }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "python3 /your/home/.claude/hooks/protect_output.py" }
        ]
      },
      { "matcher": "Read",     "hooks": [{ "type": "command", "command": "python3 /your/home/.claude/hooks/protect_output.py" }] },
      { "matcher": "Edit",     "hooks": [{ "type": "command", "command": "python3 /your/home/.claude/hooks/protect_output.py" }] },
      { "matcher": "Write",    "hooks": [{ "type": "command", "command": "python3 /your/home/.claude/hooks/protect_output.py" }] },
      { "matcher": "WebFetch", "hooks": [{ "type": "command", "command": "python3 /your/home/.claude/hooks/protect_output.py" }] },
      { "matcher": "mcp__.*",  "hooks": [{ "type": "command", "command": "python3 /your/home/.claude/hooks/protect_output.py" }] }
    ]
  }
}
```

Put hooks in the **global** `~/.claude/settings.json`, not in a project file — this ensures they apply to every session.

---

## Platform Notes

These hooks were developed and tested on **macOS**. The following patterns in the hook scripts are macOS-specific and may need adjustment on other platforms:

### Linux

| Script | macOS pattern | Linux adjustment needed |
|--------|--------------|------------------------|
| `protect.py` | `diskutil erase/zeroDisk/secureErase` | Add `wipefs`, `wipe` |
| `protect.py` | `/dev/disk*`, `/dev/rdisk*` | Add `/dev/sd*`, `/dev/nvme*`, `/dev/vd*` |
| `protect_secrets.py` | `pbcopy` in READ_COPY_VERBS | Add `xclip`, `xsel`, `wl-copy` |

`srm` and `shred` are already cross-platform; `find -delete`, `find -exec rm`, and git patterns are identical on both systems.

### Windows / WSL2

Untested. Under WSL2, Unix paths (`~/.ssh/`, `~/.aws/`) resolve correctly. The `python3` binary may need to be `python`. Native Windows credential paths (e.g. `%APPDATA%`) are not covered by the current patterns.

---

## Adding New Patterns

1. Add a `(regex, label)` tuple to the appropriate list in the hook script.
2. Test it:
   ```bash
   echo '{"tool_input":{"command":"your test command"}}' | python3 hooks/protect.py
   ```
3. Add the pattern and its rationale to the table in this file.

## Debugging

```bash
# Tail the audit log live
tail -f ~/.claude/hooks/logs/security-hooks.jsonl | python3 -m json.tool

# Replay a specific command through a hook
echo '{"tool_input":{"command":"cat ~/.aws/credentials"}}' | python3 hooks/protect_secrets.py

# Temporarily disable one hook: comment out its entry in settings.json
# No Claude Code restart needed — hooks are resolved per invocation.
```
