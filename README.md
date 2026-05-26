# Claude Code — Security & Best Practices Setup

A reference implementation for setting up Claude Code securely, following Anthropic's guidelines. Contains pre-built security hooks, settings templates, and detailed documentation.

> **Platform note:** This setup was tested on **macOS**. It should work on Linux with minor adjustments — see [Platform differences](#platform-differences) below. Windows (WSL2) is untested.

## What's Included

| Component | What it guards |
|-----------|---------------|
| `hooks/protect.py` | Blocks dangerous deletions (`rm -rf`, `find -delete`, disk writes) and `git push --force` |
| `hooks/protect_secrets.py` | Blocks reads/exfil of credential files and raw secret literals in commands |
| `hooks/protect_output.py` | Blocks tool outputs containing secret material before they reach Claude's context |
| `hooks/protect_mcp_config.py` | Blocks `@latest` in MCP server args when Claude writes or edits a settings file |
| `hooks/hook_logger.py` | Shared JSONL audit logger — appended to by all hooks above |
| `hooks/validate-mcp.py` | Standalone validator — checks settings files for `@latest`; use in CI or as a git pre-commit hook |
| `hooks/git-hooks/pre-commit` | Git pre-commit hook script that calls `validate-mcp.py --staged` |
| `install.py` | Automated installer — copies hooks and wires `settings.json` |
| `settings/settings.json.example` | Global settings with all security hooks wired |
| `settings/settings.precompact.json.example` | Extends the above with the PreCompact audit hook |
| `settings/settings.project.json.example` | Project-level settings template (commit to repo) |
| `settings/settings.local.json.example` | Personal project override template (git-ignored) |
| `docs/` | Detailed guides for hooks, permissions, MCP, CLAUDE.md, context, and CLI |

## Quick Setup

### Option A — Automated installer (recommended)

```bash
python3 install.py
```

The installer:
- Copies all hook scripts to `~/.claude/hooks/`
- Resolves your home directory at install time and writes absolute paths into `~/.claude/settings.json`
- Is idempotent — safe to re-run; updates paths if the install location changed
- Backs up your existing `settings.json` to `settings.json.bak` before writing

Preview what it would do without writing anything:

```bash
python3 install.py --dry-run
```

Remove the hook entries it added (scripts stay on disk):

```bash
python3 install.py --uninstall
```

---

### Option B — Manual setup

<details>
<summary>Expand manual steps</summary>

**1. Copy hook scripts**

```bash
mkdir -p ~/.claude/hooks
cp hooks/*.py ~/.claude/hooks/
```

**2. Wire hooks in `~/.claude/settings.json`**

Open `~/.claude/settings.json` (create it if it doesn't exist) and merge in:

```json
{
  "permissions": {
    "defaultMode": "default"
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "python3 /YOUR/HOME/.claude/hooks/protect.py" },
          { "type": "command", "command": "python3 /YOUR/HOME/.claude/hooks/protect_secrets.py" }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "python3 /YOUR/HOME/.claude/hooks/protect_output.py" }
        ]
      }
    ]
  }
}
```

Replace `/YOUR/HOME` with `echo $HOME`. Claude Code's `settings.json` does **not** expand `~`.

See `settings/settings.json.example` for the full recommended configuration.

</details>

---

### 3. Verify hooks are active

Start a Claude Code session and run `/hooks`. You should see three entries under `PreToolUse[Bash]` and `PostToolUse[Bash]`.

### 4. Smoke-test the hooks

```bash
echo '{"tool_input":{"command":"cat ~/.ssh/id_rsa"}}' | python3 ~/.claude/hooks/protect_secrets.py
# Expected: {"decision": "block", "reason": "BLOCKED: ..."}

echo '{"tool_output":"AKIAIOSFODNN7EXAMPLE"}}' | python3 ~/.claude/hooks/protect_output.py
# Expected: {"decision": "block", "reason": "BLOCKED: ..."}
```

---

## Documentation

| Guide | Contents |
|-------|----------|
| [docs/hooks.md](docs/hooks.md) | Hook event types, each script's detection logic, PreCompact example, installation |
| [docs/permissions.md](docs/permissions.md) | `default` / `acceptEdits` / `bypassPermissions` — when to use each, scoping |
| [docs/mcp.md](docs/mcp.md) | MCP server configuration, trust tiers, prompt injection mitigations |
| [docs/security-checklist.md](docs/security-checklist.md) | Pre-flight checklist covering hooks, credentials, git, and MCP |
| [docs/claude-md.md](docs/claude-md.md) | Writing effective CLAUDE.md files — memory hierarchy, imports, `#` shorthand, starter template |
| [docs/context-management.md](docs/context-management.md) | `/compact` vs `/clear`, PreCompact hook, when to start a new session |
| [docs/cli-and-models.md](docs/cli-and-models.md) | Slash commands, keyboard shortcuts, `--print`, `--fast`, model selection, `effortLevel` |

---

## Settings Hierarchy

Claude Code merges settings in this order (later entries win):

```
~/.claude/settings.json          # global — applies to every project
<project>/.claude/settings.json  # project — committed to the repo
<project>/.claude/settings.local.json  # personal project override — git-ignored
```

Put security hooks in the **global** file so they apply everywhere, regardless of project settings.

Add `.claude/settings.local.json` to your global `.gitignore` — it contains personal overrides that must never be committed:

```
echo '.claude/settings.local.json' >> ~/.gitignore_global
git config --global core.excludesfile ~/.gitignore_global
```

---

## Platform Differences

This setup was developed and tested on **macOS**. The hooks work as-is on most Linux distributions, but a few patterns are macOS-specific and should be reviewed:

| Pattern | macOS | Linux equivalent |
|---------|-------|-----------------|
| `diskutil erase/zeroDisk/secureErase` | `protect.py` | Add `wipefs`, `wipe`, `shred /dev/...` |
| `srm` (secure-remove) | `protect.py` | `shred` is already covered |
| `/dev/disk*`, `/dev/rdisk*` (raw disk) | `protect.py` | Add `/dev/sd*`, `/dev/nvme*`, `/dev/vd*` |
| `pbcopy` (clipboard) | `protect_secrets.py` READ_COPY_VERBS | Add `xclip`, `xsel`, `wl-copy` |

On **Windows / WSL2**: untested. The `python3` binary may be `python`. Credential paths (`~/.ssh/`, `~/.aws/`) resolve correctly under WSL2; native Windows paths are not covered.

To add Linux-specific patterns, edit `hooks/protect.py` and `hooks/protect_secrets.py` and re-run `python3 install.py`. See [docs/hooks.md](docs/hooks.md) for the pattern format.

---

## Audit Log

All block events are written to:

```
~/.claude/hooks/logs/security-hooks.jsonl
```

Monitor in real time:

```bash
tail -f ~/.claude/hooks/logs/security-hooks.jsonl | python3 -m json.tool
```
