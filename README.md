# Claude Code — Security & Best Practices Setup

![Without this setup, Claude Code can leak credentials and run dangerous commands. With it, the hooks step in before anything risky happens.](resources/readme-overview.png)

Claude Code is Anthropic's AI coding assistant. It reads your files, edits your code, and runs commands on your machine. That's powerful, and it's also where things can go wrong:

- It might read files it shouldn't — the private keys you use to log into servers, or your cloud credentials.
- It might run commands you didn't mean — delete files, push broken code, wipe a disk.
- It might be tricked by something it read — a web page or document that quietly tells it to do things you didn't ask for.

This repo is a **security and best-practices setup** for Claude Code. It provides security hooks that block risky actions before they execute, and guidance on permissions, MCP servers, and safe workflows — so you're covered both technically and operationally when using Claude Code on a real machine.

> **⚠️ Platform note:** Tested on **macOS**. Works on Linux with minor adjustments — see [Platform differences](#platform-differences) below. Windows (WSL2) is untested.

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

### 1. Install hooks

**Option A — Automated installer (recommended)**

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

**Option B — Manual setup**

<details>
<summary>Expand manual steps</summary>

Copy hook scripts:

```bash
mkdir -p ~/.claude/hooks
cp hooks/*.py ~/.claude/hooks/
```

Wire hooks in `~/.claude/settings.json` (create it if it doesn't exist):

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

### 2. Verify hooks are active

Start a Claude Code session and run `/hooks`. You should see three entries under `PreToolUse[Bash]` and `PostToolUse[Bash]`.

### 3. Smoke-test the hooks

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

Claude Code merges settings in this order — later entries win:

```mermaid
flowchart TD
    A["🌍 Global\n~/.claude/settings.json\nApplies to every project"]
    B["📁 Project\n&lt;project&gt;/.claude/settings.json\nCommitted to the repo"]
    C["👤 Personal override\n&lt;project&gt;/.claude/settings.local.json\nGit-ignored, never committed"]
    M["⚙️ Final merged settings\nConflicts resolved — highest priority wins"]

    A -->|"priority 1 — lowest"| M
    B -->|"priority 2 — overrides global"| M
    C -->|"priority 3 — highest"| M

    style A fill:#1e3a5f,color:#ffffff,stroke:#4a90d9
    style B fill:#1e4d2b,color:#ffffff,stroke:#4caf50
    style C fill:#4d2b1e,color:#ffffff,stroke:#e07b39
    style M fill:#2d2d2d,color:#ffffff,stroke:#888888
```

> **🔒 Security rule:** Put security hooks in the **global** file (`~/.claude/settings.json`) so they apply to every project and cannot be overridden or omitted by project-level settings.

> **⚠️ Warning:** `.claude/settings.local.json` contains personal overrides and must **never** be committed to version control. Add it to your global `.gitignore`:
>
> ```bash
> echo '.claude/settings.local.json' >> ~/.gitignore_global
> git config --global core.excludesfile ~/.gitignore_global
> ```

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
